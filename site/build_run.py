"""Bundle one run for the web: motion frames + gait + leg activity + stats."""
import numpy as np, json, sys, os
sys.path.insert(0, '/Users/dovi/fly-data/work')
S = '/Users/dovi/fly-data/site/data/runs'
run_id, neural, motion, body_json = sys.argv[1:5]
n = np.load(neural); m = np.load(motion); b = json.load(open(body_json))
from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
LEGS = ['lf', 'lm', 'lh', 'rf', 'rm', 'rh']
steps = PreprogrammedSteps()
swing_end = np.array([steps.swing_period[l][1] for l in LEGS])
mid = swing_end / 2
ph = (n['phase'] + mid[None, :]) % (2 * np.pi); mag = n['mag']
frames = m['frames']; every = max(1, int(round(1000 / 60))); fps = 1000.0 / every
T = len(frames)
fi = np.arange(T) * every
swing = ((ph[fi] < swing_end[None, :]) & (mag[fi] > 0.15)).astype(np.uint8)          # T x 6
sig = n['sig'][fi]; act = np.clip(sig / (np.percentile(np.abs(n['sig'][500:]), 95, axis=0) + 1e-6), 0, 1)
# measured stats from the command window (after 0.5 s)
w0 = int(0.5 * 1000)
from scipy.signal import welch
f, P = welch(n['sig'][w0:] - n['sig'][w0:].mean(0), fs=1000, nperseg=1024, axis=0)
band = (f > 2) & (f < 25); fstep = float(f[band][P[band].sum(1).argmax()])
a_ph = n['phase'][w0:]; tri_pairs = []
grpA = [0, 2, 4]; grpB = [1, 3, 5]   # lf, lh, rm  vs lm, rf, rh
for p in range(6):
    for q in range(p + 1, 6):
        same = (p in grpA) == (q in grpA)
        d = np.angle(np.mean(np.exp(1j * (a_ph[:, p] - a_ph[:, q]))))
        tri_pairs.append(np.cos(d - (0 if same else np.pi)))
stats = dict(speed_mm_s=round(b['speed_mm_s'], 2), heading_change_deg=round(b['heading_change_deg'], 1), step_hz=round(fstep, 2),
             tripod_index=round(float(np.mean(tri_pairs)), 3), mean_step_strength=round(float(mag[w0:].mean()), 3))
thorax_names = [i for i, x in enumerate(m['names']) if str(x).endswith('c_thorax')]
path = frames[:, thorax_names[0], :3]
frames.astype(np.float32).tofile(f'{S}/{run_id}_motion.bin')
json.dump(dict(id=run_id, frames=T, fps=fps, geoms=int(frames.shape[1]), swing=swing.tolist(), leg_activity=np.round(act, 2).tolist(),
               path=np.round(path, 3).tolist(), stats=stats, model=str(n['model']), seed=int(n['seed'])), open(f'{S}/{run_id}.json', 'w'))
print(run_id, stats)
