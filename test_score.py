#!/usr/bin/env python3
"""Unit tests for src/score.py battery scoring, difference tests, and CLI flag handling."""
import os
import sys
import json
import unittest
import subprocess
import tempfile

sys_py = sys.executable

class TestScoreCliAndPrecedence(unittest.TestCase):
    def test_help_flag(self):
        res = subprocess.run([sys_py, 'src/score.py', '--help'], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn('--battery', res.stdout)
        self.assertIn('--step', res.stdout)
        self.assertIn('--json', res.stdout)

    def test_battery_resolution_flag_override(self):
        # Test that --battery flag overrides environment variable
        cmd = [
            sys_py, 'src/score.py',
            '--battery', 'battery/battery.json',
            'results/runs.jsonl'
        ]
        env = os.environ.copy()
        env['FLY_BATTERY'] = 'battery/battery-v2.json'
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn('3 CO2 avoidance, walking state -> held', res.stdout)

    def test_json_export_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = os.path.join(tmpdir, 'out.json')
            cmd = [
                sys_py, 'src/score.py',
                '--battery', 'battery/battery-v4.json',
                'results/runs-v3.jsonl', '1',
                '--json', out_json
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            self.assertTrue(os.path.exists(out_json))
            with open(out_json) as f:
                data = json.load(f)
            self.assertIn('3', data)
            self.assertIn('4', data)
            self.assertIn('5', data)
            self.assertIn('6', data)


class TestMagnitudeAndCompoundItems(unittest.TestCase):
    def test_directional_magnitudes_items_1_to_4(self):
        from src.score import magnitude
        # Item 1: attractant - repellent (v[0] - v[2])
        self.assertEqual(magnitude(1, [10.0, 5.0, 2.0]), 8.0)
        # Item 2: low - high (v[0] - v[1])
        self.assertEqual(magnitude(2, [12.0, 4.0]), 8.0)
        # Item 3: none - co2 (v[1] - v[0])
        self.assertEqual(magnitude(3, [-5.0, 0.0]), 5.0)
        # Item 4: loom - control_visual (v[0] - v[1])
        self.assertEqual(magnitude(4, [50.0, 10.0]), 40.0)

    def test_compound_items_5_and_6_return_none(self):
        from src.score import magnitude
        # Item 5 and Item 6 return None to avoid sum-masking compound predicates
        self.assertIsNone(magnitude(5, [250.0, -250.0, 169.0, -44.0]))
        self.assertIsNone(magnitude(6, [2.4, 0.0, 9.9, 3.8, 0.0]))

    def test_difference_tests_structure_items_5_and_6(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = os.path.join(tmpdir, 'v3_out.json')
            cmd = [
                sys_py, 'src/score.py',
                '--battery', 'battery/battery-v4.json',
                'results/runs-v3.jsonl', '1',
                '--json', out_json
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            with open(out_json) as f:
                data = json.load(f)

            # Item 5: paired_wins is null, note explains sign-flip product test
            item5_shuffled = data['5']['difference_tests']['shuffled']
            self.assertIsNone(item5_shuffled['paired_wins'])
            self.assertIn('sign flip', item5_shuffled['note'])

            # Item 6: paired_wins is null, note explains multi-clause, clauses reports each clause
            item6_shuffled = data['6']['difference_tests']['shuffled']
            self.assertIsNone(item6_shuffled['paired_wins'])
            self.assertIn('differing signs', item6_shuffled['note'])
            self.assertIn('clauses', item6_shuffled)
            self.assertIn('pC1_activation', item6_shuffled['clauses'])
            self.assertIn('pIP10_activation', item6_shuffled['clauses'])
            self.assertIn('cva_inhibition', item6_shuffled['clauses'])


class TestScoreParityRegressions(unittest.TestCase):
    def test_runs_v1_parity(self):
        cmd = [sys_py, 'src/score.py', '--battery', 'battery/battery.json', 'results/runs.jsonl']
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn('1 odour valence ordering -> failed', res.stdout)
        self.assertIn('2 concentration reversal -> failed', res.stdout)
        self.assertIn('3 CO2 avoidance, walking state -> held', res.stdout)
        self.assertIn('4 looming escape via the giant fibre -> held', res.stdout)
        self.assertIn('5 optomotor turning -> failed', res.stdout)
        self.assertIn('6 male courtship song pathway -> failed', res.stdout)

    def test_runs_v3_step1_difference_tests_parity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = os.path.join(tmpdir, 'v3_step1.json')
            cmd = [
                sys_py, 'src/score.py',
                '--battery', 'battery/battery-v4.json',
                'results/runs-v3.jsonl', '1',
                '--json', out_json
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            with open(out_json) as f:
                data = json.load(f)

            item3_rand = data['3']['difference_tests']['random']
            self.assertEqual(item3_rand['fake'], '5/10')
            self.assertEqual(item3_rand['paired_wins'], '6/10')
            self.assertEqual(item3_rand['sign_p'], 0.377)

            item4_rand = data['4']['difference_tests']['random']
            self.assertEqual(item4_rand['fake'], '4/10')
            self.assertEqual(item4_rand['paired_wins'], '9/10')
            self.assertEqual(item4_rand['sign_p'], 0.0107)

if __name__ == '__main__':
    unittest.main()
