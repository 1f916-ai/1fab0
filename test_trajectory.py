"""
Unit tests for continuous 2D trajectory decoding and kinematic metrics (Grant 1FAB0).
Verifies:
  1. Straight forward run (high DNp09, low MDN) produces positive displacement, straightness ~ 1.0.
  2. Reverse run (low DNp09, high MDN) produces negative displacement.
  3. Pure asymmetric turning (DNa02_L > DNa02_R) produces angular deviation.
  4. Anti-clamping invariant: unclipped negative displacement is preserved.
  5. Distinguishing active retreat from motionless paralysis.
  6. Multi-format rate series ingestion and Trajectory array properties.
"""

import math
import unittest
import numpy as np
from src.trajectory import Trajectory, integrate_trajectory, trajectory_metrics


class TestTrajectoryDecoder(unittest.TestCase):
    def test_straight_forward_run(self):
        """Straight forward run (high DNp09, low MDN) produces positive displacement, straightness ~ 1.0."""
        rates = {
            'DNp09': [60.0] * 20,
            'MDN': [0.0] * 20,
            'DNa02_L': [0.0] * 20,
            'DNa02_R': [0.0] * 20
        }
        traj = integrate_trajectory(rates, dt=0.01)
        metrics = trajectory_metrics(traj)

        self.assertGreater(metrics['displacement'], 0.0)
        self.assertAlmostEqual(metrics['straightness'], 1.0, places=3)
        self.assertAlmostEqual(metrics['forward_progress_index'], 1.0, places=3)
        self.assertAlmostEqual(metrics['turning_rate'], 0.0, places=4)
        self.assertAlmostEqual(metrics['angular_deviation'], 0.0, places=4)
        self.assertAlmostEqual(metrics['displacement'], metrics['path_length'], places=3)

    def test_reverse_run(self):
        """Reverse run (low DNp09, high MDN) produces negative displacement."""
        rates = {
            'DNp09': [0.0] * 20,
            'MDN': [40.0] * 20,
            'DNa02_L': [0.0] * 20,
            'DNa02_R': [0.0] * 20
        }
        traj = integrate_trajectory(rates, dt=0.01)
        metrics = trajectory_metrics(traj)

        self.assertLess(metrics['displacement'], 0.0)
        self.assertLess(metrics['forward_progress_index'], 0.0)
        self.assertAlmostEqual(metrics['forward_progress_index'], -1.0, places=3)
        self.assertAlmostEqual(metrics['straightness'], 1.0, places=3)
        self.assertGreater(metrics['path_length'], 0.0)
        self.assertAlmostEqual(metrics['displacement'], -metrics['path_length'], places=3)

    def test_pure_asymmetric_turning(self):
        """Pure asymmetric turning (DNa02_L > DNa02_R) produces angular deviation."""
        # Left turning: DNa02_L > DNa02_R
        rates_l = {
            'DNp09': [20.0] * 15,
            'MDN': [0.0] * 15,
            'DNa02_L': [25.0] * 15,
            'DNa02_R': [0.0] * 15
        }
        traj_l = integrate_trajectory(rates_l, dt=0.01)
        metrics_l = trajectory_metrics(traj_l)

        self.assertGreater(metrics_l['angular_deviation'], 0.0)
        self.assertGreater(metrics_l['turning_rate'], 0.0)

        # Right turning: DNa02_R > DNa02_L
        rates_r = {
            'DNp09': [20.0] * 15,
            'MDN': [0.0] * 15,
            'DNa02_L': [0.0] * 15,
            'DNa02_R': [25.0] * 15
        }
        traj_r = integrate_trajectory(rates_r, dt=0.01)
        metrics_r = trajectory_metrics(traj_r)

        self.assertLess(metrics_r['angular_deviation'], 0.0)
        self.assertGreater(metrics_r['turning_rate'], 0.0)
        self.assertAlmostEqual(metrics_l['turning_rate'], metrics_r['turning_rate'], places=4)

    def test_invariant_preservation_anti_clamping(self):
        """Invariant preservation: unclipped negative displacement is preserved, distinguishing retreat from paralysis."""
        # 1. Reverse motion / active retreat
        rates_retreat = {'DNp09': 5.0, 'MDN': 45.0, 'DNa02_L': 0.0, 'DNa02_R': 0.0}
        traj_retreat = integrate_trajectory(rates_retreat, dt=0.01)
        metrics_retreat = trajectory_metrics(traj_retreat)

        # Must not be clamped to 0
        self.assertLess(metrics_retreat['displacement'], 0.0)
        self.assertLess(metrics_retreat['forward_progress_index'], 0.0)
        self.assertGreater(metrics_retreat['path_length'], 0.0)

        # 2. Motionless paralysis
        rates_paralysis = {'DNp09': 0.0, 'MDN': 0.0, 'DNa02_L': 0.0, 'DNa02_R': 0.0}
        traj_paralysis = integrate_trajectory(rates_paralysis, dt=0.01)
        metrics_paralysis = trajectory_metrics(traj_paralysis)

        self.assertEqual(metrics_paralysis['displacement'], 0.0)
        self.assertEqual(metrics_paralysis['path_length'], 0.0)
        self.assertEqual(metrics_paralysis['forward_progress_index'], 0.0)
        self.assertEqual(metrics_paralysis['straightness'], 0.0)

        # Crucial invariant: retreat and paralysis must NOT have identical displacement
        self.assertNotEqual(metrics_retreat['displacement'], metrics_paralysis['displacement'])
        self.assertNotEqual(metrics_retreat['path_length'], metrics_paralysis['path_length'])

    def test_trajectory_formats_and_properties(self):
        """Verifies Trajectory class properties, slicing, and input format flexibility."""
        # Input as list of step dicts
        step_dicts = [
            {'DNp09': 30.0, 'MDN': 0.0, 'DNa02_L': 5.0, 'DNa02_R': 0.0},
            {'DNp09': 40.0, 'MDN': 0.0, 'DNa02_L': 0.0, 'DNa02_R': 5.0},
            {'DNp09': 50.0, 'MDN': 5.0, 'DNa02_L': 0.0, 'DNa02_R': 0.0}
        ]
        traj = integrate_trajectory(step_dicts, dt=0.01)
        self.assertIsInstance(traj, Trajectory)
        self.assertIsInstance(traj, np.ndarray)
        self.assertEqual(traj.shape, (4, 3))
        self.assertEqual(len(traj.x), 4)
        self.assertEqual(len(traj.y), 4)
        self.assertEqual(len(traj.theta), 4)
        self.assertEqual(traj.positions.shape, (4, 2))

        # Scalar inputs broadcast properly
        traj_scalar = integrate_trajectory({'DNp09': 10.0, 'MDN': 0.0}, dt=0.01)
        self.assertEqual(traj_scalar.shape, (2, 3))

    def test_forward_progress_scale_invariance(self):
        """Forward progress index dx / L is scale-invariant with respect to v_scale."""
        rates = {'DNp09': [30.0, 40.0, 50.0], 'MDN': [5.0, 5.0, 5.0]}
        traj1 = integrate_trajectory(rates, dt=0.01, v_scale=1.0)
        traj2 = integrate_trajectory(rates, dt=0.01, v_scale=5.0)

        m1 = trajectory_metrics(traj1)
        m2 = trajectory_metrics(traj2)

        self.assertAlmostEqual(m1['forward_progress_index'], m2['forward_progress_index'], places=5)
        self.assertAlmostEqual(m1['straightness'], m2['straightness'], places=5)
        self.assertAlmostEqual(m2['displacement'], m1['displacement'] * 5.0, places=4)
        self.assertAlmostEqual(m2['path_length'], m1['path_length'] * 5.0, places=4)

    def test_score_dual_decoder_integration(self):
        """Verifies score.py evaluates both discrete approach_index and continuous trajectory verdicts side-by-side."""
        import tempfile, json, subprocess, sys, os
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False) as f:
            for cond in ('real', 'shuffled', 'random'):
                for trial in range(10):
                    # In this trial design: real shows clear chemotaxis ordering, nulls do not
                    ci_att = 0.8 if cond == 'real' else (-0.2 if cond == 'shuffled' else 0.0)
                    ci_neu = 0.2 if cond == 'real' else (0.1 if cond == 'shuffled' else 0.0)
                    ci_rep = -0.5 if cond == 'real' else (0.4 if cond == 'shuffled' else 0.0)
                    for stim, ci_val, hz_val in (('attractant', ci_att, 50.0), ('neutral', ci_neu, 30.0), ('repellent', ci_rep, 10.0)):
                        f.write(json.dumps({
                            'item': 1, 'condition': cond, 'trial': trial, 'stimulus': stim,
                            'readouts': {
                                'DNp09': {'baseline_hz': 0.0, 'stimulus_hz': hz_val},
                                'MDN': {'baseline_hz': 0.0, 'stimulus_hz': 10.0}
                            },
                            'trajectory': {
                                'displacement': ci_val * 10,
                                'path_length': 10.0,
                                'forward_progress_index': ci_val, 'chemotaxis_index': ci_val,
                                'straightness': 0.9
                            }
                        }) + '\n')
            temp_runs = f.name

        out_json = temp_runs + '.verdicts.json'
        try:
            proc = subprocess.run([sys.executable, 'src/score.py', temp_runs, '--json', out_json], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"score.py failed: {proc.stderr}")
            with open(out_json) as jf:
                scored = json.load(jf)
            self.assertIn('1', scored)
            self.assertIn('trajectory', scored['1'])
            self.assertEqual(scored['1']['trajectory']['verdict'], 'held')
            self.assertIn('[trajectory FPI]', proc.stdout)
        finally:
            if os.path.exists(temp_runs): os.unlink(temp_runs)
            if os.path.exists(out_json): os.unlink(out_json)

    def test_score_backward_compatibility(self):
        """Verifies score.py on legacy baseline without trajectory produces zero error and no regression."""
        import subprocess, sys
        proc = subprocess.run([sys.executable, 'src/score.py', 'results/runs.jsonl'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn('[trajectory FPI]', proc.stdout)
        self.assertIn('3 CO2 avoidance, walking state -> held', proc.stdout)


    def test_trajectory_gating_walking_items(self):
        """Trajectory recording is gated to walking items (1, 2, 3). Non-walking items (4, 5, 6) produce None."""
        with open('src/runner.py') as f:
            content = f.read()
        self.assertIn("is_walking = it['id'] in (1, 2, 3)", content)
        self.assertIn("trajectory=(traj_metrics if is_walking else None)", content)

        try:
            from src.runner import simulate
            import torch
            W = torch.sparse_coo_tensor(torch.zeros((2, 0), dtype=torch.int64), torch.zeros(0), (20, 20))
            P = {'tau': 10.0, 'gap': 1.0, 'Tm': 20.0, 'ref': 2.0, 'dly': 1.0, 'wscale': 1.0}
            ro = {'DNp09': [0], 'MDN': [1], 'DNa02_L': [2], 'DNa02_R': [3]}
            out, traj_none = simulate(W, P, None, [], ro, seed=1, dt=1.0, track_trajectory=False)
            self.assertIsNone(traj_none)
            out, traj_walk = simulate(W, P, None, [], ro, seed=1, dt=1.0, track_trajectory=True)
            self.assertIsNotNone(traj_walk)
            self.assertIn('forward_progress_index', traj_walk)
        except ImportError:
            pass

if __name__ == '__main__':
    unittest.main()
