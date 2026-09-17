#!/bin/zsh
# Embodied straight walking on held-out neuron draws. Usage: STAGE=_v2 ./straightness.sh evolved_real
cd ~/fly-data/work; m=$1
for sd in ${=SEEDS:-100 101 102 103 104}; do
  ~/fly-data/.venv/bin/python neural_phases.py --model $m --seed $sd --T 4.0 --stim DNg100 --out body/straight${STAGE}_${m}_s${sd}.npz 2>&1 | grep -v "Warn\|sparse_coo\|return torch" > /dev/null
  ~/fly-data/.venv312/bin/python body_from_phases.py body/straight${STAGE}_${m}_s${sd}.npz 2>&1 | grep speed
done
