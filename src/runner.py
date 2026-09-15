#!/usr/bin/env python3
"""fly-battery reference runner: leaky integrate-and-fire (Shiu et al. 2024 family) over G_traced,
with two nulls (degree-preserving shuffled twin; real graph with random dynamics), scoring the six
battery items. Usage: python src/runner.py [--items 1,2] [--trials 10] [--conditions real,shuffled,random] [--smoke]
Outputs results/runs.jsonl (hash-chained, one row per trial) and results/verdicts.json.
"""
import json, os, sys, time, hashlib, argparse, math
import numpy as np, scipy.sparse as sp, torch
import pyarrow.feather as f, pyarrow.compute as pc
DER = os.environ.get('FLY_DERIVED', 'data/derived'); DATA = os.environ.get('FLY_DATA', 'data/malecns')
dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
B = json.load(open('battery/battery.json')); R = B['reference_dynamics']; T = B['trials']
ids = np.load(f'{DER}/G_traced_bodyIds.npy'); n = len(ids); sign = np.load(f'{DER}/G_traced_presyn_sign.npy')
A = sp.load_npz(f'{DER}/G_traced_post_by_pre.npz').tocoo()        # rows post, cols pre, values synapse count
ann = f.read_table(f'{DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId', 'status', 'type', 'somaSide', 'receptorType'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(ids)
typ = ann['type'].fillna('').to_numpy(); side = ann['somaSide'].fillna('').to_numpy(); rec = ann['receptorType'].fillna('').to_numpy()
def cls(spec):
    """Resolve a stimulus/readout spec to an index array."""
    if isinstance(spec, dict):
        if 'receptorType' in spec: m = np.char.find(rec.astype(str), spec['receptorType']) >= 0
        else: m = np.isin(typ, spec['classes'])
        if spec.get('side'): m &= (side == spec['side'])
        return np.flatnonzero(m)
    return np.flatnonzero(np.isin(typ, list(spec)))
def build_weights(coo, seed=None):
    """Signed weight matrix in mV per spike (before per-neuron scaling). seed -> degree-preserving shuffle."""
    row, col, val = coo.row, coo.col, coo.data
    if seed is not None:
        rng = np.random.default_rng(1000 + seed); row = row[rng.permutation(len(row))]   # permute postsynaptic endpoints: keeps every in- and out-degree
    w = val * sign[col] * R['W_syn_mV']
    M = sp.csr_matrix((w.astype(np.float32), (row, col)), shape=(n, n)); M.sum_duplicates(); M.eliminate_zeros()
    Mc = M.tocoo(); idx = torch.tensor(np.vstack([Mc.row, Mc.col]), dtype=torch.int64); v = torch.tensor(Mc.data, dtype=torch.float32)
    return torch.sparse_coo_tensor(idx, v, (n, n)).coalesce().to(dev)
def params(kind, seed):
    P = dict(Tm=R['T_mbr_ms'], tau=R['tau_syn_ms'], dly=R['T_dly_ms'], ref=R['T_refractory_ms'], gap=R['V_threshold_mV'] - R['V_rest_mV'], wscale=1.0)
    jit = None
    if kind == 'random':
        rng = np.random.default_rng(2000 + seed)
        P = dict(Tm=rng.uniform(5, 80), tau=rng.uniform(1, 20), dly=rng.uniform(0.5, 5), ref=rng.uniform(1, 5), gap=rng.uniform(3, 20), wscale=float(np.exp(rng.uniform(np.log(0.05), np.log(1.5))) / R['W_syn_mV']))   # W_syn drawn logU[0.05,1.5] mV, expressed relative to the reference 0.275 mV. BUG until 2026-09-15: the division sat inside exp(), giving exp(u/0.275) in [2e-5, 4.4], so 7 of 10 sealed-seed draws fell below 0.01 and the twin was silent by construction.)
        jit = torch.tensor(np.exp(rng.uniform(np.log(0.5), np.log(2), size=n)), dtype=torch.float32, device=dev)
    return P, jit
def sign_permuted_weights(coo, seed):
    """random-dynamics twin also permutes the sign assignment within counts."""
    rng = np.random.default_rng(3000 + seed); s2 = sign[rng.permutation(n)]
    w = coo.data * s2[coo.col] * R['W_syn_mV']
    M = sp.csr_matrix((w.astype(np.float32), (coo.row, coo.col)), shape=(n, n)); M.eliminate_zeros(); Mc = M.tocoo()
    idx = torch.tensor(np.vstack([Mc.row, Mc.col]), dtype=torch.int64); v = torch.tensor(Mc.data, dtype=torch.float32)
    return torch.sparse_coo_tensor(idx, v, (n, n)).coalesce().to(dev)
def simulate(W, P, jit, inputs, readouts, seed, dt=1.0):
    """inputs: list of (index array, rate function of t_ms -> Hz). Returns spike counts per readout in baseline and stimulus windows."""
    g = torch.Generator(device='cpu').manual_seed(seed)
    v = torch.zeros(n, device=dev); gsyn = torch.zeros(n, device=dev); refr = torch.zeros(n, device=dev)
    D = max(1, int(round(P['dly'] / dt))); buf = [torch.zeros(n, device=dev) for _ in range(D)]
    Tw, Tb, Ts = T['warmup_ms'], T['baseline_ms'], T['stimulus_ms']; steps = int((Tw + Tb + Ts) / dt)
    counts = {k: [0.0, 0.0] for k in readouts}; ro = {k: torch.tensor(ix, device=dev) for k, ix in readouts.items()}
    decay_g = math.exp(-dt / P['tau']); Vth = P['gap']
    inp = [(torch.tensor(ix, device=dev), rate) for ix, rate in inputs]
    for t in range(steps):
        tm = t * dt; s_del = buf[t % D]
        inc = torch.sparse.mm(W, s_del[:, None])[:, 0] * P['wscale']
        if jit is not None: inc = inc * jit
        gsyn = gsyn * decay_g + inc
        v = v + dt * (gsyn - v) / P['Tm']
        spk = (v >= Vth) & (refr <= 0)
        if tm >= Tw + Tb:
            for ix, rate in inp:
                r = rate(tm - Tw - Tb) if callable(rate) else rate
                forced = torch.rand(len(ix), generator=g) < (r * dt / 1000.0)
                spk[ix] = spk[ix] | forced.to(dev)
        v = torch.where(spk, torch.zeros_like(v), v); refr = torch.where(spk, torch.full_like(refr, P['ref']), refr - dt)
        s = spk.float(); buf[t % D] = s
        if tm >= Tw:
            win = 0 if tm < Tw + Tb else 1
            for k, ix in ro.items(): counts[k][win] += float(s[ix].sum())
    out = {}
    for k, ix in readouts.items():
        nb, ns = len(ix), len(ix)
        out[k] = dict(baseline_hz=counts[k][0] / max(1, nb) / (Tb / 1000.0), stimulus_hz=counts[k][1] / max(1, ns) / (Ts / 1000.0), n=int(len(ix)))
    return out
# ---- items -> (stimuli, readouts)
def item_plan(it):
    stim = {}
    if it['id'] == 4:
        for name, s in it['stimuli'].items():
            ix = cls({'classes': s['classes']}); Ts = T['stimulus_ms']
            if name == 'recede': rate = lambda t, Ts=Ts: min(150.0, 150.0 * 0.05 / max(0.02, t / Ts))
            else: rate = lambda t, Ts=Ts: min(150.0, 150.0 * 0.05 / max(0.02, (Ts - t) / Ts))   # loom and control_visual: same rising profile
            stim[name] = [(ix, rate)]
    else:
        for name, s in it['stimuli'].items():
            if s == [] or s == {} : stim[name] = []; continue
            r = it['rate_hz'][name] if isinstance(it['rate_hz'], dict) else it['rate_hz']
            stim[name] = [(cls(s), float(r))]
    ro = {'DNp09': cls(['DNp09']), 'MDN': cls({'classes': ['MDN']}), 'DNp01': cls(['DNp01']), 'pC1': np.flatnonzero(np.char.startswith(typ.astype(str), 'pC1')), 'pIP10': cls(['pIP10']),
          'HS_R': cls({'classes': ['HSE', 'HSN', 'HSS'], 'side': 'R'}), 'HS_L': cls({'classes': ['HSE', 'HSN', 'HSS'], 'side': 'L'}), 'DNa02_R': cls({'classes': ['DNa02'], 'side': 'R'}), 'DNa02_L': cls({'classes': ['DNa02'], 'side': 'L'})}
    return stim, ro
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--items', default='1,2,3,4,5,6'); ap.add_argument('--trials', type=int, default=T['paired_trials']); ap.add_argument('--conditions', default='real,shuffled,random'); ap.add_argument('--smoke', action='store_true'); ap.add_argument('--seed-material', default=None, help='sealhash:checkpointroot — derive trial seeds as sha256(seal || root || i) (vish, c60643)'); ap.add_argument('--out', default='results/runs.jsonl')
    a = ap.parse_args()
    def trial_seed(i):
        if not a.seed_material: return i
        seal, root = a.seed_material.split(':'); return int(hashlib.sha256((seal + root + str(i)).encode()).hexdigest()[:15], 16)
    items = [it for it in B['items'] if it['id'] in {int(x) for x in a.items.split(',')}]; conds = a.conditions.split(','); ntr = 1 if a.smoke else a.trials
    os.makedirs('results', exist_ok=True); prev = hashlib.sha256(open('battery/battery.json', 'rb').read()).hexdigest()
    W_real = build_weights(A); shuffles = {}
    t0 = time.time(); rows = 0
    with open(a.out, 'a') as fo:
        for it in items:
            stim, ro = item_plan(it)
            for cond in conds:
                for tr in range(ntr):
                    sd = trial_seed(tr)
                    if cond == 'real': W, (P, jit) = W_real, params('reference', sd)
                    elif cond == 'shuffled':
                        if tr not in shuffles: shuffles[tr] = build_weights(A, seed=sd)
                        W, (P, jit) = shuffles[tr], params('reference', sd)
                    else: W, (P, jit) = sign_permuted_weights(A, sd), params('random', sd)
                    for sname, inputs in stim.items():
                        t1 = time.time(); res = simulate(W, P, jit, inputs, ro, seed=sd)
                        row = dict(seed=sd, seed_material=a.seed_material, battery_sha256=hashlib.sha256(open('battery/battery.json', 'rb').read()).hexdigest(), item=it['id'], condition=cond, trial=tr, stimulus=sname, params={k: (round(v, 4) if isinstance(v, float) else v) for k, v in P.items()}, readouts=res, wall_s=round(time.time() - t1, 1), prev=prev)
                        prev = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(); row['sha256'] = prev
                        fo.write(json.dumps(row, sort_keys=True) + '\n'); fo.flush(); rows += 1
                        print('item %d %-8s trial %d %-12s %5.1fs  DNp09 %.2f MDN %.2f DNp01 %.2f pC1 %.2f pIP10 %.2f HS R/L %.2f/%.2f' % (it['id'], cond, tr, sname, row['wall_s'], res['DNp09']['stimulus_hz'], res['MDN']['stimulus_hz'], res['DNp01']['stimulus_hz'], res['pC1']['stimulus_hz'], res['pIP10']['stimulus_hz'], res['HS_R']['stimulus_hz'], res['HS_L']['stimulus_hz']), flush=True)
    print('rows', rows, 'total %.0fs' % (time.time() - t0))
if __name__ == '__main__': main()
