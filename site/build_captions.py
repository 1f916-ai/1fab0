import json, glob, os
S = '/Users/dovi/fly-data/site/data'
runs = {os.path.basename(p)[:-5]: json.load(open(p))['stats'] for p in glob.glob(f'{S}/runs/*.json') if not os.path.basename(p).startswith('test')}
def turn(h, cmd):
    if abs(h) < 20: return 'and holds its heading'
    verb = 'turns' if cmd != 'walk' else 'drifts'
    return f"and {verb} {abs(h):.0f}° {'left' if h > 0 else 'right'} over 3.5 seconds"
cap = {}
for rid, st in runs.items():
    model, cmd = rid.rsplit('_', 1)
    who = {'evolved_real': 'The evolved nerve cord', 'published_params': 'With the published settings, the same wiring', 'evolved_scrambled': 'The scrambled wiring'}[model]
    act = {'walk': 'receives the walking command (DNg100)', 'left': 'receives the walking command plus the left turning neuron (DNa02)', 'right': 'receives the walking command plus the right turning neuron (DNa02)'}[cmd]
    if st['speed_mm_s'] < 1.0:
        body = f"The legs barely move: {st['speed_mm_s']:.1f} mm/s."
    else:
        body = f"The fly walks at {st['speed_mm_s']:.1f} mm/s, stepping {st['step_hz']:.1f} times a second, {turn(st['heading_change_deg'], cmd)}."
    tri = st['tripod_index']
    gait = 'The legs keep a clean tripod.' if tri > 0.8 else 'The tripod is partial.' if tri > 0.4 else 'There is no tripod: the legs step out of order.'
    cap[rid] = f"{who} {act}. {body} {gait}"
json.dump(cap, open(f'{S}/captions.json', 'w'), indent=1)
for k, v in sorted(cap.items()): print(k, '→', v)
