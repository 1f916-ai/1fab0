import numpy as np, time, json, urllib.request, concurrent.futures as cf, os
import pyarrow.feather as f
from cloudvolume import CloudVolume
OUT = '/Users/dovi/fly-data/anatomy'
t0 = time.time()
cv = CloudVolume('precomputed://gs://flyem-male-cns/malecns-tbar-point-cloud-512nm-smoothed/', mip=1, use_https=True, progress=False, parallel=8, fill_missing=True)
vol = np.asarray(cv[:, :, :])[..., 0]; np.save(f'{OUT}/tbar_density_mip1.npy', vol.astype(np.float16))
print('mip1', vol.shape, f'{time.time()-t0:.0f}s', flush=True)
t = f.read_table('/Users/dovi/fly-data/malecns/body-annotations-male-cns-v1.0-minconf-0.5.feather', columns=['bodyId', 'type', 'status', 'superclass', 'subclass', 'somaSide']).to_pandas()
t = t[t.status == 'Traced']
feat = t[t.type.isin(['DNg100', 'DNa02', 'MDN', 'DNp01', 'TTMn', 'DNp09'])]
legs = t[(t.superclass == 'vnc_motor') & t.subclass.isin(['fl', 'ml', 'hl']) & (t.type.str.contains('Tr flexor|Sternotrochanter', na=False))]
want = pd_ids = list(feat.bodyId) + list(legs.bodyId)
os.makedirs(f'{OUT}/swc', exist_ok=True)
def get(b):
    p = f'{OUT}/swc/{b}.swc'
    if not os.path.exists(p):
        urllib.request.urlretrieve(f'https://storage.googleapis.com/flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-swc/{b}.swc', p)
    return b
with cf.ThreadPoolExecutor(16) as ex: done = list(ex.map(get, want))
meta = {int(r.bodyId): dict(type=r.type, subclass=r.subclass, side=r.somaSide) for r in t[t.bodyId.isin(want)].itertuples()}
json.dump(meta, open(f'{OUT}/swc/meta.json', 'w'))
print('skeletons', len(done), f'{time.time()-t0:.0f}s')
