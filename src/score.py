#!/usr/bin/env python3
"""Score results/runs.jsonl against the test battery. Per item and condition: the per-trial statistic
(difference of decoded readouts between the named stimuli), a one-sided sign test over paired trials
(binomial, p < 0.01), and the pass condition: held if the direction holds in the real graph with reference
dynamics AND does not hold in the shuffled twin AND does not hold in the random-dynamics twin.
Verdicts per item: held | failed | unreadable (a needed row is missing) | not-run.
v4: one-sided Fisher exact test on counts and paired-magnitude sign test comparing bio vs control deltas."""
import json, sys, os, math, collections, argparse
from itertools import groupby

def hz(row, k): r = row['readouts'][k]; return r['stimulus_hz'] - r['baseline_hz']
def approach(row): return hz(row, 'DNp09') - hz(row, 'MDN')
def get(item, cond, trial, stim):
    for r in runs:
        if r['item'] == item and r['condition'] == cond and r['trial'] == trial and r['stimulus'] == stim: return r

def magnitude(item, v):
    """Calculates directional effect size in the predicted direction for a trial.
    For compound conditions (item 5 sign flip product test, item 6 multi-clause conjunction with mixed signs),
    returns None to avoid masking or summing mismatched quantities."""
    if item == 1: return v[0] - v[2]
    elif item == 2: return v[0] - v[1]
    elif item == 3: return v[1] - v[0]
    elif item == 4: return v[0] - v[1]
    return None

def stats(item, cond):
    """list of per-trial booleans 'predicate direction observed' and the per-trial statistic values"""
    trials = sorted({r['trial'] for r in runs if r['item'] == item and r['condition'] == cond}); obs = []; vals = []; ts = []
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
                ra, rb = (g('rot_a'), g('rot_b')) if get(item, cond, t, 'rot_a') else (g('right_a'), g('right_b')); ha = hz(ra, 'HS_R') - hz(ra, 'HS_L'); hb = hz(rb, 'HS_R') - hz(rb, 'HS_L'); da = hz(ra, 'DNa02_R') - hz(ra, 'DNa02_L'); db = hz(rb, 'DNa02_R') - hz(rb, 'DNa02_L')
                obs.append(ha * hb < 0 and da * db < 0); vals.append([ha, hb, da, db])
            elif item == 6:
                ft, cv, no = g('female_taste'), g('cva'), g('none'); obs.append(hz(ft, 'pC1') > hz(no, 'pC1') and hz(ft, 'pIP10') > hz(no, 'pIP10') and hz(cv, 'pC1') <= hz(no, 'pC1')); vals.append([hz(ft, 'pC1'), hz(no, 'pC1'), hz(cv, 'pC1'), hz(ft, 'pIP10'), hz(no, 'pIP10')])
            ts.append(t)
        except (TypeError, AttributeError): return None
    return obs, vals, ts

def sign_test(obs):
    k = sum(obs); m = len(obs); p = sum(math.comb(m, i) for i in range(k, m + 1)) / 2 ** m; return k, m, p

