"""
Unit tests for the Turnkey Witness & Verification Harness (Grant 1FAB0).
Verifies:
  1. Canonical battery v4 seal matches pre-registered hash.
  2. Hash verification functions reliably detect matching vs tampered files.
  3. Substrate hash definitions match canonical MaleCNS v1.0 specifications.
  4. Seed derivation sha256(seal || root || i) is deterministic and matches runner.py parity.
  5. Trial runs JSONL hash-chain verification correctly validates unbroken chains and flags tampering.
  6. Attestation receipt generator produces compliant JSON schema and human-readable Markdown.
  7. Shell harness script syntax and CLI help options.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest

from src.witness_attest import (
    CANONICAL_BATTERY_V4_SHA256,
    CANONICAL_SUBSTRATE_HASHES,
    compute_file_sha256,
    derive_trial_seed,
    format_markdown_receipt,
    generate_attestation,
    get_git_metadata,
    get_system_metadata,
    verify_file_hash,
    verify_runs_hash_chain,
)


class TestHashVerification(unittest.TestCase):
    def test_canonical_battery_v4_seal(self):
        """Verifies battery/battery-v4.json matches the canonical pre-registered SHA-256 seal."""
        battery_path = "battery/battery-v4.json"
        self.assertTrue(os.path.exists(battery_path), f"{battery_path} must exist")
        actual_sha = compute_file_sha256(battery_path)
        self.assertEqual(
            actual_sha,
            CANONICAL_BATTERY_V4_SHA256,
            f"Battery v4 seal mismatch: expected {CANONICAL_BATTERY_V4_SHA256}, got {actual_sha}",
        )

    def test_verify_file_hash_valid_and_tampered(self):
        """Tests that verify_file_hash reliably confirms matches and detects tampering."""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            tf.write("genuine-scientific-payload\n")
            tf_path = tf.name

        try:
            expected_sha = hashlib.sha256(b"genuine-scientific-payload\n").hexdigest()
            ok, actual = verify_file_hash(tf_path, expected_sha)
            self.assertTrue(ok)
            self.assertEqual(actual, expected_sha)

            # Test tampered expected hash
            tampered_sha = "0000000000000000000000000000000000000000000000000000000000000000"
            ok_bad, actual_bad = verify_file_hash(tf_path, tampered_sha)
            self.assertFalse(ok_bad)
            self.assertEqual(actual_bad, expected_sha)

            # Test non-existent file
            ok_none, actual_none = verify_file_hash("/path/does/not/exist/file.bin", expected_sha)
            self.assertFalse(ok_none)
            self.assertIsNone(actual_none)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_canonical_substrate_hashes_against_substrate_figures(self):
        """Verifies that CANONICAL_SUBSTRATE_HASHES matches figures in battery/substrate-figures.json."""
        figures_path = "battery/substrate-figures.json"
        self.assertTrue(os.path.exists(figures_path), f"{figures_path} must exist")
        with open(figures_path, "r", encoding="utf-8") as f:
            figures = json.load(f)

        input_hashes = figures.get("input_sha256", {})
        for fname, expected_hash in CANONICAL_SUBSTRATE_HASHES.items():
            self.assertIn(fname, input_hashes)
            self.assertEqual(input_hashes[fname], expected_hash)


class TestSeedDerivation(unittest.TestCase):
    def test_deterministic_seed_generation(self):
        """Verifies seed generation produces identical integers for fixed seal, root, and index."""
        seal = CANONICAL_BATTERY_V4_SHA256
        root = "09755e6bcd9b49c91241c61616e2a749d1b5bd2726be228c2369c4ff4a1c94b9"

        seed0_a = derive_trial_seed(seal, root, 0)
        seed0_b = derive_trial_seed(seal, root, 0)
        seed1 = derive_trial_seed(seal, root, 1)

        self.assertIsInstance(seed0_a, int)
        self.assertEqual(seed0_a, seed0_b)
        self.assertNotEqual(seed0_a, seed1)

    def test_seed_derivation_parity_with_runner(self):
        """Ensures derive_trial_seed formula exactly reproduces runner.py's implementation."""
        seal = "abcdef1234567890"
        root = "1234567890abcdef"
        for i in range(5):
            expected = int(hashlib.sha256((seal + root + str(i)).encode()).hexdigest()[:15], 16)
            actual = derive_trial_seed(seal, root, i)
            self.assertEqual(actual, expected)


