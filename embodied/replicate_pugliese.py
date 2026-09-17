import sys, time, numpy as np, pandas as pd, torch
sys.path.insert(0, '/Users/dovi/fly-data/work')
dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
base = '/Users/dovi/fly-data/pugliese/data/manc t1 connectome data/'
W = pd.read_csv(base + 'W_20250813_DNtoMN_unsorted.csv').drop(columns='bodyId_pre').to_numpy().astype(np.float32)
tab = pd.read_csv(base + 'wTable_20250813_DNtoMN_unsorted_withModules.csv', index_col=0)
n = len(W); Wt = W.T
Wr = torch.tensor(0.03 * np.maximum(Wt, 0) + 0.03 * np.minimum(Wt, 0), device=dev)
mn = np.flatnonzero(tab['class'].fillna('').str.contains('motor').to_numpy())
print('neurons', n, 'MNs', len(mn), 'W nonzero', (W != 0).sum(), 'neg', (W < 0).sum())
def run(seed, T=2.0, dt=0.0005):
    rng = np.random.default_rng(seed)
    tau = torch.tensor(rng.normal(0.02, 0.002, n), dtype=torch.float32, device=dev); a = torch.tensor(rng.normal(1, .1, n), dtype=torch.float32, device=dev)
    th = torch.tensor(rng.normal(7.5, .6, n), dtype=torch.float32, device=dev); cap = torch.tensor(rng.normal(200, 10, n), dtype=torch.float32, device=dev)
    I = torch.zeros(n, device=dev); R = torch.zeros(n, device=dev); out = []
    for k in range(int(T / dt)):
        t = k * dt; I[31] = 250.0 if 0.02 <= t <= 1.999 else 0.0
        R = R + dt * (torch.clamp(cap * torch.tanh((a / cap) * (I + Wr @ R - th)), min=0) - R) / tau
        if k % 2 == 0: out.append(R[mn].cpu().numpy())
    return np.array(out)
for seed in range(3):
    t0 = time.time(); X = run(seed); seg = X[500:1900]; act = seg.max(0) > 5
    Z = seg[:, act] - seg[:, act].mean(0); F = np.abs(np.fft.rfft(Z, axis=0)); fr = np.fft.rfftfreq(len(Z), 0.001); b = (fr > 3) & (fr < 30)
    peak = fr[b][F[b].sum(1).argmax()] if act.any() else None
    amp = (seg[:, act].max(0) - seg[:, act].min(0)) if act.any() else np.array([0])
    print(f'seed {seed}: {time.time()-t0:.0f}s active MNs {act.sum()}/{len(mn)} peak {peak:.1f} Hz  median peak-to-trough {np.median(amp):.0f} Hz  MNs swinging >20Hz {(amp>20).sum()}')
    np.save(f'/Users/dovi/fly-data/work/pug_t1_seed{seed}.npy', X)
