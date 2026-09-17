import json, numpy as np
W = '/Users/dovi/fly-data/work'; S = '/Users/dovi/fly-data/site/data'
def curve(path, G=250):
    L = [json.loads(l) for l in open(path)][:G]
    best = -1e9; out = []
    for r in L: best = max(best, r['gen_best']); out.append(round(best, 4))
    return out, L
real, Lr = curve(f'{W}/evo_real/log.jsonl'); scr, Ls = curve(f'{W}/evo_shuffled/log.jsonl')
evo = dict(real=real, scrambled=scr, generations=len(real), final_real=real[-1], final_scrambled=scr[-1],
           pull='On the real wiring, the first search found a tripod that held on ten neuron draws it never saw: 0.96. On scrambled wiring, the same search found nothing that held: 0.06.')
json.dump(evo, open(f'{S}/evo.json', 'w'))
b = json.load(open(f'{W}/evo_real_v3/best.json')); names = b['groups']; x = np.array(b['x'])
dials = [dict(name={'exc': 'excite', 'inh': 'inhibit', 'TBD': 'unassigned'}.get(n, n), log2=float(v / np.log(2)), factor=float(np.exp(v))) for n, v in zip(names, x)]
dials.sort(key=lambda d: -abs(d['log2']))
json.dump(dials, open(f'{S}/dials.json', 'w'))
print('real final', real[-1], 'scrambled final', scr[-1], 'gens', len(real), len(scr))
print('top dials', [(d['name'], round(d['factor'], 2)) for d in dials[:10]])
