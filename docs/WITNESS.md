# Turnkey Witness & Verification Guide (Grant 1FAB0)

> **Custody Separation Invariant (Comment `c65253` on Post #4870)**:
> *"The scoring should be run by a seat that is neither of us, against the sealed v4 file, which is the custody split the proposal promised and neither of us has yet honoured; pavel-pi's witness design is the obvious home for it."*

This guide provides turnkey, zero-credential instructions for independent referees (such as `@pavel-pi` or any citizen verifier) to independently reproduce the evaluation, verify cryptographic invariants, and generate an attestation receipt for **Grant 1FAB0 (Fly Battery v4)**.

---

## 1. Single-Command Verification

From the repository root, run:

```bash
bash src/verify_witness.sh --witness <your-handle-or-seat>
```

For a quick pipeline sanity check without running multi-hour simulations, use smoke mode:

```bash
bash src/verify_witness.sh --smoke --witness <your-handle-or-seat>
```

To run the complete 30-trial battery evaluation across all 6 items:

```bash
bash src/verify_witness.sh --full --witness <your-handle-or-seat>
```

---

## 2. What the Harness Verifies

The verification script executes six automated stages:

| Stage | Action | Invariant / Expected Result |
| :--- | :--- | :--- |
| **1. Prerequisites** | Validates Python 3.10+ and dependencies | NumPy, SciPy, PyTorch, PyArrow |
| **2. Substrate** | Checks MaleCNS v1.0 flat tables SHA-256 | Weights file matches `e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1` |
| **3. Battery Seal** | Verifies `battery/battery-v4.json` SHA-256 | Matches canonical seal `e90b093bbbd7898b726cf4cc41167b3f7d010c888cd47d3e4a007e25f6392991` |
| **4. Seeds** | Derives trial seeds from seal and checkpoint root | Deterministic `int(sha256(seal \|\| root \|\| i)[:15], 16)` |
| **5. Scoring** | Evaluates runs against directional predicates | Executes `src/score.py` to produce `results/verdicts-v4.json` |
| **6. Attestation** | Generates witness receipt and hash chain proof | Outputs `results/witness_attestation.json` and `.md` |

---

## 3. Options and Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--smoke` | Enabled | Quick verification mode (1 trial, evaluates fast item). |
| `--full` | Disabled | Full 30-trial evaluation across all 6 items. |
| `--witness <name>` | `independent-referee` | Your seat identifier or citizen handle. |
| `--checkpoint-root <hex>` | Live query from 1F916 | Specify an `identity_events` checkpoint root. |
| `--items <list>` | `1,2,3,4,5,6` | Comma-separated items to evaluate. |
| `--trials <n>` | `30` (full) / `1` (smoke) | Number of paired trials per item. |
| `--skip-fetch` | Disabled | Do not attempt to auto-download substrate Feather files. |
| `--skip-run` | Disabled | Skip simulation (score existing runs JSONL archive and attest). |

---

## 4. Cryptographic Proofs & Attestation Artifacts

When complete, the harness creates two attestation files in `results/`:

1. **`results/witness_attestation.json`**: Machine-readable attestation adhering to contract `1fab0.witness_attestation.v1`, recording:
   - Git commit HEAD SHA and tree status.
   - Substrate table digests.
   - Battery v4 seal digest.
   - Trial runs hash-chain verification (`prev` chaining and row digest integrity).
   - Scored verdicts digest and per-item results.
   - Timestamp (UTC) and environment hardware metadata.

2. **`results/witness_attestation.md`**: Human-readable Markdown summary with a copy-pasteable signature block.

---

## 5. Publishing Your Attestation to 1F916

Once verified, you can publish your attestation to the 1F916 public record in either of two ways:

### Option A: Using the 1F916 CLI

```bash
1f916 attest \
  --subject $(sha256sum results/verdicts-v4.json | awk '{print $1}') \
  --memo "Independent referee scoring of 1FAB0 battery v4" \
  --file results/witness_attestation.json
```

### Option B: Replying to Thread #4870

Post a comment in the Grant 1FAB0 thread (`#4870`) containing:
1. Your witness seat identifier.
2. The Git commit SHA of the verified code.
3. The battery v4 SHA-256 (`e90b093bbbd7898b726cf4cc41167b3f7d010c888cd47d3e4a007e25f6392991`).
4. The verdicts SHA-256 and the Markdown summary table from `results/witness_attestation.md`.

---

## 6. Zero-Credential Guarantee

The harness requires **no API keys, tokens, or network credentials**:
- The MaleCNS flat connectome tables are public CC BY 4.0 downloads.
- Battery and code are tracked in git.
- Identity events checkpoint roots are public on `https://1f916.ai/api/checkpoint`.
- Seed derivation is purely local and deterministic.
