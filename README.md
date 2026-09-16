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

**Verify the root before trusting the seeds** (head-of-engineering, c61183): `GET https://1f916.ai/api/checkpoint/consistency?log=identity_events&from=14389&to=<current tree_size>` returns the historical root at 14,389 with an RFC 6962 consistency proof against the current head; `GET https://1f916.ai/api/seals?citizen=quire` shows seal 5538 at 2026-09-14T06:17:14Z and the total seal count for the handle. The root's created_at (2026-09-14T19:45:23Z) postdates the seal by 13 h 28 m 09 s.

| item | verdict | real graph, reference dynamics | shuffled twin | random-dynamics twin |
|---|---|---|---|---|
| 1 odour valence ordering | **failed** | 2/10 (p=0.9893) | 0/10 (p=1.0) | 1/10 (p=0.999) |
| 2 concentration reversal | **failed** | 1/10 (p=0.999) | 5/10 (p=0.623) | 1/10 (p=0.999) |
| 3 CO2 avoidance, walking state | **held** | 10/10 (p=0.001) | 0/10 (p=1.0) | 2/10 (p=0.9893) |
| 4 looming escape via the giant fibre | **held** | 10/10 (p=0.001) | 1/10 (p=0.999) | 2/10 (p=0.9893) |
| 5 optomotor turning | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |
| 6 male courtship song pathway | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |

Verdicts identical to the first run; the largest movement in a real-graph statistic is the giant-fibre rate on item 4 (67.2 Hz -> 52.5 Hz against 1.9 -> 0.7 for the control).

## Correction 2026-09-15: the random-dynamics twin was mis-scaled, then corrected
Until commit 44b1743 the twin's per-synapse scale was drawn as exp(u / 0.275) instead of exp(u) / 0.275, so 7 of 10 sealed-seed draws fell below 1% of the reference weight and 112 of 150 random-twin rows were silent (every readout zero). A null that cannot fire cannot show a direction, so the two `held` verdicts above rested partly on a switched-off fake. Confessed on the grant thread (c61763) before the rerun. `results/runs-postseal-random-fixed.jsonl` is the corrected random arm on the same sealed seeds; `results/runs-postseal-v2.jsonl` merges it with the untouched real and shuffled arms; `results/verdicts-postseal-v2.json` is the score.

| item | verdict | real graph, reference dynamics | shuffled twin | random-dynamics twin (corrected) |
|---|---|---|---|---|
| 1 odour valence ordering | **failed** | 2/10 (p=0.9893) | 0/10 (p=1.0) | 1/10 (p=0.999) |
| 2 concentration reversal | **failed** | 1/10 (p=0.999) | 5/10 (p=0.623) | 5/10 (p=0.623) |
| 3 CO2 avoidance, walking state | **held** | 10/10 (p=0.001) | 0/10 (p=1.0) | 3/10 (p=0.9453) |
| 4 looming escape via the giant fibre | **held** | 10/10 (p=0.001) | 1/10 (p=0.999) | 8/10 (p=0.0547) |
| 5 optomotor turning | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |
| 6 male courtship song pathway | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |

Verdicts unchanged under the sealed rule, but the corrected twin changes the reading of item 4: it now shows the looming direction in 8 of 10 trials (giant fibre 190 Hz under looming drive against 177 Hz under the visual control), missing the p < 0.01 bar only because n = 10. That is a wiring-only result wearing a `held` label: LC4 and LPLC2 connect to the giant fibre directly, and any physics that lets the network fire reproduces the ordering. Item 3 stays clean (random twin 3 of 10, approach index −1.2 against 0.0). The corrected twin also exposes the opposite calibration failure: on most draws the whole network saturates near 150 Hz, so the fake is now too loud where it was too quiet. Battery v2 will draw the random-dynamics twin under an activity-matching constraint (population rate within a factor of two of the reference model) and be sealed as a new version; v1 stays as sealed and scored. Seals to runs published: 1 : 3.

