"""Held-out evaluation. Nothing here was used in training (training: DNg100 only, neuron seeds 0-1)."""
import sys, os, json, math, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evo_core as E, vnc_rate as V
STAGE = os.environ.get('STAGE', '')
OUT = os.path.expanduser(f'~/fly-data/work/heldout{STAGE}'); os.makedirs(OUT, exist_ok=True)
SEEDS = list(range(100, 110))
best_real = json.load(open(os.path.expanduser(f'~/fly-data/work/evo_real{STAGE}/best.json')))
best_shuf = json.load(open(os.path.expanduser(f'~/fly-data/work/evo_shuffled{STAGE}/best.json')))
NP = len(best_real['x'])
MODELS = {
    'published_params': ('real', np.zeros(NP)),
    'evolved_real': ('real', np.array(best_real['x'])),
    'evolved_scrambled': ('shuffled', np.array(best_shuf['x'])),
    'published_params_scrambled': ('shuffled', np.zeros(NP)),
}
nets = {'real': E.Net('real'), 'shuffled': E.Net('shuffled')}
dng = np.flatnonzero(V.TYP == 'DNg100')
report = {}

# ---- A. robustness on held-out neuron-parameter draws
A = {}
for name, (null, x) in MODELS.items():
    net = nets[null]; rows = []
    for sd in SEEDS:
        Y, sat = net.run(x[None, :], sd, [dng]); sc, comps = net.fitness(Y, sat)
        c = comps[0]; c.pop('amp'); c['score'] = float(sc[0]); rows.append(c)
    df = pd.DataFrame(rows); A[name] = {k: [round(float(df[k].mean()), 3), round(float(df[k].std()), 3)] for k in df.columns}
    print('A', name, A[name], flush=True)
report['A_robustness_heldout_seeds'] = A

# ---- B. DN screen: walking vs non-walking descending neuron types
tab = pd.read_csv(os.path.expanduser('~/fly-data/work/dnan_function.csv'))
lab = tab[tab.function.notna()].drop_duplicates('type')[['type', 'function']]
WALK = ('walk', 'locomotion', 'steering', 'turning')
lab['walking'] = lab.function.str.lower().apply(lambda s: any(w in s for w in WALK))
lab = lab[lab.type != 'DNg100']
types = []
for _, r in lab.iterrows():
    ix = np.flatnonzero(V.TYP == r.type)
    ix = [i for i in ix if i in nets['real'].local]
    if ix: types.append((r.type, r.function, bool(r.walking), ix))
print('B screen types', len(types), 'walking', sum(t[2] for t in types), flush=True)
B = {}
for name, (null, x) in MODELS.items():
    net = nets[null]; per = {t[0]: [] for t in types}
    for sd in SEEDS[:3]:
        X = np.repeat(x[None, :], len(types), 0)
        Y, sat = net.run(X, sd, [t[3] for t in types]); sc, comps = net.fitness(Y, sat)
        for b, t in enumerate(types):
            c = comps[b]; per[t[0]].append(c['moving'] * c['rhythm'])
    stepping = {k: float(np.mean(v)) for k, v in per.items()}
    wk = [stepping[t[0]] for t in types if t[2]]; nw = [stepping[t[0]] for t in types if not t[2]]
    auc = float(np.mean([[1.0 if a > b else 0.5 if a == b else 0.0 for b in nw] for a in wk]))
    B[name] = dict(auc_walking_vs_not=round(auc, 3), walking_mean=round(float(np.mean(wk)), 3), nonwalking_mean=round(float(np.mean(nw)), 3),
                   per_type={t[0]: dict(function=t[1], walking=t[2], stepping=round(stepping[t[0]], 3)) for t in types})
    print('B', name, {k: v for k, v in B[name].items() if k != 'per_type'}, flush=True)
report['B_dn_screen'] = B

# ---- C. DNa02 unilateral: ipsilateral legs should take smaller steps (turn toward the activated side)
C = {}
for name, (null, x) in MODELS.items():
    net = nets[null]; res = []
    for sd in SEEDS[:5]:
        for side in ('L', 'R'):
            ix = [i for i in np.flatnonzero((V.TYP == 'DNa02') & (V.ROOT == ('LHS' if side == 'L' else 'RHS'))) if i in net.local]
            if not ix: ix = [i for i in np.flatnonzero((V.TYP == 'DNa02') & (V.SIDE == side)) if i in net.local]
            stim = list(ix) + list(dng)   # walking drive plus one-sided DNa02
            Y, sat = net.run(x[None, :], sd, [stim]); flex, ext = net.legs(Y, 0)
            amp = (flex - ext).max(1) - (flex - ext).min(1)   # LEGS order: flL, mlR, hlL, flR, mlL, hlR
            left = amp[[0, 2, 4]].mean(); right = amp[[1, 3, 5]].mean()
            ipsi_smaller = (left < right) if side == 'L' else (right < left)
            res.append(dict(seed=sd, side=side, left=float(left), right=float(right), ipsi_smaller=bool(ipsi_smaller), n_dna02=len(ix)))
    C[name] = dict(fraction_ipsilateral_smaller=round(float(np.mean([r['ipsi_smaller'] for r in res])), 3), trials=res)
    print('C', name, C[name]['fraction_ipsilateral_smaller'], flush=True)
report['C_dna02_turning'] = C
json.dump(report, open(f'{OUT}/report.json', 'w'), indent=1)
print('saved', f'{OUT}/report.json')
