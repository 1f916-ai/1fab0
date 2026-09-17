#!/bin/zsh
cd ~/fly-data/work
for m in evolved_real published_params evolved_scrambled; do
  for c in walk left right; do
    extra=""; stim="--stim DNg100"
    [ $c = left ] && stim="--stim DNa02 --side L --extra DNg100"
    [ $c = right ] && stim="--stim DNa02 --side R --extra DNg100"
    ~/fly-data/.venv/bin/python neural_phases.py --model $m --seed 100 --T 4.0 ${=stim} --out body/site_${m}_${c}.npz 2>&1 | grep -v "Warn\|sparse_coo\|return torch"
    ~/fly-data/.venv312/bin/python body_from_phases.py body/site_${m}_${c}.npz 2>&1 | grep -v "WARN\|warn"
    ~/fly-data/.venv312/bin/python ~/fly-data/site/build_run.py ${m}_${c} body/site_${m}_${c}.npz body/site_${m}_${c}_motion.npz body/site_${m}_${c}_body.json 2>&1 | tail -1
  done
done
echo ALL-RUNS-DONE
