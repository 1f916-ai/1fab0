"""Sample a synapse point cloud from the MaleCNS T-bar density (1 um), label points by neuropil ROI."""
import numpy as np, json
OUT = '/Users/dovi/fly-data/site/data'; A = '/Users/dovi/fly-data/anatomy'
rng = np.random.default_rng(7)
d = np.load(f'{A}/tbar_density_mip1.npy').astype(np.float32)            # (x, y, z) voxels of 1024 nm
w = np.clip(d, 0, None) ** 2.0; w[d < 0.03] = 0
zz = np.arange(d.shape[2])[None, None, :]
N_BRAIN, N_VNC = 270000, 190000; N = N_BRAIN + N_VNC
parts = []
for mask_fn, count in ((lambda: zz < 406, N_BRAIN), (lambda: zz >= 406, N_VNC)):   # z=203 at 2048 nm = 406 at 1024 nm
    wm = np.where(np.broadcast_to(mask_fn(), d.shape), w, 0).ravel(); pm = wm / wm.sum()
    parts.append(rng.choice(wm.size, size=count, replace=True, p=pm))
idx = np.concatenate(parts)
xyz = np.array(np.unravel_index(idx, d.shape)).T.astype(np.float32)
xyz += rng.random(xyz.shape, dtype=np.float32)                          # jitter within voxel
um = xyz * 1.024                                                         # micrometres
# ROI labels from 2048 nm grids
vnc = np.load(f'{A}/roi_vnc.npy'); brain = np.load(f'{A}/roi_brain.npy')
vj = json.load(open(f'{A}/roi_vnc.json')); bj = json.load(open(f'{A}/roi_brain.json'))
g = (xyz // 2).astype(int)
def lab(vol):
    gi = np.minimum(g, np.array(vol.shape) - 1); return vol[gi[:, 0], gi[:, 1], gi[:, 2]]
lv = lab(vnc); lb = lab(brain)
names = ['none']; code = {}
def cid(nm):
    if nm not in code: code[nm] = len(names); names.append(nm)
    return code[nm]
roi = np.zeros(N, np.uint8)
for u in np.unique(lv[lv > 0]): roi[lv == u] = cid('VNC:' + vj['names'].get(str(int(u)), str(int(u))))
for u in np.unique(lb[(lb > 0) & (roi == 0)]): roi[(lb == u) & (roi == 0)] = cid('BR:' + bj['names'].get(str(int(u)), str(int(u))))
centre = np.array([(16 + 361) / 2, (19 + 269) / 2, (39 + 523) / 2]) * 2.048
scale = 1.0 / (((523 - 39) * 2.048) / 2)
pos = ((um - centre) * scale).astype(np.float32)
order = np.argsort(roi, kind='stable')
pos[order].tofile(f'{OUT}/cloud_pos.bin'); roi[order].tofile(f'{OUT}/cloud_roi.bin')
dens = (d[np.minimum(xyz[:, 0].astype(int), d.shape[0] - 1), np.minimum(xyz[:, 1].astype(int), d.shape[1] - 1), np.minimum(xyz[:, 2].astype(int), d.shape[2] - 1)])
(np.clip(dens / np.percentile(dens, 99), 0, 1) * 255).astype(np.uint8)[order].tofile(f'{OUT}/cloud_density.bin')
json.dump(dict(count=N, roi_names=names, centre_um=centre.tolist(), scale_per_um=scale, source='MaleCNS v1.0 T-bar point cloud (512 nm smoothed), sampled at 1 um, CC BY 4.0'), open(f'{OUT}/cloud_meta.json', 'w'))
print('points', N, 'labelled', (roi > 0).mean().round(3), 'rois', len(names), 'pos range', pos.min(0), pos.max(0))
