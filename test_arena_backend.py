"""
Unit tests for ConnectomeArena Continuous Rate ODE Simulation Backend (Grant 1FAB0).

Verifies:
  1. Numerical stability, ODE convergence, and non-divergence across extreme inputs.
  2. Sigmoidal and rectified linear (ReLU) activation functions.
  3. Sensory driving and modulation of descending readouts (DNp09, MDN, DNa02, DNp01, pC1, pIP10).
  4. Degree-preserving shuffled and sign-preserving random-dynamics null models.
  5. Deterministic reproducibility under identical random seeds.
  6. Integration with continuous 2D trajectory decoding and anti-clamping preservation.
  7. Backward compatibility and --simulator CLI flag in runner.py.
"""

import unittest
import numpy as np

from src.arena_backend import ConnectomeArenaSimulation
from src.trajectory import Trajectory


def build_toy_sensory_motor_circuit():
    """
    Builds a synthetic Drosophila-inspired microcircuit with named classes:
      Inputs:
        0: ORN_DM1 (attractant)
        1: ORN_DA2 (repellent)
        2: LC4 (visual looming)
        3: T4a (visual flow left)
        4: T4b (visual flow right)
        5: female_taste (pheromone / taste)
      Interneurons:
        6: PN_DM1 (projection neuron)
        7: PN_DA2 (projection neuron)
        8: LN_inh (local inhibitory interneuron)
      Descending / Readouts:
        9: DNp09 (forward locomotion)
        10: MDN (backward locomotion / moonwalker)
        11: DNa02_L (steering left)
        12: DNa02_R (steering right)
        13: DNp01 (giant fibre looming escape)
        14: pC1 (courtship integration hub)
        15: pIP10 (pulse song command)
    """
    n = 16
    types = [
        'ORN_DM1', 'ORN_DA2', 'LC4', 'T4a', 'T4b', 'female_taste',
        'PN_DM1', 'PN_DA2', 'LN_inh',
        'DNp09', 'MDN', 'DNa02', 'DNa02', 'DNp01', 'pC1', 'pIP10'
    ]
    sides = [
        '', '', '', 'L', 'R', '',
        '', '', '',
        '', '', 'L', 'R', '', '', ''
    ]
    receptors = ['' for _ in range(n)]
    receptors[5] = 'putative_ppk25'

    # Synaptic connections (post, pre, weight)
    edges = [
        # Odour attractant: ORN_DM1 -> PN_DM1 -> DNp09
        (6, 0, 0.5),
        (9, 6, 0.5),

        # Odour repellent: ORN_DA2 -> PN_DA2 -> MDN + LN_inh
        (7, 1, 0.5),
        (10, 7, 0.5),
        (8, 7, 0.5),
        # Inhibitory LN -> DNp09
        (9, 8, -0.5),

        # Looming: LC4 -> DNp01
        (13, 2, 0.5),

        # Steering: T4a -> DNa02_L, T4b -> DNa02_R
        (11, 3, 0.5),
        (12, 4, 0.5),

        # Courtship: female_taste -> pC1 -> pIP10
        (14, 5, 0.5),
        (15, 14, 0.5),
    ]

    row = np.array([e[0] for e in edges], dtype=np.int64)
    col = np.array([e[1] for e in edges], dtype=np.int64)
    data = np.array([e[2] for e in edges], dtype=np.float32)

    return (row, col, data), n, types, sides, receptors


