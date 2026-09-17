# Connectome Evaluation Viewer & Trial Replayer

An interactive 2D simulation arena, dual-decoder comparator, and JSONL trial replayer for Grant 1FAB0 (`1f916-ai/1fab0`).

The viewer provides an un-mocked visual interface to inspect evaluation runs, compare descending readouts side-by-side with continuous trajectory kinematics, and verify cryptographic hash chains across all six behavioral items.

## Deployments & Quick Start

### 1. GitHub Pages (Zero-Dependency Static Web)
The viewer is hosted statically via GitHub Pages directly from `docs/`:
```
https://1f916-ai.github.io/1fab0/
```
No Python backend, Node.js server, or external build step is required. The page ships with a self-contained 36-trial benchmark covering all six items across real, degree-shuffled, and random-dynamics twins.

### 2. Local Viewer Server
To serve local run datasets (`results/*.jsonl`) dynamically, run the standard library Python server:

```bash
# Launch server and open browser automatically on http://127.0.0.1:8080/
python3 src/viewer.py

# Specify custom port without launching browser
python3 src/viewer.py --port 9090 --no-browser

# Listen on all interfaces
python3 src/viewer.py --host 0.0.0.0 --port 8080
```

#### CLI Options
```
options:
  -h, --help            show this help message and exit
  --port, -p PORT       Port to bind server (default: 8080)
  --host, -H HOST       Host / interface to bind server (default: 127.0.0.1)
  --no-browser          Do not open web browser automatically (default: False)
  --docs-dir DOCS_DIR   Path to docs directory (static web root) (default: docs)
  --results-dir RESULTS_DIR
                        Path to results directory (default: results)
  --battery-dir BATTERY_DIR
                        Path to battery directory (default: battery)
```

The local server routes `/` to `docs/index.html`, `/results/<path>` to the repository `results/` folder, `/battery/<path>` to `battery/`, and provides an `/api/results` endpoint listing available trial files.

---

## The Six Behavioral Test Items

| Item | Name | Sensory Drivers | Readouts | Predicate / Behavioral Target |
|:---|:---|:---|:---|:---|
| **1** | Odour Valence Ordering | `ORN_DM1`, `ORN_VA2` (attractant) vs `ORN_DA2` (repellent) | `approach_index` (DNp09, MDN) | `approach_index(attractant) > neutral > repellent` |
| **2** | Concentration Reversal | Low 50 Hz vs High 150 Hz (`DM1`, `VA2`, `DM5`) | `approach_index` | Attraction at low concentration reverses to avoidance at high concentration |
| **3** | CO2 Walking Avoidance | `ORN_V` (50 Hz CO2 plume) | `approach_index` | `approach_index(co2) < approach_index(none)` (backward stepping via MDN) |
| **4** | Looming Visual Escape | `LC4`, `LPLC2` (expanding dark disc, $0 \to 150$ Hz) | `rate(DNp01)` | `rate(DNp01 \| loom) > rate(DNp01 \| control_visual)` (Giant Fibre leap) |
| **5** | Optomotor Yaw Steering | `T4`/`T5` (rotating vertical grating stripes: `rot_a`, `rot_b`) | `steer_asymmetry(HS)`, `steer_asymmetry(DNa02)` | Asymmetric turning changes sign between clockwise and counter-clockwise rotation |
| **6** | Male Courtship Song | `female_taste` (`ppk25` contact) vs `cva` (`ORN_DA1`) | `rate(pC1)`, `rate(pIP10)` | `rate(pC1, pIP10 \| female_taste) > rate(none)` (unilateral wing extension pulse song) |

---

## Dual-Decoder Comparative Architecture

The dashboard visualizes two complementary decoding strategies side-by-side:

### 1. Quire's Discrete Descending Decoder (Proposal 22 Baseline)
- **Forward/Backward Walking**: $\Delta \text{Hz} = \text{rate}(\text{DNp09}) - \text{rate}(\text{MDN})$
- **Optomotor Steering**: $\Delta \text{Hz} = \text{rate}(\text{DNa02\_R}) - \text{rate}(\text{DNa02\_L})$
- **Giant Fibre Escape**: $\text{rate}(\text{DNp01})$
- **Courtship Song**: $\text{rate}(\text{pC1})$ and $\text{rate}(\text{pIP10})$
- Linear difference readouts of named descending or motor classes without spatial embodiment.

### 2. Strata's Continuous Trajectory Decoder (Grant 1FAB0 Kinematics)
- **Kinematic Integration**: Integrates instantaneous descending spike rates into physical 2D motion $(x, y, \theta)$ over time:
  $$\nu(t) = \nu_{\text{scale}} \cdot (r_{\text{DNp09}}(t) - r_{\text{MDN}}(t))$$
  $$\omega(t) = \text{turn\_scale} \cdot (r_{\text{DNa02\_L}}(t) - r_{\text{DNa02\_R}}(t))$$
- **Metrics**:
  - Signed displacement: $dx = x_{\text{end}} - x_0$
  - Cumulative path length: $L = \sum_i \sqrt{\Delta x_i^2 + \Delta y_i^2}$
  - Chemotaxis Index: $CI = dx / L$
  - Path straightness: $S = \sqrt{dx^2 + dy^2} / L$

### The Anti-Clamping Metric Invariant
Signed displacement $dx$ and Chemotaxis Index $CI$ are unclipped: negative space ($dx < 0$, $CI < 0$) is strictly preserved without `max(0, ...)` clamping. Preserving negative values discriminates active retreat or repulsion (e.g. Item 3 CO2 avoidance) from quiescent paralysis ($L \approx 0$).

---

## Trial Replayer & Cryptographic Attestation

- **Data Sources**: Load built-in benchmarks, choose from repository runs (`smoke-v4.jsonl`, `smoke-v2.jsonl`, `runs-postseal-v2.jsonl`, `runs-v3.jsonl`), or drag-and-drop any custom `runs.jsonl`.
- **Playback Controls**: Play/pause (Spacebar), scrubber slider, frame stepping (-5f / +5f), trial navigation, and variable speed (0.5x, 1.0x, 2.0x).
- **Cryptographic Hash Chain**: Every row in `runs.jsonl` contains `prev` (SHA-256 of previous row or battery hash) and `sha256` (SHA-256 of current sorted row). The viewer contains a live hash-chain verifier checking cryptographic continuity across all loaded trials.

---

## Verification & Testing

Unit tests for the viewer CLI and HTTP request handling:
```bash
python3 -m unittest test_viewer.py
```
