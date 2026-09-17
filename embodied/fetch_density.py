import numpy as np, time
from cloudvolume import CloudVolume
cv = CloudVolume('precomputed://gs://flyem-male-cns/malecns-tbar-point-cloud-512nm-smoothed/', mip=2, use_https=True, progress=False, parallel=8, fill_missing=True)
print('mip2 shape', cv.shape, 'res', cv.resolution, 'offset', cv.voxel_offset, flush=True)
t0 = time.time(); vol = np.asarray(cv[:, :, :])[..., 0]
print('downloaded', vol.shape, vol.dtype, 'min', vol.min(), 'max', vol.max(), 'nonzero', (vol > 0).mean(), f'{time.time()-t0:.0f}s', flush=True)
np.save('/Users/dovi/fly-data/anatomy/tbar_density_mip2.npy', vol)
np.save('/Users/dovi/fly-data/anatomy/tbar_density_mip2_meta.npy', np.array([*cv.resolution, *cv.voxel_offset], dtype=np.float64))
