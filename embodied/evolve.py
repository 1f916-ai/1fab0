"""Evolve the missing biology: per-hemilineage output gains (+ DN, MN, exc, inh) so that DNg100 drives a tripod gait
in the MaleCNS v1.0 nerve cord (Pugliese et al. 2025 rate model). CMA-ES, batched on the GPU.

Training target (published): tripod coordination in walking Drosophila (L1,R2,L3 vs R1,L2,R3 in antiphase;
Strauss & Heisenberg 1990; Wosnitza et al. 2013; Mendes et al. 2013), stepping in the 5-15 Hz range, and
flexor/extensor alternation within a leg. Nothing about MDN, DNp09, DNa02 or looming is used: those are held out.

--null shuffled: identical search on a degree-preserving scrambled wiring (post-synaptic endpoints permuted).
"""
import sys, os, json, time, math, argparse
import numpy as np, torch, cma
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnc_rate as V, malecns_cpg as C
import pyarrow.feather as f, pyarrow.compute as pc
dev = V.dev

ap = argparse.ArgumentParser()
ap.add_argument('--null', default='real', choices=['real', 'shuffled'])
ap.add_argument('--gens', type=int, default=120); ap.add_argument('--pop', type=int, default=24); ap.add_argument('--seeds', type=int, default=2)
ap.add_argument('--T', type=float, default=1.2); ap.add_argument('--out', default=None)
ap.add_argument('--fitness', default='v1', choices=['v1', 'v2', 'v3']); ap.add_argument('--x0', default=None); ap.add_argument('--sigma', type=float, default=0.5)
a = ap.parse_args()
OUT = a.out or os.path.expanduser(f'~/fly-data/work/evo_{a.null}'); os.makedirs(OUT, exist_ok=True)

