"""Run a model (published or evolved gains) and extract per-leg stepping phase + magnitude from motor neuron pools.
Swing proxy: Tr flexor MNs; stance proxy: Sternotrochanter MNs. Phase from the analytic signal of (flexor - extensor)."""
import sys, os, json, argparse
import numpy as np
from scipy.signal import butter, filtfilt, hilbert
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evo_core as E, vnc_rate as V
ap = argparse.ArgumentParser(); ap.add_argument('--model', required=True); ap.add_argument('--seed', type=int, default=100)
ap.add_argument('--T', type=float, default=3.0); ap.add_argument('--stim', default='DNg100'); ap.add_argument('--side', default='')
ap.add_argument('--extra', default=''); ap.add_argument('--out', required=True)
a = ap.parse_args()
STAGE = os.environ.get('STAGE', '')
best = {'evolved_real': ('real', f'evo_real{STAGE}'), 'evolved_scrambled': ('shuffled', f'evo_shuffled{STAGE}'), 'published_params': ('real', None), 'published_params_scrambled': ('shuffled', None)}[a.model]
net = E.Net(best[0]); x = np.array(json.load(open(os.path.expanduser(f'~/fly-data/work/{best[1]}/best.json')))['x']) if best[1] else np.zeros(net.NG + 2)
def cells(t, side=''):
    ix = np.flatnonzero(V.TYP == t)
    if side: ix = [i for i in ix if V.ROOT[i] == ('LHS' if side == 'L' else 'RHS') or V.SIDE[i] == side]
    return [i for i in ix if i in net.local]
stim = cells(a.stim, a.side) + (cells(a.extra) if a.extra else [])
Y, sat = net.run(x[None, :], a.seed, [stim], T=a.T)
flex, ext = net.legs(Y, 0, t0=0)                        # E.LEGS order: flL, mlR, hlL, flR, mlL, hlR
order = {'lf': 0, 'lm': 4, 'lh': 2, 'rf': 3, 'rm': 1, 'rh': 5}   # -> walker order lf, lm, lh, rf, rm, rh
sig = np.array([flex[order[l]] - ext[order[l]] for l in ['lf', 'lm', 'lh', 'rf', 'rm', 'rh']])
b, a_ = butter(2, [2 / 500, 20 / 500], btype='band'); f = filtfilt(b, a_, sig, axis=1)
an = hilbert(f, axis=1); env = np.abs(an); ph = np.angle(an)
ref = np.percentile(env[:, 400:], 90) + 1e-6
mag = np.clip(env / ref, 0, 1)
mag[:, :150] = 0   # no stepping before the command arrives (filter edge)
np.savez(a.out, phase=ph.T, mag=mag.T, sig=sig.T, sat=sat, stim=np.array(stim), model=a.model, seed=a.seed)
print(a.model, 'stim', a.stim, a.side, len(stim), 'saved', a.out, 'mean mag', mag[:, 400:].mean(1).round(2))
