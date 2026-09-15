#!/usr/bin/env python3
"""Score results/runs.jsonl against battery/battery.json. Per item and condition: the per-trial statistic
(difference of decoded readouts between the named stimuli), a one-sided sign test over paired trials
(binomial, p < 0.01), and the pass condition: held if the direction holds in the real graph with reference
dynamics AND does not hold in the shuffled twin AND does not hold in the random-dynamics twin.
Verdicts per item: held | failed | unreadable (a needed row is missing) | not-run."""
import json, sys, math, collections
from itertools import groupby
ALL = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else 'results/runs.jsonl')]
STEP = float(sys.argv[2]) if len(sys.argv) > 2 else None   # v3: score the random arm at one sweep step (multiplier); real/shuffled rows have step None
runs = [r for r in ALL if r.get('condition') != 'random' or r.get('step') == STEP or (STEP is None and r.get('step') is None)]
B = json.load(open('battery/battery.json'))
def hz(row, k): r = row['readouts'][k]; return r['stimulus_hz'] - r['baseline_hz']
def approach(row): return hz(row, 'DNp09') - hz(row, 'MDN')
def get(item, cond, trial, stim):
    for r in runs:
        if r['item'] == item and r['condition'] == cond and r['trial'] == trial and r['stimulus'] == stim: return r
def stats(item, cond):
    """list of per-trial booleans 'predicate direction observed' and the per-trial statistic values"""
    trials = sorted({r['trial'] for r in runs if r['item'] == item and r['condition'] == cond}); obs = []; vals = []
    for t in trials:
        g = lambda s: get(item, cond, t, s)
        try:
            if item == 1:
                a, nn, rp = approach(g('attractant')), approach(g('neutral')), approach(g('repellent')); obs.append(a > nn and nn > rp); vals.append([a, nn, rp])
            elif item == 2:
                lo, hi = approach(g('low')), approach(g('high')); obs.append(lo > hi); vals.append([lo, hi])
            elif item == 3:
                c, z = approach(g('co2')), approach(g('none')); obs.append(c < z); vals.append([c, z])
            elif item == 4:
                l, c = hz(g('loom'), 'DNp01'), hz(g('control_visual'), 'DNp01'); obs.append(l > c); vals.append([l, c])
            elif item == 5:
                ra, rb = g('right_a'), g('right_b'); ha = hz(ra, 'HS_R') - hz(ra, 'HS_L'); hb = hz(rb, 'HS_R') - hz(rb, 'HS_L'); da = hz(ra, 'DNa02_R') - hz(ra, 'DNa02_L'); db = hz(rb, 'DNa02_R') - hz(rb, 'DNa02_L')
                obs.append(ha * hb < 0 and da * db < 0); vals.append([ha, hb, da, db])
            elif item == 6:
                ft, cv, no = g('female_taste'), g('cva'), g('none'); obs.append(hz(ft, 'pC1') > hz(no, 'pC1') and hz(ft, 'pIP10') > hz(no, 'pIP10') and hz(cv, 'pC1') <= hz(no, 'pC1')); vals.append([hz(ft, 'pC1'), hz(no, 'pC1'), hz(cv, 'pC1'), hz(ft, 'pIP10'), hz(no, 'pIP10')])
        except (TypeError, AttributeError): return None
    return obs, vals
def sign_test(obs):
    k = sum(obs); m = len(obs); p = sum(math.comb(m, i) for i in range(k, m + 1)) / 2 ** m; return k, m, p
out = {}
for it in B['items']:
    i = it['id']; rec = {'name': it['name'], 'conditions': {}}
    for cond in ('real', 'shuffled', 'random'):
        s = stats(i, cond)
        if s is None or not s[0]: rec['conditions'][cond] = {'verdict': 'unreadable' if s is None else 'not-run'}; continue
        k, m, p = sign_test(s[0]); rec['conditions'][cond] = {'direction_observed': f'{k}/{m}', 'p_one_sided': round(p, 4), 'holds': p < 0.01, 'mean_stats': [round(sum(v[j] for v in s[1]) / m, 3) for j in range(len(s[1][0]))]}
    c = rec['conditions']
    if all(x.get('verdict') in ('unreadable', 'not-run') for x in c.values()): rec['verdict'] = 'not-run'
    elif any('holds' not in x for x in c.values()): rec['verdict'] = 'unreadable'
    else: rec['verdict'] = 'held' if (c['real']['holds'] and not c['shuffled']['holds'] and not c['random']['holds']) else 'failed'
    rec['real_only'] = bool(c.get('real', {}).get('holds'))
    out[str(i)] = rec
json.dump(out, open('results/verdicts.json' if STEP is None else 'results/verdicts-step-%g.json' % STEP, 'w'), indent=1)
for i, r in out.items(): print(i, r['name'], '->', r['verdict'], {k: (v.get('direction_observed'), v.get('holds')) for k, v in r['conditions'].items()})