ann = f.read_table(f'{V.DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId', 'status', 'trumanHl'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(V.ids)
HL = ann['trumanHl'].fillna('').to_numpy()

keep = C.pathway_subset(['fl', 'ml', 'hl'], 2); n = len(keep)
sub = V.A[keep][:, keep].tocoo()
row, col, val = sub.row, sub.col, sub.data
if a.null == 'shuffled':
    rng = np.random.default_rng(12345); row = row[rng.permutation(len(row))]
s = V.sign[keep][col]
def sp(mask):
    return torch.sparse_coo_tensor(torch.tensor(np.vstack([row[mask], col[mask]]), dtype=torch.int64), torch.tensor(val[mask] * np.abs(s[mask]), dtype=torch.float32), (n, n)).coalesce().to(dev)
W_exc, W_inh = sp(s > 0), sp(s < 0)

# parameter groups: presynaptic gain per group
sup = V.SUP[keep]; hl = HL[keep]
groups = ['DN', 'MN'] + sorted(set(hl[(sup == 'vnc_intrinsic') & (hl != '')]))
gid = np.full(n, -1)
gid[sup == 'descending_neuron'] = 0; gid[sup == 'vnc_motor'] = 1
for i, g in enumerate(groups[2:], start=2): gid[(sup == 'vnc_intrinsic') & (hl == g)] = i
NG = len(groups); NP = NG + 2   # + exc, inh multipliers
print(f'null={a.null} neurons {n} groups {NG} params {NP} unassigned {(gid < 0).sum()}', flush=True)
gid_t = torch.tensor(np.where(gid < 0, NG, gid), device=dev)

# legs: swing proxy = Tr flexor MN, stance proxy = Sternotrochanter MN (trochanter depressor)
LEGS = [('fl', 'L'), ('ml', 'R'), ('hl', 'L'), ('fl', 'R'), ('ml', 'L'), ('hl', 'R')]   # first three = tripod A
def pool(leg, side, word):
    return np.flatnonzero((sup == 'vnc_motor') & (V.SUB[keep] == leg) & (V.SIDE[keep] == side) & np.array([word in t for t in V.TYP[keep]]))
FLEX = [pool(l, s_, 'Tr flexor') for l, s_ in LEGS]; EXT = [pool(l, s_, 'Sternotrochanter') for l, s_ in LEGS]
print('flexor pool sizes', [len(x) for x in FLEX], 'extensor pool sizes', [len(x) for x in EXT], flush=True)
rec_ix = torch.tensor(np.concatenate(FLEX + EXT), device=dev)
dng = np.flatnonzero(V.TYP[keep] == 'DNg100')

def neuron_params(seed, B):
    rng = np.random.default_rng(seed)
    d = dict(tau=np.clip(rng.normal(.02, .002, n), .005, None), a=rng.normal(1, .1, n), theta=rng.normal(7.5, .6, n), cap=rng.normal(200, 10, n))
    return {k: torch.tensor(v, dtype=torch.float32, device=dev)[:, None].expand(n, B) for k, v in d.items()}

def run_batch(X, seed, stim_ix, stim_I=250.0, T=None, dt=0.0005):
    """X: B x NP log-gains. Returns recorded pools (steps_ms x len(rec) x B) and saturation fraction per candidate."""
    T = T or a.T; B = X.shape[0]
    g = torch.exp(torch.tensor(X[:, :NG], dtype=torch.float32, device=dev))              # B x NG
    g = torch.cat([g, torch.ones(B, 1, device=dev)], 1)                                     # unassigned -> 1
    G = g[:, gid_t].T.contiguous()                                                          # n x B
    e = 0.03 * torch.exp(torch.tensor(X[:, NG], dtype=torch.float32, device=dev)); i_ = 0.03 * torch.exp(torch.tensor(X[:, NG + 1], dtype=torch.float32, device=dev))
    P = neuron_params(seed, B)
    R = torch.zeros(n, B, device=dev); I = torch.zeros(n, B, device=dev); I[stim_ix] = stim_I
    out = []; sat = torch.zeros(B, device=dev); steps = int(T / dt)
    for k in range(steps):
        GR = G * R
        x = (I if k * dt >= 0.02 else 0) + torch.sparse.mm(W_exc, GR) * e - torch.sparse.mm(W_inh, GR) * i_ - P['theta']
        R = R + dt * (torch.clamp(P['cap'] * torch.tanh((P['a'] / P['cap']) * x), min=0) - R) / P['tau']
        if k % 2 == 0:
            out.append(R[rec_ix])
            if k * dt > 0.3: sat += (R > 180).float().mean(0)
    return torch.stack(out).cpu().numpy(), (sat / (steps / 2)).cpu().numpy()

def fitness(Y, sat, T=None):
    """Y: steps x rec x B. Higher is better; returns per-candidate score and components."""
    T = T or a.T; t0 = 400; seg = Y[t0:]; L = len(seg)
    nf = [len(x) for x in FLEX]; ne = [len(x) for x in EXT]
    offs = np.cumsum([0] + nf + ne)
    fr = np.fft.rfftfreq(L, .001); band = (fr >= 5) & (fr <= 15)
    B = Y.shape[2]; scores = np.zeros(B); comps = []
    for b in range(B):
        flex = np.array([seg[:, offs[j]:offs[j + 1], b].mean(1) if nf[j] else np.zeros(L) for j in range(6)])
        ext = np.array([seg[:, offs[6 + j]:offs[7 + j], b].mean(1) if ne[j] else np.zeros(L) for j in range(6)])
        sig = flex - ext; sig = sig - sig.mean(1, keepdims=True)
        amp = sig.max(1) - sig.min(1)
        F = np.fft.rfft(sig, axis=1); P_ = np.abs(F) ** 2
        tot = P_[:, 1:].sum() + 1e-9
        k = np.flatnonzero(band)[P_[:, band].sum(0).argmax()] if band.any() else 1
        rhythm = P_[:, band].sum() / tot
        ph = np.angle(F[:, k]); phf = np.angle(np.fft.rfft(flex - flex.mean(1, keepdims=True), axis=1)[:, k]); phe = np.angle(np.fft.rfft(ext - ext.mean(1, keepdims=True), axis=1)[:, k])
        grp = np.array([0, 0, 0, 1, 1, 1]); tri = []
        for p in range(6):
            for q in range(p + 1, 6):
                want = 0.0 if grp[p] == grp[q] else math.pi
                tri.append(math.cos(ph[p] - ph[q] - want))
        tripod = float(np.mean(tri)); alt = float(np.mean(np.cos(phf - phe - math.pi)))
        moving = float(np.mean(np.clip(amp / 20.0, 0, 1)))
        sc = moving * (0.45 * tripod + 0.2 * alt + 0.35 * rhythm) - 2.0 * float(sat[b])
        balance = uniform = 1.0
        lock = 1.0
        if a.fitness in ('v2', 'v3'):
            left = amp[[0, 2, 4]].mean(); right = amp[[1, 3, 5]].mean()   # LEGS: flL mlR hlL | flR mlL hlR -> left = idx 0,2,4
            balance = float(1.0 - abs(left - right) / (left + right + 1e-9)); uniform = float(amp.min() / (amp.max() + 1e-9))
            sc = moving * (0.35 * tripod + 0.15 * alt + 0.25 * rhythm + 0.15 * balance + 0.10 * uniform) - 2.0 * float(sat[b])
        if a.fitness == 'v3':
            from scipy.signal import hilbert, butter, filtfilt
            bb, aa = butter(2, [2 / 500, 20 / 500], btype='band')
            hp = np.angle(hilbert(filtfilt(bb, aa, sig, axis=1), axis=1))[:, 100:-100]
            # cross-side pairs in LEGS order (0 flL,1 mlR,2 hlL,3 flR,4 mlL,5 hlR): left = 0,2,4 ; right = 1,3,5
            locks = [abs(np.mean(np.exp(1j * (hp[p] - hp[q])))) for p in (0, 2, 4) for q in (1, 3, 5)]
            lock = float(np.mean(locks))
            sc = moving * (0.25 * tripod + 0.10 * alt + 0.20 * rhythm + 0.10 * balance + 0.10 * uniform + 0.25 * lock) - 2.0 * float(sat[b])
        scores[b] = sc; comps.append(dict(tripod=round(tripod, 3), alternation=round(alt, 3), rhythm=round(float(rhythm), 3), moving=round(moving, 3), freq=round(float(fr[k]), 2), sat=round(float(sat[b]), 4), balance=round(balance, 3), uniform=round(uniform, 3), lock=round(lock, 3)))
    return scores, comps

x0 = np.array(json.load(open(a.x0))['x']) if a.x0 else np.zeros(NP)
es = cma.CMAEvolutionStrategy(x0, a.sigma, {'popsize': a.pop, 'bounds': [-2.0, 2.0], 'seed': 1, 'verbose': -9})
best = (-1e9, None, None); log = open(f'{OUT}/log.jsonl', 'a')
base_scores = None
for gen in range(a.gens):
    t0 = time.time()
    X = np.array(es.ask()) if gen > 0 else np.vstack([x0, np.array(es.ask())[1:]])
    S = np.zeros(len(X)); allc = []
    for sd in range(a.seeds):
        Y, sat = run_batch(X, seed=sd, stim_ix=dng)
        sc, comps = fitness(Y, sat); S += sc / a.seeds; allc.append(comps)
    if gen == 0: base_scores = dict(score=float(S[0]), comps=[c[0] for c in allc])
    es.tell(list(X), list(-S))
    j = int(S.argmax())
    if S[j] > best[0]:
        best = (float(S[j]), X[j].tolist(), [c[j] for c in allc])
        json.dump(dict(null=a.null, score=best[0], x=best[1], comps=best[2], groups=groups + ['exc', 'inh'], gen=gen, baseline=base_scores), open(f'{OUT}/best.json', 'w'))
    rec = dict(gen=gen, secs=round(time.time() - t0, 1), best=round(best[0], 4), gen_best=round(float(S[j]), 4), gen_mean=round(float(S.mean()), 4), comps=allc[0][j], sigma=round(es.sigma, 4))
    log.write(json.dumps(rec) + '\n'); log.flush()
    print(json.dumps(rec), flush=True)
print('done', best[0])
