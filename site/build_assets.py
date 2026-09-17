"""Web assets: neuron skeleton line segments (cloud frame) and fly meshes (from a MuJoCo export)."""
import numpy as np, json, glob, os, sys
S = '/Users/dovi/fly-data/site/data'; A = '/Users/dovi/fly-data/anatomy'
meta = json.load(open(f'{S}/cloud_meta.json')); centre = np.array(meta['centre_um']); scale = meta['scale_per_um']
swmeta = json.load(open(f'{A}/swc/meta.json'))

def load_swc(p):
    a = np.loadtxt(p, comments='#')
    if a.ndim == 1: a = a[None]
    return a

def simplify(a, min_um=4.0):
    ids = a[:, 0].astype(int); par = a[:, 6].astype(int); xyz = a[:, 2:5] * 0.008   # 8 nm voxels -> um
    idx = {n: i for i, n in enumerate(ids)}
    children = {}
    for i, p in enumerate(par): children.setdefault(p, []).append(i)
    keep_seg = []
    # walk from roots, emit segment when accumulated length exceeds min_um or at branch/leaf
    stack = [(i, i, 0.0) for i, p in enumerate(par) if p not in idx]
    while stack:
        i, anchor, acc = stack.pop()
        ch = children.get(ids[i], [])
        for c in ch:
            d = acc + np.linalg.norm(xyz[c] - xyz[i])
            if d >= min_um or len(children.get(ids[c], [])) != 1:
                keep_seg.append((anchor, c)); stack.append((c, c, 0.0))
            else:
                stack.append((c, anchor, d))
    seg = np.array(keep_seg) if keep_seg else np.zeros((0, 2), int)
    pts = ((xyz - centre) * scale).astype(np.float32)
    return pts[seg[:, 0]], pts[seg[:, 1]]

groups = {}
for p in sorted(glob.glob(f'{A}/swc/*.swc')):
    b = os.path.basename(p)[:-4]; m = swmeta.get(b)
    if not m: continue
    t = m['type']
    g = 'leg_mn' if ('Tr flexor' in t or 'Sternotrochanter' in t) else t
    a0, a1 = simplify(load_swc(p))
    groups.setdefault(g, []).append((b, m, a0, a1))
out_pos = []; index = []; off = 0
for g, items in groups.items():
    for b, m, a0, a1 in items:
        seg = np.stack([a0, a1], 1).reshape(-1, 3); out_pos.append(seg)
        index.append(dict(group=g, bodyId=int(b), type=m['type'], subclass=m.get('subclass'), side=m.get('side'), offset=off, count=len(seg)))
        off += len(seg)
np.concatenate(out_pos).astype(np.float32).tofile(f'{S}/skeletons.bin')
json.dump(index, open(f'{S}/skeletons.json', 'w'))
print('skeleton vertices', off, {g: len(v) for g, v in groups.items()})

if len(sys.argv) > 1:
    d = np.load(sys.argv[1])
    names = [str(x) for x in d['names']]; vb = []; fb = []; mi = []; vo = fo = 0
    for i, n in enumerate(names):
        v = d[f'v{i}'].astype(np.float32); f = d[f'f{i}'].astype(np.uint32)
        vb.append(v); fb.append(f); mi.append(dict(name=n, voff=vo, vcount=len(v), foff=fo, fcount=len(f))); vo += len(v); fo += len(f)
    np.concatenate(vb).tofile(f'{S}/fly_verts.bin'); np.concatenate(fb).tofile(f'{S}/fly_faces.bin')
    json.dump(mi, open(f'{S}/fly_meshes.json', 'w'))
    print('fly meshes', len(names), 'verts', vo, 'faces', fo)