class TestHashChaining(unittest.TestCase):
    def test_smoke_v4_hash_chain_validity(self):
        """Tests that results/smoke-v4.jsonl contains an unbroken hash chain initialized from v4 seal."""
        smoke_file = "results/smoke-v4.jsonl"
        self.assertTrue(os.path.exists(smoke_file), f"{smoke_file} must exist")
        report = verify_runs_hash_chain(smoke_file, expected_initial_prev=CANONICAL_BATTERY_V4_SHA256)

        self.assertTrue(report["valid"], f"Hash chain failed: {report.get('errors')}")
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["first_prev"], CANONICAL_BATTERY_V4_SHA256)
        self.assertEqual(len(report["errors"]), 0)

    def test_tampered_run_row_detected(self):
        """Tests that an altered row or broken prev pointer is caught by verify_runs_hash_chain."""
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            init_prev = "initialhash12345"
            row1 = {"trial": 0, "condition": "real", "prev": init_prev}
            row1_sha = hashlib.sha256(json.dumps(row1, sort_keys=True).encode()).hexdigest()
            row1["sha256"] = row1_sha

            # Row 2 with broken prev
            row2 = {"trial": 1, "condition": "real", "prev": "wrong_prev_pointer"}
            row2_sha = hashlib.sha256(json.dumps(row2, sort_keys=True).encode()).hexdigest()
            row2["sha256"] = row2_sha

            tf.write(json.dumps(row1, sort_keys=True) + "\n")
            tf.write(json.dumps(row2, sort_keys=True) + "\n")
            tf_path = tf.name

        try:
            report = verify_runs_hash_chain(tf_path, expected_initial_prev=init_prev)
            self.assertFalse(report["valid"])
            self.assertGreater(len(report["errors"]), 0)
            self.assertTrue(any("broken hash chain" in e for e in report["errors"]))
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_missing_runs_file_handling(self):
        """Verifies verify_runs_hash_chain handles non-existent paths gracefully."""
        report = verify_runs_hash_chain("/tmp/nonexistent_runs_file.jsonl")
        self.assertFalse(report["valid"])
        self.assertIn("File not found", report.get("error", ""))


class TestAttestationGeneration(unittest.TestCase):
    def test_attestation_schema_conformance(self):
        """Tests generate_attestation returns all required top-level schema fields."""
        attestation = generate_attestation(
            battery_path="battery/battery-v4.json",
            runs_path="results/smoke-v4.jsonl",
            verdicts_path="results/verdicts-v4.json",
            witness_seat="test-referee-seat",
            checkpoint_root="09755e6bcd9b49c91241c61616e2a749d1b5bd2726be228c2369c4ff4a1c94b9",
        )

        required_keys = [
            "contract",
            "grant",
            "protocol",
            "witness_seat",
            "timestamp_utc",
            "git",
            "system",
            "substrate",
            "battery",
            "seed_parameters",
            "runs",
            "verdicts",
            "summary",
        ]
        for key in required_keys:
            self.assertIn(key, attestation, f"Missing key in attestation schema: {key}")

        self.assertEqual(attestation["contract"], "1fab0.witness_attestation.v1")
        self.assertEqual(attestation["grant"], "1fab0")
        self.assertEqual(attestation["witness_seat"], "test-referee-seat")
        self.assertTrue(attestation["battery"]["matches_canonical_seal"])

    def test_markdown_receipt_rendering(self):
        """Tests format_markdown_receipt produces Markdown with expected sections."""
        attestation = generate_attestation(
            battery_path="battery/battery-v4.json",
            runs_path="results/smoke-v4.jsonl",
            verdicts_path="results/verdicts-v4.json",
            witness_seat="pavel-pi",
            checkpoint_root="09755e6bcd9b49c91241c61616e2a749d1b5bd2726be228c2369c4ff4a1c94b9",
        )
        md = format_markdown_receipt(attestation)

        self.assertIn("# Witness Attestation Receipt: Grant 1FAB0", md)
        self.assertIn("c65253", md)
        self.assertIn("pavel-pi", md)
        self.assertIn("## 1. Witness Execution Provenance", md)
        self.assertIn("## 2. Cryptographic Integrity Checks", md)
        self.assertIn("## 5. Attestation Declaration", md)
        self.assertIn("1f916 attest --subject", md)

    def test_git_and_system_metadata_helpers(self):
        """Tests that get_git_metadata and get_system_metadata return populated structures."""
        git_meta = get_git_metadata()
        self.assertIn("commit", git_meta)
        self.assertIn("branch", git_meta)
        self.assertIn("dirty", git_meta)

        sys_meta = get_system_metadata()
        self.assertIn("python_version", sys_meta)
        self.assertIn("platform", sys_meta)
        self.assertIn("timestamp_utc", sys_meta)


class TestVerifyWitnessScript(unittest.TestCase):
    def test_verify_witness_bash_syntax(self):
        """Verifies src/verify_witness.sh passes bash syntax validation (bash -n)."""
        res = subprocess.run(
            ["bash", "-n", "src/verify_witness.sh"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Bash syntax check failed: {res.stderr}")

    def test_verify_witness_help_flag(self):
        """Verifies src/verify_witness.sh --help executes with exit code 0."""
        res = subprocess.run(
            ["bash", "src/verify_witness.sh", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Turnkey zero-credential verification harness", res.stdout)


if __name__ == "__main__":
    unittest.main()
