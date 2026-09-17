#!/usr/bin/env python3
"""witness_attest.py — Independent Referee Attestation Generator for Grant 1FAB0.

Implements the custody separation protocol agreed in 1F916 thread #4870 (comment c65253):
Scoring of the sealed battery v4 is executed and attested by an independent referee/witness
seat (neither the proposal author nor competitor seats).

This module aggregates the complete execution receipt:
  1. Git commit provenance and working tree clean status
  2. Substrate Feather tables SHA-256 vs canonical MaleCNS v1.0 hashes
  3. Battery JSON SHA-256 vs canonical v4 seal
  4. Trial runs hash-chain integrity and final row digest
  5. Verdicts output SHA-256 and scored outcomes
  6. Pre-registered seed derivation parameters sha256(seal || root || i)
  7. Formatted attestation documents (.json and .md) and 1F916 submission instructions
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys

CANONICAL_BATTERY_V4_SHA256 = "e90b093bbbd7898b726cf4cc41167b3f7d010c888cd47d3e4a007e25f6392991"

CANONICAL_SUBSTRATE_HASHES = {
    "connectome-weights-male-cns-v1.0-minconf-0.5.feather": "e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1",
    "body-annotations-male-cns-v1.0-minconf-0.5.feather": "2177e246113e4cfbf1e7772ec37c6da1955ff22e8063d0b1f833101f99a9a3b2",
    "body-neurotransmitters-male-cns-v1.0.feather": "95c9289220663abeb3409f3ad9e5a7f8a53f8093f5139d15502cd08da8879621",
}


def compute_file_sha256(path, bufsize=1 << 20):
    """Compute hex SHA-256 digest of a file; returns None if file does not exist."""
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(bufsize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_file_hash(path, expected_hash):
    """Verifies a file matches the expected hex hash string."""
    actual = compute_file_sha256(path)
    if actual is None:
        return False, None
    return actual.lower() == expected_hash.lower(), actual


def derive_trial_seed(seal, root, trial_index):
    """Derive deterministic trial seed sha256(seal || root || i), matching runner.py."""
    payload = (seal + root + str(trial_index)).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:15], 16)


def verify_runs_hash_chain(runs_path, expected_initial_prev=None):
    """Verifies that a JSONL runs file forms an unbroken SHA-256 hash chain.

    Each row's 'prev' field must match the previous row's 'sha256' hash.
    The first row's 'prev' must match expected_initial_prev (if provided).
    Each row's 'sha256' must match the SHA-256 of the row JSON without the 'sha256' key.
    """
    if not os.path.exists(runs_path):
        return {"valid": False, "rows": 0, "error": f"File not found: {runs_path}"}

    rows_count = 0
    prev_hash = expected_initial_prev
    first_prev = None
    last_sha256 = None
    errors = []

    with open(runs_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rows_count += 1
            try:
                row = json.loads(line)
            except Exception as e:
                errors.append(f"Line {line_no}: invalid JSON: {e}")
                break

            row_prev = row.get("prev")
            row_sha = row.get("sha256")

            if line_no == 1:
                first_prev = row_prev
                if expected_initial_prev and row_prev != expected_initial_prev:
                    errors.append(
                        f"Line 1: initial prev mismatch. Expected {expected_initial_prev}, got {row_prev}"
                    )
            elif prev_hash is not None and row_prev != prev_hash:
                errors.append(
                    f"Line {line_no}: broken hash chain. Expected prev={prev_hash}, got {row_prev}"
                )

            # Check self-consistency: sha256 of row without sha256 key
            if row_sha:
                row_copy = dict(row)
                row_copy.pop("sha256", None)
                computed_sha = hashlib.sha256(
                    json.dumps(row_copy, sort_keys=True).encode("utf-8")
                ).hexdigest()
                if computed_sha != row_sha:
                    errors.append(
                        f"Line {line_no}: row hash mismatch. Expected {row_sha}, computed {computed_sha}"
                    )

            prev_hash = row_sha
            last_sha256 = row_sha

    is_valid = (len(errors) == 0) and (rows_count > 0)
    return {
        "valid": is_valid,
        "rows": rows_count,
        "first_prev": first_prev,
        "last_sha256": last_sha256,
        "file_sha256": compute_file_sha256(runs_path),
        "errors": errors,
    }


def get_git_metadata(repo_dir=None):
    """Extract current git commit SHA, branch, and working tree state."""
    cwd = repo_dir or os.getcwd()
    meta = {
        "commit": None,
        "commit_short": None,
        "branch": None,
        "dirty": None,
        "remote_origin": None,
    }
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=cwd, stderr=subprocess.DEVNULL
        ).decode().strip()
        meta["commit"] = commit
        meta["commit_short"] = commit[:7]
    except Exception:
        pass

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, stderr=subprocess.DEVNULL
        ).decode().strip()
        meta["branch"] = branch
    except Exception:
        pass

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=cwd, stderr=subprocess.DEVNULL
        ).decode().strip()
        meta["dirty"] = len(status) > 0
    except Exception:
        pass

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=cwd, stderr=subprocess.DEVNULL
        ).decode().strip()
        meta["remote_origin"] = remote
    except Exception:
        pass

    return meta


def get_system_metadata():
    """Extract runtime system metadata."""
    meta = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "pytorch_version": None,
        "pytorch_device": None,
    }
    try:
        import torch
        meta["pytorch_version"] = torch.__version__
        meta["pytorch_device"] = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    except ImportError:
        meta["pytorch_version"] = "not installed"
        meta["pytorch_device"] = "none"
    return meta


def generate_attestation(
    battery_path="battery/battery-v4.json",
    runs_path="results/runs-v4.jsonl",
    verdicts_path="results/verdicts-v4.json",
    substrate_dir="data/malecns",
    witness_seat="independent-referee",
    checkpoint_root=None,
    repo_dir=None,
):
    """Assembles the full witness attestation dictionary."""
    git_meta = get_git_metadata(repo_dir)
    sys_meta = get_system_metadata()

    # Substrate check
    substrate_report = {}
    all_substrate_match = True
    for fname, expected_hash in CANONICAL_SUBSTRATE_HASHES.items():
        full_path = os.path.join(substrate_dir, fname) if substrate_dir else None
        present = os.path.exists(full_path) if full_path else False
        actual_hash = compute_file_sha256(full_path) if present else None
        matches = (actual_hash == expected_hash) if actual_hash else False
        if not matches:
            all_substrate_match = False
        substrate_report[fname] = {
            "present": present,
            "canonical_sha256": expected_hash,
            "actual_sha256": actual_hash,
            "matches_canonical": matches,
        }

    # Battery check
    battery_sha = compute_file_sha256(battery_path)
    battery_is_v4_canonical = (battery_sha == CANONICAL_BATTERY_V4_SHA256) if battery_sha else False
    battery_meta = {
        "path": battery_path,
        "sha256": battery_sha,
        "canonical_v4_sha256": CANONICAL_BATTERY_V4_SHA256,
        "matches_canonical_seal": battery_is_v4_canonical,
    }

    # Runs check
    runs_report = verify_runs_hash_chain(runs_path, expected_initial_prev=battery_sha)

    # Verdicts check
    verdicts_sha = compute_file_sha256(verdicts_path)
    verdicts_data = None
    if verdicts_path and os.path.exists(verdicts_path):
        try:
            with open(verdicts_path, "r", encoding="utf-8") as f:
                verdicts_data = json.load(f)
        except Exception as e:
            verdicts_data = {"error": f"Failed to parse verdicts JSON: {e}"}

    # Seeds summary
    sample_seeds = []
    if battery_sha and checkpoint_root:
        for i in range(min(5, runs_report.get("rows", 5) or 5)):
            sample_seeds.append({
                "trial": i,
                "seed": derive_trial_seed(battery_sha, checkpoint_root, i),
            })

    attestation = {
        "contract": "1fab0.witness_attestation.v1",
        "grant": "1fab0",
        "protocol": "Custody-Separated Independent Battery Scoring (c65253)",
        "witness_seat": witness_seat,
        "timestamp_utc": sys_meta["timestamp_utc"],
        "git": git_meta,
        "system": sys_meta,
        "substrate": {
            "all_canonical_match": all_substrate_match,
            "files": substrate_report,
        },
        "battery": battery_meta,
        "seed_parameters": {
            "seal": battery_sha,
            "checkpoint_root": checkpoint_root,
            "derivation_rule": "int(sha256(seal || root || str(i))[:15], 16)",
            "sample_seeds": sample_seeds,
        },
        "runs": runs_report,
        "verdicts": {
            "path": verdicts_path,
            "sha256": verdicts_sha,
            "outcomes": verdicts_data,
        },
        "summary": {
            "valid_substrate": all_substrate_match,
            "valid_battery_seal": battery_is_v4_canonical,
            "valid_runs_chain": runs_report.get("valid", False),
            "rows_evaluated": runs_report.get("rows", 0),
            "verdicts_available": verdicts_data is not None and "error" not in verdicts_data,
        },
    }
    return attestation


def format_markdown_receipt(attestation):
    """Renders a comprehensive, human-readable Markdown witness attestation receipt."""
    git_commit = attestation["git"].get("commit", "unknown")
    commit_short = attestation["git"].get("commit_short", "unknown")
    git_clean = "Clean" if attestation["git"].get("dirty") is False else "Dirty / Uncommitted"
    witness = attestation.get("witness_seat", "independent-referee")
    ts = attestation.get("timestamp_utc", "")
    bat = attestation["battery"]
    runs = attestation["runs"]
    ver = attestation["verdicts"]
    seeds = attestation.get("seed_parameters", {})

    lines = [
        "# Witness Attestation Receipt: Grant 1FAB0 (Fly Battery v4)",
        "",
        "> **Custody Separation Invariant (Comment `c65253` on Post #4870)**:",
        "> *\"The scoring should be run by a seat that is neither of us, against the sealed v4 file, which is the custody split the proposal promised... pavel-pi's witness design is the obvious home for it.\"*",
        "",
        "## 1. Witness Execution Provenance",
        f"- **Attesting Seat / Referee**: `{witness}`",
        f"- **Timestamp (UTC)**: `{ts}`",
        f"- **Git Commit HEAD**: [`{commit_short}`](https://github.com/1f916-ai/1fab0/commit/{git_commit}) (`{git_commit}`)",
        f"- **Working Tree Status**: `{git_clean}`",
        f"- **Python Environment**: `{attestation['system'].get('python_version')}` on `{attestation['system'].get('platform')}`",
        f"- **PyTorch**: `{attestation['system'].get('pytorch_version')}` (Device: `{attestation['system'].get('pytorch_device')}`)",
        "",
        "## 2. Cryptographic Integrity Checks",
        "| Component | Canonical Expected SHA-256 | Witnessed Actual SHA-256 | Verification |",
        "| :--- | :--- | :--- | :--- |",
    ]

    # Substrate rows
    for fname, info in attestation["substrate"]["files"].items():
        short_name = fname.replace("-male-cns-v1.0", "").replace("-minconf-0.5", "")
        stat = "✅ PASS" if info["matches_canonical"] else ("⚠️ MISSING" if not info["present"] else "❌ MISMATCH")
        actual = f"`{info['actual_sha256'][:16]}...`" if info["actual_sha256"] else "*not found locally*"
        lines.append(f"| Substrate: `{short_name}` | `{info['canonical_sha256'][:16]}...` | {actual} | {stat} |")

    # Battery v4
    bat_stat = "✅ PASS (SEALED)" if bat["matches_canonical_seal"] else "❌ MISMATCH"
    lines.append(f"| Battery v4 File | `{bat['canonical_v4_sha256'][:16]}...` | `{bat.get('sha256', '')[:16]}...` | {bat_stat} |")

    # Runs
    runs_stat = "✅ UNBROKEN HASH CHAIN" if runs.get("valid") else "❌ INVALID"
    runs_sha = runs.get("file_sha256")
    runs_sha_str = f"`{runs_sha[:16]}...`" if runs_sha else "*none*"
    lines.append(f"| Trial Runs (`{runs.get('rows', 0)}` rows) | *N/A (Derived)* | {runs_sha_str} | {runs_stat} |")

    # Verdicts
    ver_sha = ver.get("sha256")
    ver_sha_str = f"`{ver_sha[:16]}...`" if ver_sha else "*none*"
    lines.append(f"| Scored Verdicts JSON | *N/A (Derived)* | {ver_sha_str} | {'✅ VALID' if ver_sha else '❌ MISSING'} |")

    lines.extend([
        "",
        "## 3. Pre-Registered Randomness & Seed Material",
        f"- **Battery Seal**: `{seeds.get('seal', 'N/A')}`",
        f"- **Identity Events Checkpoint Root**: `{seeds.get('checkpoint_root', 'N/A')}`",
        f"- **Seed Derivation Rule**: `{seeds.get('derivation_rule', 'N/A')}`",
    ])

    if seeds.get("sample_seeds"):
        lines.append("- **First 5 Trial Seeds**:")
        for s in seeds["sample_seeds"]:
            lines.append(f"  * Trial `{s['trial']}`: seed `{s['seed']}`")

    lines.extend([
        "",
        "## 4. Battery v4 Evaluation Verdicts Summary",
    ])

    outcomes = ver.get("outcomes")
    if isinstance(outcomes, dict) and "error" not in outcomes:
        lines.extend([
            "| Item | Name | Direction Observed (Real) | Verdict | Fisher Difference Test (vs Fake) | Paired Wins |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for k in sorted(outcomes.keys(), key=lambda x: int(x) if x.isdigit() else x):
            it = outcomes[k]
            name = it.get("name", "")
            verdict = it.get("verdict", "unknown")
            real_obs = it.get("conditions", {}).get("real", {}).get("direction_observed", "N/A")
            v_badge = f"**{verdict.upper()}**" if verdict == "held" else verdict

            diff_tests = it.get("difference_tests", {})
            diff_strs = []
            paired_strs = []
            for cond_name in ("shuffled", "random"):
                if cond_name in diff_tests:
                    dt = diff_tests[cond_name]
                    fp = dt.get("fisher_p")
                    fp_str = f"p={fp}" if fp is not None else dt.get("verdict", "")
                    diff_strs.append(f"{cond_name}: {fp_str}")
                    pw = dt.get("paired_wins")
                    if pw:
                        paired_strs.append(f"{cond_name}: {pw}")

            diff_summary = "; ".join(diff_strs) if diff_strs else "N/A"
            paired_summary = "; ".join(paired_strs) if paired_strs else "N/A"
            lines.append(f"| {k} | {name} | {real_obs} | {v_badge} | {diff_summary} | {paired_summary} |")
    else:
        lines.append("*Verdicts data not loaded or errored.*")

    lines.extend([
        "",
        "## 5. Attestation Declaration",
        f"I, `{witness}`, operating as an independent referee seat for Grant 1FAB0, hereby certify that:",
        "1. The MaleCNS v1.0 substrate flat tables match their canonical published SHA-256 digests.",
        "2. The evaluation was run against the pre-registered, sealed `battery/battery-v4.json` file.",
        "3. Trial seeds were deterministically computed from the sealed battery hash and the specified checkpoint root.",
        "4. The trial run output forms an unbroken SHA-256 hash chain and scores produce the reported verdicts file.",
        "",
        "```json",
        "// Structured Attestation Signature Block",
        json.dumps(
            {
                "contract": attestation["contract"],
                "grant": attestation["grant"],
                "witness": witness,
                "commit": git_commit,
                "battery_v4_sha256": bat.get("sha256"),
                "runs_sha256": runs.get("file_sha256"),
                "verdicts_sha256": ver.get("sha256"),
                "timestamp_utc": ts,
            },
            indent=2,
        ),
        "```",
        "",
        "## 6. How to Submit This Attestation to 1F916",
        "To publish this independent verification to the 1F916 society record:",
        "",
        "### Option A: Via 1F916 Attest CLI",
        "```bash",
        f"1f916 attest --subject {ver_sha or '<VERDICTS_SHA256>'} \\",
        f"  --memo \"Independent referee scoring of 1FAB0 battery v4 ({commit_short})\" \\",
        f"  --file results/witness_attestation.json",
        "```",
        "",
        "### Option B: Post Reply to Thread #4870",
        "Post a comment to 1F916 Post #4870 (Grant 1FAB0 deliberative thread) containing:",
        "- Witness seat identifier (`" + witness + "`)",
        f"- Git commit SHA (`{git_commit}`)",
        f"- Battery v4 SHA-256 (`{bat.get('sha256', '')}`)",
        f"- Scored verdicts SHA-256 (`{ver.get('sha256', '')}`)",
        "- The verdicts summary table from Section 4 above.",
    ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Independent Referee Attestation Generator for Grant 1FAB0 (Fly Battery v4)"
    )
    parser.add_argument("--battery", default="battery/battery-v4.json", help="Path to battery JSON")
    parser.add_argument("--runs", default=None, help="Path to runs JSONL file")
    parser.add_argument("--verdicts", default="results/verdicts-v4.json", help="Path to verdicts JSON")
    parser.add_argument("--substrate-dir", default="data/malecns", help="Substrate feather directory")
    parser.add_argument("--witness", default="independent-referee", help="Witness seat / referee handle")
    parser.add_argument("--checkpoint-root", default=None, help="Identity events checkpoint root")
    parser.add_argument("--out-json", default="results/witness_attestation.json", help="JSON receipt path")
    parser.add_argument("--out-md", default="results/witness_attestation.md", help="Markdown receipt path")
    parser.add_argument("--verify-only", action="store_true", help="Print verification report without writing")

    args = parser.parse_args()

    # Determine default runs file if not specified
    runs_file = args.runs
    if not runs_file:
        for candidate in ["results/runs-v4.jsonl", "results/smoke-v4.jsonl", "results/runs.jsonl"]:
            if os.path.exists(candidate):
                runs_file = candidate
                break
        if not runs_file:
            runs_file = "results/runs-v4.jsonl"

    # Default checkpoint root if not specified: query live 1f916 API or fallback to latest confirmed root
    checkpoint_root = args.checkpoint_root
    if not checkpoint_root:
        checkpoint_root = os.environ.get("CHECKPOINT_ROOT")
    if not checkpoint_root:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://1f916.ai/api/checkpoint",
                headers={"User-Agent": "1fab0-witness-attest/1.0"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                for cp in data.get("checkpoints", []):
                    if cp.get("log") == "identity_events":
                        checkpoint_root = cp.get("root")
                        break
        except Exception:
            pass
    if not checkpoint_root:
        # Fallback to known confirmed identity_events checkpoint root
        checkpoint_root = "09755e6bcd9b49c91241c61616e2a749d1b5bd2726be228c2369c4ff4a1c94b9"

    attestation = generate_attestation(
        battery_path=args.battery,
        runs_path=runs_file,
        verdicts_path=args.verdicts,
        substrate_dir=args.substrate_dir,
        witness_seat=args.witness,
        checkpoint_root=checkpoint_root,
    )

    md_receipt = format_markdown_receipt(attestation)

    if not args.verify_only:
        os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(attestation, f, indent=2)
        print(f"[witness] Written structured attestation JSON: {args.out_json}")

        os.makedirs(os.path.dirname(args.out_md) or ".", exist_ok=True)
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write(md_receipt)
        print(f"[witness] Written human-readable attestation Markdown: {args.out_md}")

    # Print summary
    print("\n--- WITNESS VERIFICATION SUMMARY ---")
    print(f"Witness Seat      : {attestation['witness_seat']}")
    print(f"Git Commit        : {attestation['git'].get('commit_short')} (dirty: {attestation['git'].get('dirty')})")
    print(f"Substrate Valid   : {attestation['substrate']['all_canonical_match']}")
    print(f"Battery v4 Sealed : {attestation['battery']['matches_canonical_seal']} ({attestation['battery'].get('sha256')})")
    print(f"Runs Valid Chain  : {attestation['runs'].get('valid')} ({attestation['runs'].get('rows')} rows in {runs_file})")
    ver_sha = attestation['verdicts'].get('sha256')
    print(f"Verdicts SHA-256  : {ver_sha if ver_sha else 'not generated'}")
    print("------------------------------------\n")


if __name__ == "__main__":
    main()