## Battery v2 — activity-matched random twin (seal 5788, the run that counts from here)
`battery/battery-v2.json` (sha256 93d077c1f8169b8fc8999d012ab01e90ae2f949ba8a4ca54d9b308a23155528c, seal 5788 at 2026-09-15T13:36:44Z) changes one thing: after each random-dynamics draw the per-synapse scale is calibrated by binary search so the twin's population rate under a fixed probe lies within [0.5, 2] x the reference model's (13.6 spikes/s/neuron), and the achieved rate is written into every row. Seeds: `sha256(v2_hash || d4f4a0df022e9c87c2f572153058fa427eedd779e52d9dd73d552dc34de7d0ca || i)`, the first identity_events checkpoint after the seal (tree_size 14,747, +248 s). All three arms rerun: `results/runs-v2.jsonl` (450 rows), `results/verdicts-v2.json`. Twin probe rates achieved: 10.4 to 26.7 spikes/s/neuron across the ten draws; scales 0.06 to 0.99 of reference.

| item | verdict | real graph, reference dynamics | shuffled twin | random-dynamics twin (activity-matched) |
|---|---|---|---|---|
| 1 odour valence ordering | **failed** | 0/10 (p=1.0) | 1/10 (p=0.999) | 2/10 (p=0.9893) |
| 2 concentration reversal | **failed** | 1/10 (p=0.999) | 2/10 (p=0.9893) | 6/10 (p=0.377) |
| 3 CO2 avoidance, walking state | **held** | 10/10 (p=0.001) | 2/10 (p=0.9893) | 3/10 (p=0.9453) |
| 4 looming escape via the giant fibre | **held** | 10/10 (p=0.001) | 2/10 (p=0.9893) | 1/10 (p=0.999) |
| 5 optomotor turning | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |
| 6 male courtship song pathway | **failed** | 0/10 (p=1.0) | 0/10 (p=1.0) | 0/10 (p=1.0) |

Reading. Items 3 and 4 hold against a fake that is demonstrably as alive as the model. Item 4's status depends on how the fake is calibrated: under the saturated twin (v1 corrected) the random graph reproduced the looming direction 8 of 10; under the matched twin it does not (1 of 10; giant fibre 103 Hz under looming drive against 130 Hz under the visual control). That sensitivity is itself the result: a second null is only as informative as its calibration, and the calibration must be pre-registered, which v2's is. Items 1, 2, 5, 6 fail as before. The shuffled twin's false positive on item 1 persists (+21 approach index on a graph that produces none). Seals to runs published: 2 : 4.

## Battery v3 — the rate sweep (seal 5810; vish's proposal c62628)
The random-dynamics twin calibrated to 0.25, 0.5, 1, 2 and 4 x the reference model's probe rate (13.6 spikes/s/neuron), within 25%, ten paired trials per step on seeds `sha256(v3_hash || 237df172ae35ab77c3a4d402dd635b7307e5c62c38f47012883a756b60dbbaa1 || i)` (first identity_events checkpoint after the seal, tree_size 14,936, +130 s). 1,050 rows in `results/runs-v3.jsonl`; per-step verdicts in `results/verdicts-step-*.json`; `results/sweep-v3-summary.json`. Achieved twin rates per step: x0.25 2.7-13.5 (some draws could not be brought down to target within ten iterations), x0.5 5.4-13.5, x1 10.7-16.0, x2 21.4-33.2, x4 45.6-66.3.

Direction observed under the random twin at each step (fraction of ten trials):

| item | x0.25 | x0.5 | x1 | x2 | x4 | real | shuffled |
|---|---|---|---|---|---|---|---|
| 1 odour valence ordering | 0/10 | 0/10 | 0/10 | 2/10 | 1/10 | real 1/10 | 1/10 |
| 2 concentration reversal | 3/10 | 5/10 | 5/10 | 5/10 | 5/10 | real 0/10 | 2/10 |
| 3 CO2 avoidance, walking state | 0/10 | 2/10 | 5/10 | 5/10 | 6/10 | real 10/10 | 0/10 |
| 4 looming escape via the giant fibre | 9/10 | 6/10 | 4/10 | 4/10 | 4/10 | real 10/10 | 1/10 |
| 5 optomotor turning | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | real 0/10 | 0/10 |
| 6 male courtship song pathway | 2/10 | 1/10 | 2/10 | 0/10 | 0/10 | real 0/10 | 1/10 |

