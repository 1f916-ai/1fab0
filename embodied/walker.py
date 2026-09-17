"""Drive NeuroMechFly legs from per-leg stepping phases.
Step SHAPE: single-leg steps recorded from real walking flies (flygym_demo PreprogrammedSteps).
Step TIMING and inter-leg COORDINATION: whatever phases are passed in (from the connectome, or a reference)."""
import numpy as np
from flygym import Simulation
from flygym.compose.world.flat_ground import FlatGroundWorld
from flygym.utils.math import Rotation3D
from flygym_demo.complex_terrain.common import make_locomotion_fly, get_default_locomotion_dof_order, dof_spec_to_jointdof, LocomotionAction, apply_locomotion_action
from flygym_demo.complex_terrain.preprogrammed import PreprogrammedSteps

LEGS = ['lf', 'lm', 'lh', 'rf', 'rm', 'rh']

def run(phases, mags, dt_ctrl=0.001, video=None, colorize=True, return_yaw=False, export=None, export_fps=60):
    """phases, mags: (T, 6) arrays in LEGS order, sampled every dt_ctrl seconds. Returns thorax xy trajectory."""
    fly = make_locomotion_fly(colorize=colorize)
    cam = fly.add_tracking_camera() if video else None
    world = FlatGroundWorld()
    world.add_fly(fly, np.array([0, 0, 0.7]), Rotation3D('quat', [1, 0, 0, 0]))
    sim = Simulation(world)
    if video: sim.set_renderer(cam, camera_res=(360, 480), playback_speed=0.25, output_fps=30)
    steps = PreprogrammedSteps(); order = get_default_locomotion_dof_order()
    sim.warmup()
    sub = int(round(dt_ctrl / sim.timestep)); traj = []
    root = None; yaws = []
    import mujoco as mj
    m, dd = sim.mj_model, sim.mj_data
    mesh_geoms = [g for g in range(m.ngeom) if m.geom_type[g] == mj.mjtGeom.mjGEOM_MESH]
    frames = []; q4 = np.zeros(4); every = max(1, int(round(1.0 / export_fps / dt_ctrl)))
    for t in range(len(phases)):
        by_dof = {}; adh = []
        for j, leg in enumerate(LEGS):
            ang = steps.get_joint_angles(leg, phases[t, j], mags[t, j])
            for k, spec in enumerate(steps.dofs_per_leg): by_dof[dof_spec_to_jointdof(leg, spec)] = ang[k]
            adh.append(steps.get_adhesion_onoff(leg, phases[t, j]) if mags[t, j] > 0.05 else True)
        apply_locomotion_action(sim, fly.name, LocomotionAction(np.array([by_dof[d] for d in order]), np.array(adh)))
        for _ in range(sub):
            sim.step()
            if video: sim.render_as_needed()
        if export and t % every == 0:
            fr = []
            for g in mesh_geoms:
                mj.mju_mat2Quat(q4, dd.geom_xmat[g]); fr.append(np.concatenate([dd.geom_xpos[g], q4]))
            frames.append(np.array(fr, dtype=np.float32))
        pos = sim.get_body_positions(fly.name)[0]
        traj.append(pos[:2].copy())
        q = sim.get_body_rotations(fly.name)[0]
        yaws.append(np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] ** 2 + q[3] ** 2)))
    if video: sim.renderer.save_video(video)
    if export:
        meshes = []
        for g in mesh_geoms:
            mid = m.geom_dataid[g]; va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]; fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
            meshes.append(dict(name=mj.mj_id2name(m, mj.mjtObj.mjOBJ_GEOM, g) or f'g{g}', mesh=mj.mj_id2name(m, mj.mjtObj.mjOBJ_MESH, mid), rgba=m.geom_rgba[g].tolist(),
                               verts=m.mesh_vert[va:va + vn].astype(np.float32), faces=m.mesh_face[fa:fa + fn].astype(np.uint32)))
        np.savez_compressed(export, frames=np.array(frames), fps=export_fps, names=np.array([x['name'] for x in meshes]), meshnames=np.array([x['mesh'] for x in meshes]),
                            rgba=np.array([x['rgba'] for x in meshes]), **{f'v{i}': x['verts'] for i, x in enumerate(meshes)}, **{f'f{i}': x['faces'] for i, x in enumerate(meshes)})
    if return_yaw: return np.array(traj), np.unwrap(np.array(yaws))
    return np.array(traj)

def tripod_reference(T_s=1.0, f=12.0, dt=0.001):
    t = np.arange(int(T_s / dt)) * dt
    offs = np.array([0, np.pi, 0, np.pi, 0, np.pi])   # lf, lm, lh | rf, rm, rh : tripod A = lf, rm, lh
    offs = np.array([0, np.pi, 0, np.pi, 0, np.pi])
    offs[3], offs[4] = np.pi, 0   # rf antiphase to lf, rm in phase with lf
    ph = (2 * np.pi * f * t[:, None] + offs[None, :]) % (2 * np.pi)
    return ph, np.ones_like(ph)
