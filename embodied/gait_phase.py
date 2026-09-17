import sys, numpy as np; sys.path.insert(0, '/Users/dovi/fly-data/work')
import vnc_rate as V, malecns_cpg as C
dng = np.flatnonzero(V.TYP == 'DNg100')
keep = C.pathway_subset(['fl', 'ml', 'hl'], 2)
mn_loc = np.flatnonzero((V.SUP[keep] == 'vnc_motor') & np.isin(V.SUB[keep], ['fl', 'ml', 'hl']))
g = keep[mn_loc]
res = {}
for seed in range(4):
    M, P = C.build_from(keep, seed=seed)
    for stim, sl in [([dng[0]], 'L'), (list(dng), 'both')]:
        X = V.simulate(keep, M, P, {x: 250.0 for x in stim}, T=2.0, record=mn_loc)
        seg = X[500:1900]; Z = seg - seg.mean(0)
        F = np.fft.rfft(Z, axis=0); fr = np.fft.rfftfreq(len(Z), .001); b = (fr > 2) & (fr < 30)
        k = np.flatnonzero(b)[np.abs(F[b]).sum(1).argmax()]; f0 = fr[k]
        out = {}
        for leg in ('fl', 'ml', 'hl'):
            for side in ('L', 'R'):
                for group, words in (('flex', ('flexor',)), ('ext', ('extensor',)), ('pro', ('promotor',)), ('rem', ('remotor',))):
                    m = np.array([V.SUB[i] == leg and V.SIDE[i] == side and any(w in V.TYP[i] for w in words) for i in g])
                    if m.any() and np.abs(F[k, m]).sum() > 1e-6:
                        c = F[k, m].sum(); out[f'{leg}{side}_{group}'] = (np.angle(c, deg=True), np.abs(c) / m.sum())
        res[(seed, sl)] = (f0, out)
        amp = {kk: round(v[1]) for kk, v in out.items()}
        ph = {kk: round(v[0]) for kk, v in out.items() if kk.endswith('flex')}
        print(f'seed {seed} DNg100 {sl:4s} f0 {f0:.2f} Hz  flexor phase by leg {ph}')
        print(f'    amplitude {amp}', flush=True)
