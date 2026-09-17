"""Pugliese et al. 2025 rate model (MIT code, re-implemented in torch) on the MaleCNS v1.0 nerve cord.
dR/dt = (max(0, frcap*tanh(a/frcap*(I + W R - theta))) - R)/tau, exc/inh multipliers 0.03, per-neuron draws."""
import os, math, numpy as np, torch, scipy.sparse as sp, pyarrow.feather as f, pyarrow.compute as pc
DER = os.environ.get('FLY_DERIVED', os.path.expanduser('~/fly-data/derived')); DATA = os.environ.get('FLY_DATA', os.path.expanduser('~/fly-data/malecns'))
dev = 'mps' if torch.backends.mps.is_available() else 'cpu'

ids = np.load(f'{DER}/G_traced_bodyIds.npy'); sign = np.load(f'{DER}/G_traced_presyn_sign.npy')
A = sp.load_npz(f'{DER}/G_traced_post_by_pre.npz').tocsr()
ann = f.read_table(f'{DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId','status','type','superclass','subclass','somaSide','somaNeuromere','rootSide'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(ids)
SUP = ann['superclass'].fillna('').to_numpy(); TYP = ann['type'].fillna('').to_numpy(); SUB = ann['subclass'].fillna('').to_numpy()
SIDE = ann['somaSide'].fillna('').to_numpy(); ROOT = ann['rootSide'].fillna('').to_numpy()

def build(superclasses=('descending_neuron', 'vnc_intrinsic', 'vnc_motor', 'ascending_neuron', 'vnc_efferent'), exc=0.03, inh=0.03, seed=0, scales=None):
    keep = np.flatnonzero(np.isin(SUP, superclasses))
    sub = A[keep][:, keep].tocoo()
    s = sign[keep][sub.col]
    w = sub.data * np.where(s > 0, exc, np.where(s < 0, -inh, 0.0))
    if scales is not None: w = w * scales(keep, sub)
    M = torch.sparse_coo_tensor(torch.tensor(np.vstack([sub.row, sub.col]), dtype=torch.int64), torch.tensor(w, dtype=torch.float32), (len(keep), len(keep))).coalesce()
    rng = np.random.default_rng(seed); n = len(keep)
    P = dict(tau=np.clip(rng.normal(0.02, 0.002, n), 0.005, None), a=rng.normal(1, 0.1, n), theta=rng.normal(7.5, 0.6, n), cap=rng.normal(200, 10, n))
    P = {k: torch.tensor(v, dtype=torch.float32, device=dev) for k, v in P.items()}
    return keep, M.to(dev), P

def simulate(keep, W, P, stim, T=2.0, dt=0.0005, record=None, step_cb=None):
    """stim: dict global-index -> current (or callable t->current). record: local indices to return (every 1 ms)."""
    n = len(keep); loc = {g: i for i, g in enumerate(keep)}
    R = torch.zeros(n, device=dev); I = torch.zeros(n, device=dev)
    rec = record if record is not None else np.arange(n)
    rec_t = torch.tensor(rec, device=dev); out = []
    steps = int(T / dt); every = int(round(0.001 / dt))
    for k in range(steps):
        t = k * dt
        I.zero_()
        for g, c in stim.items():
            I[loc[g]] = c(t) if callable(c) else (c if t >= 0.02 else 0.0)
        if step_cb is not None: step_cb(t, I, loc)
        x = I + torch.sparse.mm(W, R[:, None])[:, 0] - P['theta']
        act = torch.clamp(P['cap'] * torch.tanh((P['a'] / P['cap']) * x), min=0)
        R = R + dt * (act - R) / P['tau']
        if k % every == 0: out.append(R[rec_t].cpu().numpy())
    return np.array(out)
