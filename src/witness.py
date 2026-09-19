#!/usr/bin/env python3
"""witness.py — Turnkey Witness Runner & Attestation CLI for Grant 1FAB0.

Ensures independent referee full runs are namespaced under:
  results/witness/<seat>/runs-v4.jsonl
  results/witness/<seat>/verdicts-v4.json
  results/witness/<seat>/witness_attestation.json
preventing collision with upstream results/runs-v4.jsonl.
"""

import os
import sys

# Ensure repository root is in sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

try:
    from src.witness_attest import (
        CANONICAL_BATTERY_V4_SHA256,
        CANONICAL_SUBSTRATE_HASHES,
        compute_file_sha256,
        verify_file_hash,
        derive_trial_seed,
        verify_runs_hash_chain,
        get_git_metadata,
        get_system_metadata,
        generate_attestation,
        format_markdown_receipt,
        main,
    )
except ImportError:
    from witness_attest import (
        CANONICAL_BATTERY_V4_SHA256,
        CANONICAL_SUBSTRATE_HASHES,
        compute_file_sha256,
        verify_file_hash,
        derive_trial_seed,
        verify_runs_hash_chain,
        get_git_metadata,
        get_system_metadata,
        generate_attestation,
        format_markdown_receipt,
        main,
    )

if __name__ == "__main__":
    main()
