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

## Status
2026-09-14: substrate reproduced; classes located; sources resolved; battery file and runner in progress.
Proposals on the grant close 2026-09-14T20:00Z; voting closes 2026-09-16T20:00Z.

## Not in this repository
Papers (publisher access), the connectome tables, derived matrices, and every environment file are
ignored by `.gitignore`. The rebuild path for all of them is above.
