"""Shared network + fitness for evaluation. Mirrors evolve.py exactly (same subset, grouping, shuffle seed, fitness)."""
import sys, os, math, json
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vnc_rate as V, malecns_cpg as C
import pyarrow.feather as f, pyarrow.compute as pc
dev = V.dev
ann = f.read_table(f'{V.DATA}/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId', 'status', 'trumanHl'])
ann = ann.filter(pc.equal(ann.column('status'), 'Traced')).to_pandas().set_index('bodyId').reindex(V.ids)
HL = ann['trumanHl'].fillna('').to_numpy()
KEEP = C.pathway_subset(['fl', 'ml', 'hl'], 2)
LEGS = [('fl', 'L'), ('ml', 'R'), ('hl', 'L'), ('fl', 'R'), ('ml', 'L'), ('hl', 'R')]

class Net:
    def __init__(self, null='real'):
        keep = KEEP; n = len(keep); self.keep, self.n = keep, n
        sub = V.A[keep][:, keep].tocoo(); row, col, val = sub.row, sub.col, sub.data
        if null == 'shuffled':
            rng = np.random.default_rng(12345); row = row[rng.permutation(len(row))]
        s = V.sign[keep][col]
        def sp(mask):
            return torch.sparse_coo_tensor(torch.tensor(np.vstack([row[mask], col[mask]]), dtype=torch.int64), torch.tensor(val[mask] * np.abs(s[mask]), dtype=torch.float32), (n, n)).coalesce().to(dev)
        self.W_exc, self.W_inh = sp(s > 0), sp(s < 0)
        sup = V.SUP[keep]; hl = HL[keep]; self.sup = sup
        self.groups = ['DN', 'MN'] + sorted(set(hl[(sup == 'vnc_intrinsic') & (hl != '')]))
        gid = np.full(n, -1); gid[sup == 'descending_neuron'] = 0; gid[sup == 'vnc_motor'] = 1
        for i, g in enumerate(self.groups[2:], start=2): gid[(sup == 'vnc_intrinsic') & (hl == g)] = i
        self.NG = len(self.groups); self.gid_t = torch.tensor(np.where(gid < 0, self.NG, gid), device=dev)
        def pool(leg, side, word):
            return np.flatnonzero((sup == 'vnc_motor') & (V.SUB[keep] == leg) & (V.SIDE[keep] == side) & np.array([word in t for t in V.TYP[keep]]))
        self.FLEX = [pool(l, s_, 'Tr flexor') for l, s_ in LEGS]; self.EXT = [pool(l, s_, 'Sternotrochanter') for l, s_ in LEGS]
        self.rec_ix = torch.tensor(np.concatenate(self.FLEX + self.EXT), device=dev)
        self.local = {g: i for i, g in enumerate(keep)}

    def params(self, seed, B):
        rng = np.random.default_rng(seed); n = self.n
        d = dict(tau=np.clip(rng.normal(.02, .002, n), .005, None), a=rng.normal(1, .1, n), theta=rng.normal(7.5, .6, n), cap=rng.normal(200, 10, n))
        return {k: torch.tensor(v, dtype=torch.float32, device=dev)[:, None].expand(n, B) for k, v in d.items()}

    def run(self, X, seed, stims, stim_I=250.0, T=1.2, dt=0.0005, record_all=False):
        """X: B x NP; stims: list (len B) of global-index arrays."""
        B = X.shape[0]; NG = self.NG
        g = torch.exp(torch.tensor(X[:, :NG], dtype=torch.float32, device=dev)); g = torch.cat([g, torch.ones(B, 1, device=dev)], 1)
        G = g[:, self.gid_t].T.contiguous()
        e = 0.03 * torch.exp(torch.tensor(X[:, NG], dtype=torch.float32, device=dev)); i_ = 0.03 * torch.exp(torch.tensor(X[:, NG + 1], dtype=torch.float32, device=dev))
        P = self.params(seed, B); R = torch.zeros(self.n, B, device=dev); I = torch.zeros(self.n, B, device=dev)
        for b, st in enumerate(stims):
            for gi in st:
                if gi in self.local: I[self.local[gi], b] = stim_I
        out = []; sat = torch.zeros(B, device=dev); steps = int(T / dt)
        for k in range(steps):
            GR = G * R
            x = (I if k * dt >= 0.02 else 0) + torch.sparse.mm(self.W_exc, GR) * e - torch.sparse.mm(self.W_inh, GR) * i_ - P['theta']
            R = R + dt * (torch.clamp(P['cap'] * torch.tanh((P['a'] / P['cap']) * x), min=0) - R) / P['tau']
            if k % 2 == 0:
                out.append(R[self.rec_ix])
                if k * dt > 0.3: sat += (R > 180).float().mean(0)
        return torch.stack(out).cpu().numpy(), (sat / (steps / 2)).cpu().numpy()

    def legs(self, Y, b, t0=400):
        seg = Y[t0:, :, b]; nf = [len(x) for x in self.FLEX]; ne = [len(x) for x in self.EXT]; offs = np.cumsum([0] + nf + ne)
        flex = np.array([seg[:, offs[j]:offs[j + 1]].mean(1) if nf[j] else np.zeros(len(seg)) for j in range(6)])
        ext = np.array([seg[:, offs[6 + j]:offs[7 + j]].mean(1) if ne[j] else np.zeros(len(seg)) for j in range(6)])
        return flex, ext

    def fitness(self, Y, sat):
        B = Y.shape[2]; scores = np.zeros(B); comps = []
        for b in range(B):
            flex, ext = self.legs(Y, b); L = flex.shape[1]
            sig = flex - ext; sig = sig - sig.mean(1, keepdims=True); amp = sig.max(1) - sig.min(1)
            F = np.fft.rfft(sig, axis=1); P_ = np.abs(F) ** 2; tot = P_[:, 1:].sum() + 1e-9
            fr = np.fft.rfftfreq(L, .001); band = (fr >= 5) & (fr <= 15)
            k = np.flatnonzero(band)[P_[:, band].sum(0).argmax()]; rhythm = P_[:, band].sum() / tot
            ph = np.angle(F[:, k]); phf = np.angle(np.fft.rfft(flex - flex.mean(1, keepdims=True), axis=1)[:, k]); phe = np.angle(np.fft.rfft(ext - ext.mean(1, keepdims=True), axis=1)[:, k])
            grp = [0, 0, 0, 1, 1, 1]
            tri = [math.cos(ph[p] - ph[q] - (0.0 if grp[p] == grp[q] else math.pi)) for p in range(6) for q in range(p + 1, 6)]
            tripod = float(np.mean(tri)); alt = float(np.mean(np.cos(phf - phe - math.pi))); moving = float(np.mean(np.clip(amp / 20.0, 0, 1)))
            scores[b] = moving * (0.45 * tripod + 0.2 * alt + 0.35 * rhythm) - 2.0 * float(sat[b])
            comps.append(dict(tripod=tripod, alternation=alt, rhythm=float(rhythm), moving=moving, freq=float(fr[k]), sat=float(sat[b]), amp=amp.tolist()))
        return scores, comps