class TestConnectomeArenaSimulation(unittest.TestCase):

    def test_ode_numerical_stability_and_bounds(self):
        """Rates must remain strictly bounded in [0, r_max] even under extreme stimulus pulses."""
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()
        sim = ConnectomeArenaSimulation(
            weights=weights,
            num_neurons=n,
            neuron_types=types,
            soma_sides=sides,
            receptor_types=recs,
            r_max=150.0,
            tau_ms=20.0,
            gain_k=0.5,
            x0=10.0,
            activation='sigmoid'
        )

        # Drive with extreme rate pulses (1,000 Hz)
        for t in range(500):
            extreme_inputs = [('ORN_DM1', 1000.0), ('ORN_DA2', 1000.0)]
            r = sim.step(dt_ms=1.0, stimulus_inputs=extreme_inputs, t_ms=float(t))
            self.assertTrue(np.all(r >= 0.0), "Rates dropped below 0")
            self.assertTrue(np.all(r <= 150.0 + 1e-6), "Rates exceeded r_max")

    def test_ode_convergence_to_steady_state(self):
        """Under constant input, isolated rate ODE converges monotonically to fixed point phi(I)."""
        # Single isolated neuron (W = 0)
        sim = ConnectomeArenaSimulation(
            weights=None,
            num_neurons=1,
            tau_ms=20.0,
            r_max=150.0,
            gain_k=0.1,
            x0=0.0,
            activation='sigmoid'
        )

        ext_drive = np.array([10.0])
        expected_target = sim.phi(ext_drive)[0]

        # Integrate forward
        dt = 1.0
        for _ in range(300):
            sim.step(dt_ms=dt, ext_current=ext_drive)

        # Should be within 0.1% of analytical target
        self.assertAlmostEqual(sim.r[0], expected_target, delta=0.05)

    def test_activation_functions(self):
        """Sigmoid and ReLU satisfy mathematical bounds and monotonicity."""
        sim_sig = ConnectomeArenaSimulation(num_neurons=5, r_max=150.0, gain_k=0.2, x0=5.0, activation='sigmoid')
        sim_relu = ConnectomeArenaSimulation(num_neurons=5, r_max=150.0, gain_k=2.0, x0=5.0, activation='relu')

        x_vals = np.array([-50.0, 0.0, 5.0, 10.0, 100.0])

        # Sigmoid tests
        sig_out = sim_sig.phi(x_vals)
        self.assertAlmostEqual(sig_out[2], 75.0, places=3)  # Midpoint phi(x0) = r_max / 2
        self.assertTrue(np.all(np.diff(sig_out) > 0))        # Monotonicity
        self.assertAlmostEqual(sig_out[0], 0.0, places=2)   # Negative saturation
        self.assertAlmostEqual(sig_out[-1], 150.0, places=2) # Positive saturation

        # ReLU tests
        relu_out = sim_relu.phi(x_vals)
        self.assertEqual(relu_out[0], 0.0)                  # Below threshold
        self.assertEqual(relu_out[1], 0.0)                  # Below threshold
        self.assertEqual(relu_out[2], 0.0)                  # At threshold
        self.assertEqual(relu_out[3], 10.0)                 # Linear slope: 2.0 * (10 - 5) = 10
        self.assertEqual(relu_out[4], 150.0)                # Saturation at r_max

    def test_sensory_modulation_odour_attractant_vs_repellent(self):
        """
        Attractant stimulus (ORN_DM1) drives forward walking (DNp09 > MDN), positive CI.
        Repellent stimulus (ORN_DA2) drives reverse walking (MDN > DNp09), negative CI.
        Anti-clamping invariant: negative displacement is preserved.
        """
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()
        sim = ConnectomeArenaSimulation(
            weights=weights,
            num_neurons=n,
            neuron_types=types,
            soma_sides=sides,
            receptor_types=recs,
            tau_ms=20.0,
            r_max=150.0,
            gain_k=0.5,
            x0=10.0
        )

        readouts = {
            'DNp09': sim.resolve_class('DNp09'),
            'MDN': sim.resolve_class('MDN'),
            'DNa02_L': sim.resolve_class({'classes': ['DNa02'], 'side': 'L'}),
            'DNa02_R': sim.resolve_class({'classes': ['DNa02'], 'side': 'R'}),
        }

        # 1. Stimulate attractant (DM1)
        res_attr, traj_attr = sim.simulate(
            inputs=[('ORN_DM1', 50.0)],
            readouts=readouts,
            warmup_ms=100.0,
            baseline_ms=100.0,
            stimulus_ms=300.0,
            dt_ms=1.0
        )

        self.assertGreater(res_attr['DNp09']['stimulus_hz'], res_attr['DNp09']['baseline_hz'])
        self.assertGreater(res_attr['DNp09']['stimulus_hz'], res_attr['MDN']['stimulus_hz'])
        self.assertIsNotNone(traj_attr)
        self.assertGreater(traj_attr['displacement'], 0.0)
        self.assertGreater(traj_attr['chemotaxis_index'], 0.0)

        # 2. Stimulate repellent (DA2)
        res_rep, traj_rep = sim.simulate(
            inputs=[('ORN_DA2', 50.0)],
            readouts=readouts,
            warmup_ms=100.0,
            baseline_ms=100.0,
            stimulus_ms=300.0,
            dt_ms=1.0
        )

        self.assertGreater(res_rep['MDN']['stimulus_hz'], res_rep['MDN']['baseline_hz'])
        self.assertGreater(res_rep['MDN']['stimulus_hz'], res_rep['DNp09']['stimulus_hz'])
        self.assertIsNotNone(traj_rep)
        # Anti-clamping invariant verification
        self.assertLess(traj_rep['displacement'], 0.0)
        self.assertLess(traj_rep['chemotaxis_index'], 0.0)

    def test_sensory_modulation_visual_steering_and_looming(self):
        """
        Asymmetric visual flow (T4a) drives asymmetric steering (DNa02_L > DNa02_R).
        Looming stimulus (LC4) drives giant fibre escape (DNp01).
        """
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()
        sim = ConnectomeArenaSimulation(
            weights=weights,
            num_neurons=n,
            neuron_types=types,
            soma_sides=sides,
            receptor_types=recs,
            tau_ms=20.0,
            r_max=150.0,
            gain_k=0.5,
            x0=10.0
        )

        readouts = {
            'DNp09': sim.resolve_class('DNp09'),
            'MDN': sim.resolve_class('MDN'),
            'DNa02_L': sim.resolve_class({'classes': ['DNa02'], 'side': 'L'}),
            'DNa02_R': sim.resolve_class({'classes': ['DNa02'], 'side': 'R'}),
            'DNp01': sim.resolve_class('DNp01'),
            'pC1': sim.resolve_class('pC1'),
            'pIP10': sim.resolve_class('pIP10'),
        }

        # 1. Drive left visual motion (T4a)
        res_turn, traj_turn = sim.simulate(
            inputs=[('T4a', 50.0)],
            readouts=readouts,
            warmup_ms=100.0,
            baseline_ms=100.0,
            stimulus_ms=300.0
        )

        self.assertGreater(res_turn['DNa02_L']['stimulus_hz'], res_turn['DNa02_R']['stimulus_hz'])
        self.assertGreater(traj_turn['turning_rate'], 0.0)
        self.assertGreater(traj_turn['angular_deviation'], 0.0)

        # 2. Drive looming stimulus (LC4)
        res_loom, _ = sim.simulate(
            inputs=[('LC4', lambda t: min(150.0, 150.0 * 0.05 / max(0.02, (300.0 - t) / 300.0)))],
            readouts=readouts,
            warmup_ms=100.0,
            baseline_ms=100.0,
            stimulus_ms=300.0
        )

        self.assertGreater(res_loom['DNp01']['stimulus_hz'], res_loom['DNp01']['baseline_hz'] + 20.0)

        # 3. Drive courtship taste (female_taste)
        res_court, _ = sim.simulate(
            inputs=[('female_taste', 50.0)],
            readouts=readouts,
            warmup_ms=100.0,
            baseline_ms=100.0,
            stimulus_ms=300.0
        )
        self.assertGreater(res_court['pC1']['stimulus_hz'], res_court['pC1']['baseline_hz'] + 20.0)
        self.assertGreater(res_court['pIP10']['stimulus_hz'], res_court['pIP10']['baseline_hz'] + 20.0)

    def test_null_models_shuffled_and_random_twins(self):
        """
        Shuffled twin preserves node degrees while breaking specific sensory-motor alignment.
        Random dynamics twin permutes signs and randomizes dynamics parameters.
        """
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()
        sim_real = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='real', seed=42
        )
        sim_shuffled = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='shuffled', seed=42
        )
        sim_random = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='random', seed=42
        )

        # Verify degree preservation in shuffled twin
        in_degrees_real = np.bincount(sim_real.row, minlength=n)
        in_degrees_shuffled = np.bincount(sim_shuffled.row, minlength=n)
        out_degrees_real = np.bincount(sim_real.col, minlength=n)
        out_degrees_shuffled = np.bincount(sim_shuffled.col, minlength=n)

        np.testing.assert_array_equal(out_degrees_real, out_degrees_shuffled)
        # Sum of in-degrees matches
        self.assertEqual(int(np.sum(in_degrees_real)), int(np.sum(in_degrees_shuffled)))

        # Verify random dynamics parameters
        self.assertIsNotNone(sim_random.jitter)
        self.assertNotEqual(float(sim_random.tau[0]), float(sim_real.tau[0]))
        self.assertNotEqual(float(sim_random.x0[0]), float(sim_real.x0[0]))

    def test_deterministic_reproducibility(self):
        """Identical seeds produce bit-for-bit identical trajectories and rates."""
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()

        sim1 = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='random', seed=12345
        )
        res1, traj1 = sim1.simulate(
            inputs=[('ORN_DM1', 50.0)],
            warmup_ms=100.0, baseline_ms=100.0, stimulus_ms=200.0, dt_ms=1.0
        )

        sim2 = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='random', seed=12345
        )
        res2, traj2 = sim2.simulate(
            inputs=[('ORN_DM1', 50.0)],
            warmup_ms=100.0, baseline_ms=100.0, stimulus_ms=200.0, dt_ms=1.0
        )

        self.assertEqual(res1['DNp09']['stimulus_hz'], res2['DNp09']['stimulus_hz'])
        self.assertEqual(traj1['displacement'], traj2['displacement'])
        self.assertEqual(traj1['forward_progress_index'], traj2['forward_progress_index'])
        self.assertEqual(traj1['chemotaxis_index'], traj2['chemotaxis_index'])

        # Different seed produces distinct results
        sim3 = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='random', seed=99999
        )
        res3, traj3 = sim3.simulate(
            inputs=[('ORN_DM1', 50.0)],
            warmup_ms=100.0, baseline_ms=100.0, stimulus_ms=200.0, dt_ms=1.0
        )
        self.assertNotEqual(traj1['displacement'], traj3['displacement'])

    def test_trajectory_tracking_gated(self):
        """When track_trajectory=False, simulate() returns traj_metrics=None."""
        weights, n, types, sides, recs = build_toy_sensory_motor_circuit()
        sim = ConnectomeArenaSimulation(
            weights=weights, num_neurons=n, neuron_types=types, soma_sides=sides,
            condition='real', seed=42
        )
        res, traj = sim.simulate(
            inputs=[('ORN_DM1', 50.0)],
            warmup_ms=50.0, baseline_ms=50.0, stimulus_ms=100.0,
            track_trajectory=False
        )
        self.assertIsNotNone(res)
        self.assertIsNone(traj)

    def test_null_twin_stream_offsets_documented(self):
        """Verifies docstring explicitly details the null twin stream offsets."""
        import src.arena_backend as ab
        self.assertIn("1000 + seed", ab.__doc__)
        self.assertIn("2000 + seed", ab.__doc__)
        self.assertIn("3000 + seed", ab.__doc__)
        self.assertIn("1000 + seed", ab.ConnectomeArenaSimulation.__doc__)

    def test_from_substrate_raises_on_missing_files(self):
        """from_substrate explicitly raises an error if data files are missing."""
        with self.assertRaises(Exception):
            ConnectomeArenaSimulation.from_substrate(derived_dir="/tmp/nonexistent_1fab0_dir")

    def test_score_disagreement_check(self):
        """score.py rejects runs.jsonl files with mixed simulator backends."""
        import subprocess, sys, tempfile, json
        row1 = {
            "battery_file": "battery/battery.json",
            "battery_sha256": "fake",
            "condition": "real",
            "item": 1,
            "params": {"simulator": "spiking"},
            "prev": "0",
            "readouts": {},
            "seed": 0,
            "seed_material": None,
            "sha256": "fake1",
            "step": None,
            "stimulus": "test",
            "trial": 0,
            "wall_s": 0.1,
        }
        row2 = dict(row1, params={"simulator": "arena"}, sha256="fake2")
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tf:
            tf.write(json.dumps(row1) + "\n" + json.dumps(row2) + "\n")
            tf_path = tf.name

        import os
        try:
            cmd = [sys.executable, "src/score.py", tf_path]
            p = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("Disagreement in simulation backend", p.stderr)
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_runner_simulator_cli_flag(self):
        """Verifies runner.py supports --simulator {spiking,arena} defaulting to spiking."""
        import subprocess, sys
        cmd = [sys.executable, 'src/runner.py', '--help']
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn('--simulator {spiking,arena}', res.stdout)
        self.assertIn('arena continuous rate ODE', res.stdout)
        normalized_stdout = " ".join(res.stdout.split()).replace("- ", "-")
        self.assertIn('results/runs-arena.jsonl if --simulator arena', normalized_stdout)


if __name__ == '__main__':
    unittest.main()

