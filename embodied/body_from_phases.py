import sys, os, numpy as np, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import walker as Wk
from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps
src, video = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
d = np.load(src)
steps = PreprogrammedSteps()
mid_swing = np.array([steps.swing_period[l][1] / 2 for l in Wk.LEGS])
ph = (d['phase'] + mid_swing[None, :]) % (2 * np.pi)   # flexor peak -> mid-swing
traj, yaw = Wk.run(ph, d['mag'], video=video, return_yaw=True, export=src.replace('.npz', '_motion.npz'))
dxy = traj[-1] - traj[int(0.5 / 0.001)]
out = dict(src=src, speed_mm_s=float(np.linalg.norm(dxy) / ((len(traj) - 500) * 0.001)), displacement=dxy.tolist(), heading_change_deg=float(np.degrees(yaw[-1] - yaw[500])))
print(json.dumps(out)); json.dump(out, open(src.replace('.npz', '_body.json'), 'w'))
