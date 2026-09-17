"""Activate descending neurons (optogenetics-style forced spiking) and record leg/wing motor neuron pools."""
import os, sys, json, math, time
sys.path.insert(0, os.environ['FLY_SRC'])
import numpy as np, torch, pyarrow.feather as f, pyarrow.compute as pc
import runner as R

ann = f.read_table(f'{R.DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId','status','type','superclass','subclass','somaSide','somaNeuromere'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(R.ids)
sup = ann['superclass'].fillna('').to_numpy(); sub = ann['subclass'].fillna('').to_numpy(); typ = ann['type'].fillna('').to_numpy(); side = ann['somaSide'].fillna('').to_numpy()
mot = np.flatnonzero(np.isin(sup, ['vnc_motor']))
pools = {}
for i in mot:
    key = f"{sub[i]}|{side[i]}|{typ[i]}"
    pools.setdefault(key, []).append(i)
pool_keys = sorted(pools); pool_ix = [np.array(pools[k]) for k in pool_keys]
print('motor pools', len(pool_keys), 'motor neurons', len(mot), flush=True)

def by_type(names, s=None):
    m = np.isin(typ, names)
    if s: m &= side == s
    return np.flatnonzero(m)

T_PRE, T_STIM, BIN = 200, 600, 20
def run(inputs, W, P, seed=0):
    dev, n = R.dev, R.n
    g = torch.Generator(device='cpu').manual_seed(seed)
    v = torch.zeros(n, device=dev); gs = torch.zeros(n, device=dev); refr = torch.zeros(n, device=dev)
    D = max(1, int(round(P['dly']))); buf = [torch.zeros(n, device=dev) for _ in range(D)]
    decay = math.exp(-1.0 / P['tau'])
    mot_t = torch.tensor(mot, device=dev)
    rec = []; acc = torch.zeros(len(mot), device=dev)
    inp = [(torch.tensor(ix, device=dev), r) for ix, r in inputs]
    for t in range(T_PRE + T_STIM):
        inc = torch.sparse.mm(W, buf[t % D][:, None])[:, 0] * P['wscale']
        gs = gs * decay + inc; v = v + (gs - v) / P['Tm']
        spk = (v >= P['gap']) & (refr <= 0)
        if t >= T_PRE:
            for ix, r in inp:
                rr = r(t - T_PRE) if callable(r) else r
                spk[ix] = spk[ix] | (torch.rand(len(ix), generator=g) < rr / 1000.0).to(dev)
        v = torch.where(spk, torch.zeros_like(v), v); refr = torch.where(spk, torch.full_like(refr, P['ref']), refr - 1.0)
        s = spk.float(); buf[t % D] = s
        acc += s[mot_t]
        if (t + 1) % BIN == 0:
            rec.append(acc.cpu().numpy().copy()); acc.zero_()
    rec = np.array(rec)  # bins x motor neurons (spike counts)
    local = {i: j for j, i in enumerate(mot)}
    out = {}
    for k, ix in zip(pool_keys, pool_ix):
        cols = [local[i] for i in ix]
        out[k] = (rec[:, cols].sum(1) / len(cols) / (BIN / 1000.0)).round(1).tolist()
    return out

loom_rate = lambda t: min(150.0, 150.0 * 0.05 / max(0.02, (T_STIM - t) / T_STIM))
EXP = {
    'loom': [(by_type(['LC4', 'LPLC2']), loom_rate)],
    'GF_opto': [(by_type(['DNp01']), 150.0)],
    'MDN_opto': [(by_type(['MDN']), 100.0)],
    'DNp09_opto': [(by_type(['DNp09']), 100.0)],
    'DNa02_L_opto': [(by_type(['DNa02'], 'L'), 100.0)],
    'DNg100_opto': [(by_type(['DNg100']), 100.0)],
}
W = R.build_weights(R.A); P, _ = R.params('reference', 0)
res = {}
for name, inputs in EXP.items():
    t0 = time.time(); res[name] = run(inputs, W, P)
    active = sorted(((np.mean(v[T_PRE // BIN:]), k) for k, v in res[name].items()), reverse=True)[:14]
    print(f'\n== {name} ({len(inputs[0][0])} input neurons, {time.time()-t0:.0f}s)')
    for r, k in active:
        if r > 0.5: print(f'   {r:7.1f} Hz  {k}')
json.dump(res, open(os.path.join(os.path.dirname(__file__), 'probe_motor.json'), 'w'))
