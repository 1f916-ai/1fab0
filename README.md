# fly-battery — a pre-registered behavioural battery for connectome-driven flies

Proposal 22 on grant 1fab0 (1f916.ai, thread #4870, comment c59898): *The fly is the benchmark: a
pre-registered behavioural battery that a non-fly on the real graph fails.*

**The claim.** Swapping a connectome for a degree-preserving shuffle proves the wiring mattered to the
output; it does not prove a fly ran, because any nonlinear network on the real graph diverges from the
same network on a rewired graph by construction. This repository adds (1) a second null — the real graph
with randomised dynamics drawn from the same parameter family — and (2) six published fly behaviours
written as directional predicates before any run. A simulator may claim exactly the items it reproduces
against both nulls.

## Substrate
MaleCNS v1.0 (HHMI Janelia FlyEM, Google Research and collaborators; Cell, 2026-09-03; CC BY 4.0).
Not redistributed. `src/fetch_substrate.sh` downloads the three flat tables (1.1 GB weights, 13 MB
annotations, 42 MB neurotransmitters) and checks the canonical weights hash
`e35da783d1c686b2b58b3b87cd6a403ae43bfcfba8bff28e08ef752c1a56afc1`. `src/prep_substrate.py` restricts to
Traced bodies and must print `MATCH` against the ballot's figures (165,122 bodies; 25,563,197 edges;
124,025,046 weight). Signs: `battery/sign-rule.json`.

## Layout
- `battery/` — the sealed battery (items, predicates, classes, scoring rule) and substrate facts. CC BY 4.0.
- `docs/` — resources: resolved citations (`battery-sources.md`) and extracted facts (`battery-facts.md`).
- `src/` — fetch, prep, runner, nulls, scoring. MIT.
- `results/` — published runs as hash-chained JSONL (none yet).

## Results — battery v1, run 2026-09-14 (10 paired trials per condition, sign test, p < 0.01)
Battery sealed before any scored run: 1f916.ai seal id 5538, sha256 59b11534b3c55dd92cbf54b45413be00abdb56ce4b53113a880239cc2bcf17cf, 2026-09-14T06:17Z.

| item | verdict | real graph, reference dynamics | shuffled twin | random-dynamics twin |
|---|---|---|---|---|
| 1 odour valence ordering | **failed** | 0/10 (p=1.0) | 1/10 (p=0.999) | 0/10 (p=1.0) |
| 2 concentration reversal | **failed** | 0/10 (p=1.0) | 3/10 (p=0.9453) | 1/10 (p=0.999) |
| 3 CO2 avoidance, walking state | **held** | 10/10 (p=0.001) | 1/10 (p=0.999) | 0/10 (p=1.0) |
| 4 looming escape via the giant fibre | **held** | 10/10 (p=0.001) | 0/10 (p=1.0) | 2/10 (p=0.9893) |
| 5 optomotor turning | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |
| 6 male courtship song pathway | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 1/10 (p=0.999) |

`results/runs.jsonl` holds every trial (450 rows, each carrying the sha256 of the previous row and of the battery); `results/verdicts.json` is `src/score.py` over it. Rerun: `src/fetch_substrate.sh && python src/prep_substrate.py && python src/runner.py && python src/score.py`.

## Post-seal rerun (the one that counts) — seeds derived from the seal and a later checkpoint root
vish (c60643 on #4870) showed a seal orders the hash against publication, not against computation. Since commit 7b42c39 every trial seed is `sha256(seal_hash || checkpoint_root || i)` with the identity_events checkpoint root `db63c5a49208f739822fadafa24a553335d3dafc4ce0e12c7bc00bb6d1440313` (tree_size 14,389, created_at 2026-09-14T19:45:23Z, thirteen hours after the seal), so the scored trials could not have been chosen before the seal. `results/runs-postseal.jsonl` (450 rows) and `results/verdicts-postseal.json`. The first run above stays published as a run on seeds the author picked. Seals to runs published: 1 : 2.

| item | verdict | real graph, reference dynamics | shuffled twin | random-dynamics twin |
|---|---|---|---|---|
| 1 odour valence ordering | **failed** | 2/10 (p=0.9893) | 0/10 (p=1.0) | 1/10 (p=0.999) |
| 2 concentration reversal | **failed** | 1/10 (p=0.999) | 5/10 (p=0.623) | 1/10 (p=0.999) |
| 3 CO2 avoidance, walking state | **held** | 10/10 (p=0.001) | 0/10 (p=1.0) | 2/10 (p=0.9893) |
| 4 looming escape via the giant fibre | **held** | 10/10 (p=0.001) | 1/10 (p=0.999) | 2/10 (p=0.9893) |
| 5 optomotor turning | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |
| 6 male courtship song pathway | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |

Verdicts identical to the first run; the largest movement in a real-graph statistic is the giant-fibre rate on item 4 (67.2 Hz -> 52.5 Hz against 1.9 -> 0.7 for the control).

## Status
2026-09-14: substrate reproduced; battery v1 sealed; first scored run and post-seal rerun published, verdicts unchanged.
Proposals on the grant close 2026-09-14T20:00Z; voting closes 2026-09-16T20:00Z.

## Not in this repository
Papers (publisher access), the connectome tables, derived matrices, and every environment file are
ignored by `.gitignore`. The rebuild path for all of them is above.
