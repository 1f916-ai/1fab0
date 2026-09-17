import sys, time, numpy as np, torch, scipy.sparse as sp
sys.path.insert(0, '/Users/dovi/fly-data/work')
import vnc_rate as V
dev = V.dev
NEURO = None
import pyarrow.feather as f, pyarrow.compute as pc
ann = f.read_table(f'{V.DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId','status','somaNeuromere'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(V.ids)
NM = ann['somaNeuromere'].fillna('').to_numpy()

def pathway_subset(mn_sub, hops=3):
    """DNs + neurons on paths DN -> ... -> MN within `hops` synaptic steps (forward from DNs AND backward from MNs)."""
    vnc = np.isin(V.SUP, ['descending_neuron', 'vnc_intrinsic', 'vnc_motor'])
    Av = V.A.multiply(vnc[:, None]).multiply(vnc[None, :]).tocsr()   # post x pre
    Av = (Av >= 1).astype(np.int8)
    dn = np.flatnonzero(V.SUP == 'descending_neuron'); mn = np.flatnonzero((V.SUP == 'vnc_motor') & np.isin(V.SUB, mn_sub))
    fwd = np.zeros(len(V.ids), bool); fwd[dn] = True; front = fwd.copy()
    for _ in range(hops):
        nxt = (Av @ front.astype(np.int8)) > 0; front = nxt & ~fwd; fwd |= nxt
    bwd = np.zeros(len(V.ids), bool); bwd[mn] = True; front = bwd.copy(); At = Av.T.tocsr()
    for _ in range(hops):
        nxt = (At @ front.astype(np.int8)) > 0; front = nxt & ~bwd; bwd |= nxt
    keep = np.flatnonzero((fwd & bwd) | np.isin(np.arange(len(V.ids)), mn) | np.isin(np.arange(len(V.ids)), dn))
    return keep

def build_from(keep, seed=0, exc=0.03, inh=0.03):
    sub = V.A[keep][:, keep].tocoo(); s = V.sign[keep][sub.col]
    w = sub.data * np.where(s > 0, exc, np.where(s < 0, -inh, 0.0))
    M = torch.sparse_coo_tensor(torch.tensor(np.vstack([sub.row, sub.col]), dtype=torch.int64), torch.tensor(w, dtype=torch.float32), (len(keep), len(keep))).coalesce().to(dev)
    rng = np.random.default_rng(seed); n = len(keep)
    P = {k: torch.tensor(v, dtype=torch.float32, device=dev) for k, v in dict(tau=np.clip(rng.normal(0.02, 0.002, n), .005, None), a=rng.normal(1, .1, n), theta=rng.normal(7.5, .6, n), cap=rng.normal(200, 10, n)).items()}
    return M, P

def score(X):
    seg = X[500:1900]; act = seg.max(0) > 5
    if not act.any(): return 0, 0, 0
    Z = seg[:, act] - seg[:, act].mean(0); F = np.abs(np.fft.rfft(Z, axis=0)); fr = np.fft.rfftfreq(len(Z), .001); b = (fr > 3) & (fr < 30)
    amp = seg[:, act].max(0) - seg[:, act].min(0)
    return act.sum(), fr[b][F[b].sum(1).argmax()], (amp > 20).sum()

if __name__ == '__main__':
    dng = np.flatnonzero(V.TYP == 'DNg100')
    for label, mn_sub, hops in [('front legs, 2 hops', ['fl'], 2), ('front legs, 3 hops', ['fl'], 3), ('all legs, 2 hops', ['fl', 'ml', 'hl'], 2)]:
        keep = pathway_subset(mn_sub, hops); M, P = build_from(keep)
        mn_loc = np.flatnonzero((V.SUP[keep] == 'vnc_motor') & np.isin(V.SUB[keep], mn_sub))
        for stim, sl in [([dng[0]], 'DNg100 L'), (list(dng), 'DNg100 both')]:
            t0 = time.time(); X = V.simulate(keep, M, P, {g: 250.0 for g in stim}, T=2.0, record=mn_loc)
            a, pk, sw = score(X)
            print(f'{label:20s} n={len(keep):6d} {sl:12s} {time.time()-t0:4.0f}s active {a}/{len(mn_loc)} peak {pk} Hz swinging {sw}', flush=True)
