import numpy as np, json, time
from cloudvolume import CloudVolume
OUT = '/Users/dovi/fly-data/anatomy'
def main():
    for name, url in [('vnc', 'precomputed://gs://flyem-male-cns/rois/malecns-vnc-neuropil-roi-v0'), ('brain', 'precomputed://gs://flyem-male-cns/rois/fullbrain-roi-v5')]:
        t0 = time.time()
        cv = CloudVolume(url, use_https=True, progress=False, parallel=1, fill_missing=True)
        mips = cv.available_mips; res = [cv.mip_resolution(m).tolist() for m in mips]
        m = max(i for i, r in zip(mips, res) if r[0] <= 2048)
        cv.mip = m
        vol = np.asarray(cv[:, :, :])[..., 0]
        props = cv.info.get('segment_properties')
        names = {}
        try:
            from cloudvolume.datasource.precomputed.metadata import PrecomputedMetadata
            import requests
            base = url.replace('precomputed://gs://', 'https://storage.googleapis.com/')
            sp = requests.get(f'{base}/{props}/info').json()
            ids = sp['inline']['ids']; vals = sp['inline']['properties'][0]['values']
            names = dict(zip(ids, vals))
        except Exception as e:
            print('props err', e)
        np.save(f'{OUT}/roi_{name}.npy', vol.astype(np.uint32)); json.dump(dict(mip=m, resolution=cv.resolution.tolist(), offset=cv.voxel_offset.tolist(), names=names), open(f'{OUT}/roi_{name}.json', 'w'))
        print(name, 'mip', m, cv.resolution, vol.shape, 'labels', len(np.unique(vol)), 'names', list(names.items())[:12], f'{time.time()-t0:.0f}s', flush=True)

if __name__ == '__main__':
    main()