if __name__ == '__main__':
    env_battery = os.environ.get('FLY_BATTERY')
    if env_battery:
        default_battery = env_battery
    elif os.path.exists('battery/battery-v4.json'):
        default_battery = 'battery/battery-v4.json'
    else:
        default_battery = 'battery/battery.json'

    parser = argparse.ArgumentParser(description='Score results/runs.jsonl against the test battery.')
    parser.add_argument('runs', nargs='?', default='results/runs.jsonl', help='Path to runs JSONL file (default: results/runs.jsonl)')
    parser.add_argument('pos_step', nargs='?', type=float, default=None, metavar='STEP', help='Sweep step multiplier for random arm (optional positional)')
    parser.add_argument('--battery', '-b', default=default_battery, metavar='FILE',
                        help='Path to battery JSON file (default: $FLY_BATTERY, battery/battery-v4.json if present, else battery/battery.json)')
    parser.add_argument('--step', '-s', type=float, default=None, help='Sweep step multiplier for random arm')
    parser.add_argument('--json', '-j', nargs='?', const=True, default=None, metavar='FILE',
                        help='Export evaluation verdicts to machine-readable JSON file (default: results/verdicts.json or results/verdicts-step-<step>.json)')

    args = parser.parse_args()

    runs_path = args.runs
    step = args.step if args.step is not None else args.pos_step

    json_path = None
    if args.json is not None:
        if args.json is True:
            json_path = 'results/verdicts.json' if step is None else ('results/verdicts-step-%g.json' % step)
        elif isinstance(args.json, str) and (args.json.endswith('.jsonl') or args.json.endswith('.jsonl.gz')):
            runs_path = args.json
            json_path = 'results/verdicts.json' if step is None else ('results/verdicts-step-%g.json' % step)
        else:
            json_path = args.json

    ALL = [json.loads(l) for l in open(runs_path)]
    STEP = step
    runs = [r for r in ALL if r.get('condition') != 'random' or r.get('step') == STEP or (STEP is None and r.get('step') is None)]
    B = json.load(open(args.battery))

    out = {}
    for it in B['items']:
        i = it['id']; rec = {'name': it['name'], 'conditions': {}}
        for cond in ('real', 'shuffled', 'random'):
            s = stats(i, cond)
            if s is None or not s[0]: rec['conditions'][cond] = {'verdict': 'unreadable' if s is None else 'not-run'}; continue
            k, m, p = sign_test(s[0]); rec['conditions'][cond] = {'direction_observed': f'{k}/{m}', 'p_one_sided': round(p, 4), 'holds': p < 0.01, 'mean_stats': [round(sum(v[j] for v in s[1]) / m, 3) for j in range(len(s[1][0]))]}
        c = rec['conditions']
        if B.get('battery','').endswith('v4') or 'v4' in B.get('battery',''):
            # v4: one-sided Fisher on counts (real vs fake) at 0.01, both fakes; paired-magnitude sign test beside
            def fisher(a, na, b, nb):
                tot = a + b; N = na + nb
                return sum(math.comb(na, x) * math.comb(nb, tot - x) / math.comb(N, tot) for x in range(a, min(na, tot) + 1))
            sr = stats(i, 'real')
            if sr and sr[0]:
                ka, na = sum(sr[0]), len(sr[0]); rec['difference_tests'] = {}
                for cond in ('shuffled', 'random'):
                    sf = stats(i, cond)
                    if not sf or not sf[0]: rec['difference_tests'][cond] = {'verdict': 'unreadable'}; continue
                    kb, nb = sum(sf[0]), len(sf[0]); pf = fisher(ka, na, kb, nb)
                    tr_map = dict(zip(sr[2], sr[1]))
                    tf_map = dict(zip(sf[2], sf[1]))
                    shared = sorted(set(tr_map) & set(tf_map))
                    m_sample = magnitude(i, tr_map[shared[0]]) if shared else None
                    if m_sample is not None:
                        paired = [1 if magnitude(i, tr_map[t]) > magnitude(i, tf_map[t]) else 0 for t in shared]
                        kp, mp, pp = sign_test(paired) if paired else (0, 0, 1.0)
                        rec['difference_tests'][cond] = {
                            'real': f'{ka}/{na}',
                            'fake': f'{kb}/{nb}',
                            'fisher_p': round(pf, 5),
                            'holds': pf < 0.01,
                            'paired_wins': f'{kp}/{mp}',
                            'sign_p': round(pp, 4),
                            'paired_p': round(pp, 4)
                        }
                    else:
                        note = ("item 5 predicate is a sign flip between conditions (product test), not a directional magnitude"
                                if i == 5 else
                                "item 6 predicate has multiple clauses with differing signs; scalar sum omitted to prevent masking")
                        dt_entry = {
                            'real': f'{ka}/{na}',
                            'fake': f'{kb}/{nb}',
                            'fisher_p': round(pf, 5),
                            'holds': pf < 0.01,
                            'paired_wins': None,
                            'note': note
                        }
                        if i == 6 and shared:
                            # Report paired magnitude per clause: pC1 excitation, pIP10 excitation, cVA non-excitation
                            clauses = {
                                'pC1_activation': [1 if (tr_map[t][0] - tr_map[t][1]) > (tf_map[t][0] - tf_map[t][1]) else 0 for t in shared],
                                'pIP10_activation': [1 if (tr_map[t][3] - tr_map[t][4]) > (tf_map[t][3] - tf_map[t][4]) else 0 for t in shared],
                                'cva_inhibition': [1 if (tr_map[t][1] - tr_map[t][2]) > (tf_map[t][1] - tf_map[t][2]) else 0 for t in shared],
                            }
                            dt_entry['clauses'] = {c_name: f'{sum(cp)}/{len(cp)}' for c_name, cp in clauses.items()}
                        rec['difference_tests'][cond] = dt_entry
                bar = max([k for k in range(0, na + 1) if fisher(ka, na, k, na) < 0.01] or [-1])
                rec['count_bar'] = f'with real at {ka}/{na}, the fake must show the direction in at most {bar} of {na}'
                rec['verdict'] = 'held' if all(rec['difference_tests'][x].get('holds') for x in ('shuffled', 'random')) else ('unreadable' if any(rec['difference_tests'][x].get('verdict') == 'unreadable' for x in ('shuffled', 'random')) else 'failed')
                rec['real_only'] = bool(c.get('real', {}).get('holds')); out[str(i)] = rec; continue
        if all(x.get('verdict') in ('unreadable', 'not-run') for x in c.values()): rec['verdict'] = 'not-run'
        elif any('holds' not in x for x in c.values()): rec['verdict'] = 'unreadable'
        else: rec['verdict'] = 'held' if (c['real']['holds'] and not c['shuffled']['holds'] and not c['random']['holds']) else 'failed'
        rec['real_only'] = bool(c.get('real', {}).get('holds'))
        out[str(i)] = rec

    if json_path:
        parent_dir = os.path.dirname(json_path)
        if parent_dir: os.makedirs(parent_dir, exist_ok=True)
        with open(json_path, 'w') as f:
            json.dump(out, f, indent=1)

    for i, r in out.items(): print(i, r['name'], '->', r['verdict'], {k: (v.get('direction_observed'), v.get('holds')) for k, v in r['conditions'].items()})
