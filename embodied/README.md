# Embodied: the MaleCNS nerve cord walking a physics fly

Local work from the night of 2026-09-17. Not pushed.

## The question

A connectome gives wiring, not the strength with which each family of neurons drives its targets. Can a small, interpretable set of those missing numbers make the mapped nerve cord produce walking in a body? And does the result hold on behaviour it was never trained on, where scrambled wiring fails?

## Pipeline

1. **Nerve cord model.** A reimplementation of the rate model from Pugliese, Tuthill & Brunton 2025 (MIT), in `vnc_rate.py`. It runs on the MaleCNS v1.0 nerve cord: 14,750 neurons on descending-to-motor pathways across all six legs (`malecns_cpg.py`). `replicate_pugliese.py` reproduces their MANC-T1 DNg100 rhythm first.
2. **Search.** CMA-ES over 41 natural-log gains (`evolve.py`, batched on MPS): 37 hemilineage output gains (36 named plus unlabelled), descending neurons, motor neurons, and global excitation and inhibition. Each candidate is scored on two random neuron-parameter draws (seeds 0–1).
   - Stage 1 (`v1`): tripod coordination, rhythm and flexor–extensor alternation, over 0.8 s.
   - Stage 2 (`v2`): adds left–right stride balance and per-leg evenness.
   - Stage 3 (`v3`): 3 s trials, and adds left–right phase locking.
   - Each stage ran identically on degree-preserving scrambled wiring with the same budget.
3. **Body.** NeuroMechFly on FlyGym 2.1 with MuJoCo (`walker.py`).
   - Step shape: single-leg steps recorded from real walking flies (`PreprogrammedSteps`).
   - Step timing and inter-leg coordination: the phase of (Tr flexor − Sternotrochanter) motor-neuron activity per leg (`neural_phases.py`).
   - No hand-written rhythm generator.

## Held-out results

All results below use neuron-parameter draws 100–109, never used in training. Details are in `results/heldout*/report.json` and `../../OVERNIGHT.md`.

| Test | Evolved (real wiring) | Scrambled wiring, same search | Published parameters |
|---|---|---|---|
| Straight fast walking in the body (>5 mm/s, <10° drift over 3.5 s), stage 3 | **7/10** (7.0–8.4 mm/s) | 0/10 (≤2.0 mm/s) | 0/10 (≤1.4 mm/s) |
| Steering in the body, DNa02 left vs right, never trained, stage 3 | **12/12 turns correct; L−R heading +149° mean** | 1/6 correct sign, −17° | inconsistent, barely moving |
| DN screen: 84 labelled types, walking vs not (AUC), stage 3 | **0.74 (perm p 0.0002)** | 0.63 (p 0.036) | 0.59 (p 0.098) |
| Tripod index, stage 1 | **0.96 ± 0.02** | 0.06 ± 0.25 | 0.09 ± 0.25 |
| Tripod index, stage 3 | 0.75 ± 0.47 (2/10 draws fail) | 0.15 ± 0.21 | 0.09 ± 0.25 |

## Finding

With tuned gains, each side of the nerve cord locks its own three legs, but the two sides step at slightly different rates (for example 6.01 vs 5.91 Hz). They drift apart over seconds, so the tripod dissolves and the fly curves. In this model the coupling across the midline is the weak link. Rewarding left–right locking over 3 s fixed straight walking on 7 of 10 unseen draws, and steering emerged without being trained.

## Limits

- No electrical synapses, neuromodulation, plasticity or proprioceptive feedback. The brain above the neck is not simulated; commands are forced descending-neuron input.
- Step shape is replayed from recordings.
- Several gains sit at the ±2 search bound.
- Robustness traded down between stage 1 and stage 3.
- Step rate is about 6–7 Hz. We have not compared it quantitatively against real flies yet.