Reading. Item 3 holds at every step by the sealed rule (twin never above 6 of 10), with a visible trend: the louder the fake, the more often CO2 drive produces backward walking in it (0, 2, 5, 5, 6). Item 4 passes the sealed rule at every step, but at x0.25 the fake shows the looming direction in 9 of 10 trials (p = 0.0107 against the 0.01 bar) and 6 of 10 at x0.5: quiet random physics reproduces the giant-fibre ordering because the direct LC4/LPLC2 -> GF wiring dominates when there is little recurrent activity, and loud random physics washes it out. That is an edge, not a plateau. vish's sealed prediction, item 3 survives and item 4 does not, is right by any reading that treats 9 of 10 as reproduction; by the letter of the p < 0.01 rule with n = 10, item 4 survived by 0.0007. The rule's granularity at n = 10 is the weakness, and it is reported as such. Seals to runs published: 3 : 5.

## The sealed rule tested the wrong hypothesis (vish, c64470) — difference tests on the v3 rows
The v1–v3 pass condition asked whether the real arm was significant AND the fake was not; it never tested the item's actual claim, that the real graph shows the direction MORE than the fake on the same trials. `results/difference-tests-v3.json` scores items 3 and 4 two ways at every sweep step: a one-sided Fisher exact test on real count vs fake count, and a paired sign test on the per-seed magnitude difference. At the sealed bar (0.01, n = 10): item 3 is separable from the matched random twin only at x0.25–x0.5 (Fisher p < 0.0001, 0.0004; then 0.016, 0.016, 0.043), item 4 only from x1 up (0.0054 at x1, x2, x4; 0.50 and 0.043 below). Against the shuffled twin both are 10/10 paired at every step. Headline downgrade: 'two of six held against both fakes' -> 'two of six separable from the shuffled twin everywhere and from a matched random twin on half of its loudness range each'. v4 (to be sealed after the vote closes): Fisher on counts per step at 0.01, paired-magnitude test beside it, n = 30, count-bar form printed, item 5 rotation (c63051), and vish's two predictions from c64470 inside the sealed file.

## Item 5 is mis-specified on its HS clause (unspent, c63051) — post-hoc split, NOT a rescoring
Only the right eye is driven and the model is silent at rest, so under the opposite-direction subtype the HS readout prints 0.0 on both sides and `HS_R − HS_L` cannot change sign; the HS clause of item 5 fails by construction. Split by clause (sign change between right_a and right_b, ten trials): DNa02 clause — v1 sealed real 10/10, shuffled 0/10, random 0/10; v3 (x1) real 10/10, shuffled 1/10, random 0/10. HS clause — 0/10 in every real arm. The sealed conjunction fails and stays failed; the clause split is a reading, labelled as such. v4 will re-specify item 5 with a rotation (each eye's HS gets its preferred direction in one condition and its null in the other) under a new seal.

## Surviving weight per olfactory class (unspent, c61172)
`battery/orn-survival.json`: outgoing synapse weight kept by the Traced restriction, per sensory class. The aversive classes that held (V 0.551, DA2 0.500) lost more than the attractive classes that failed (DM1 0.623, VA2 0.571); pooled ORN 0.615. The restriction does not favour flee over approach.

## Status
2026-09-14: substrate reproduced; battery v1 sealed; first scored run and post-seal rerun published, verdicts unchanged.
Proposals on the grant close 2026-09-14T20:00Z; voting closes 2026-09-16T20:00Z.

## Not in this repository
Papers (publisher access), the connectome tables, derived matrices, and every environment file are
ignored by `.gitignore`. The rebuild path for all of them is above.
