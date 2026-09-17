// 1FAB0 exhibit. Everything drawn here is data: synapse sites and neuron skeletons from the MaleCNS
// connectome, body poses exported from the MuJoCo simulation, and nerve-cord activity from the model runs.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const $ = (s) => document.querySelector(s);
const PLAYBACK = 0.5;             // half speed: stepping at ~6 Hz is readable
const LEG_ROI = ['VNC:LegNp(T1)(L)', 'VNC:LegNp(T2)(L)', 'VNC:LegNp(T3)(L)', 'VNC:LegNp(T1)(R)', 'VNC:LegNp(T2)(R)', 'VNC:LegNp(T3)(R)'];
const LEG_KEY = [['fl', 'L'], ['ml', 'L'], ['hl', 'L'], ['fl', 'R'], ['ml', 'R'], ['hl', 'R']];
const LEG_LABEL = ['L1', 'L2', 'L3', 'R1', 'R2', 'R3'];
const COLORS = { ink: new THREE.Color('#34424f'), hot: new THREE.Color('#e0462b'), cmd: new THREE.Color('#1f6f86'), leg: new THREE.Color('#b0782c') };

const bin = async (url, T) => new T(await (await fetch(url)).arrayBuffer());
const json = async (url) => (await fetch(url)).json();

// ---------------------------------------------------------------- shared anatomy
const anatomy = (async () => {
  const [pos, roi, dens, meta, skel, skelIdx] = await Promise.all([
    bin('data/cloud_pos.bin', Float32Array), bin('data/cloud_roi.bin', Uint8Array), bin('data/cloud_density.bin', Uint8Array),
    json('data/cloud_meta.json'), bin('data/skeletons.bin', Float32Array), json('data/skeletons.json'),
  ]);
  // data axes: x left-right, y dorsal-ventral, z head-to-tail -> three.js: brain on top
  const p = new Float32Array(pos.length);
  for (let i = 0; i < pos.length; i += 3) { p[i] = pos[i]; p[i + 1] = -pos[i + 2]; p[i + 2] = pos[i + 1]; }
  const s = new Float32Array(skel.length);
  for (let i = 0; i < skel.length; i += 3) { s[i] = skel[i]; s[i + 1] = -skel[i + 2]; s[i + 2] = skel[i + 1]; }
  const roiIndex = Object.fromEntries(meta.roi_names.map((n, i) => [n, i]));
  return { pos: p, roi, dens, meta, skel: s, skelIdx, roiIndex };
})();

// ---------------------------------------------------------------- specimen view
class Specimen {
  constructor(canvas, { autoRotate = true, distance = 4.6, interactive = true } = {}) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, devicePixelRatio));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.01, 50);
    this.camera.position.set(distance * 0.5, 0.1, distance * 0.87); this.camera.lookAt(0, 0, 0);
    this.controls = new OrbitControls(this.camera, canvas);
    Object.assign(this.controls, { enableDamping: true, autoRotate, autoRotateSpeed: 0.55, enablePan: false, minDistance: 1.2, maxDistance: 7, enabled: interactive });
    canvas.addEventListener('pointerdown', () => { this.controls.autoRotate = false; });
    this.roiAct = new Float32Array(256);
    this.roiTex = new THREE.DataTexture(this.roiAct, 256, 1, THREE.RedFormat, THREE.FloatType); this.roiTex.needsUpdate = true;
    this.groupAct = {};
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
  }
  async init() {
    const A = await anatomy;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(A.pos, 3));
    const r = new Float32Array(A.roi.length); for (let i = 0; i < r.length; i++) r[i] = A.roi[i];
    g.setAttribute('aRoi', new THREE.BufferAttribute(r, 1));
    const d = new Float32Array(A.dens.length); for (let i = 0; i < d.length; i++) d[i] = A.dens[i] / 255;
    g.setAttribute('aDens', new THREE.BufferAttribute(d, 1));
    const seeds = new Float32Array(A.roi.length); for (let i = 0; i < seeds.length; i++) seeds[i] = Math.random();
    g.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
    this.cloudMat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { uRoi: { value: this.roiTex }, uScale: { value: 1 }, uTime: { value: 0 }, uInk: { value: COLORS.ink }, uHot: { value: COLORS.hot } },
      vertexShader: `
        attribute float aRoi; attribute float aDens; attribute float aSeed;
        uniform sampler2D uRoi; uniform float uScale; uniform float uTime;
        varying float vAct; varying float vDens; varying float vDepth;
        void main(){
          float act = texture2D(uRoi, vec2((aRoi + 0.5) / 256.0, 0.5)).r;
          float flicker = 0.75 + 0.25 * sin(uTime * 23.0 + aSeed * 60.0);
          vAct = clamp(act * flicker, 0.0, 1.0); vDens = aDens;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vDepth = clamp((-mv.z - 3.8) / 2.0, 0.0, 1.0);
          gl_PointSize = max(0.9, (0.85 + aDens * 0.9 + vAct * 2.2) * uScale / -mv.z);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform vec3 uInk; uniform vec3 uHot;
        varying float vAct; varying float vDens; varying float vDepth;
        void main(){
          vec2 c = gl_PointCoord - 0.5; float d = length(c); if (d > 0.5) discard;
          vec3 amber = vec3(0.93, 0.62, 0.22);
          vec3 col = mix(uInk, mix(amber, uHot, smoothstep(0.35, 0.95, vAct)), smoothstep(0.04, 0.4, vAct));
          float a = (0.08 + 0.24 * vDens) * (1.0 - 0.45 * vDepth) + vAct * 0.42;
          gl_FragColor = vec4(col, clamp(a, 0.0, 1.0) * smoothstep(0.5, 0.2, d));
        }`,
    });
    this.scene.add(new THREE.Points(g, this.cloudMat));

    // skeletons: one LineSegments per group, colour and glow driven by activity
    this.skel = [];
    for (const e of A.skelIdx) {
      const key = e.group === 'leg_mn' ? `leg:${e.subclass}:${e.side}` : e.group;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(A.skel.subarray(e.offset * 3, (e.offset + e.count) * 3), 3));
      const base = e.group === 'leg_mn' ? COLORS.leg : ['DNg100', 'DNa02'].includes(e.group) ? COLORS.cmd : new THREE.Color('#8d96a0');
      const mat = new THREE.LineBasicMaterial({ color: base.clone(), transparent: true, opacity: e.group === 'leg_mn' ? 0.28 : 0.4, depthWrite: false });
      const line = new THREE.LineSegments(geo, mat); line.userData = { key, base, group: e.group, side: e.side };
      this.scene.add(line); this.skel.push(line);
    }
    this.A = A; this.resize();
    return this;
  }
  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect(); if (!r.width) return;
    this.renderer.setSize(r.width, r.height, false);
    this.camera.aspect = r.width / r.height; this.camera.updateProjectionMatrix();
    if (this.cloudMat) this.cloudMat.uniforms.uScale.value = r.height * 0.0042 * Math.min(2, devicePixelRatio);
  }
  setActivity({ legs = [0, 0, 0, 0, 0, 0], cmd = 0, turnL = 0, turnR = 0, ambient = 0 }) {
    const A = this.A; if (!A) return;
    this.roiAct.fill(0);
    for (const [name, i] of Object.entries(A.roiIndex)) if (name.startsWith('VNC:')) this.roiAct[i] = ambient * 0.25;
    LEG_ROI.forEach((n, k) => { const i = A.roiIndex[n]; if (i !== undefined) this.roiAct[i] = Math.max(this.roiAct[i], legs[k]); });
    for (const n of ['BR:GNG', 'VNC:IntTct', 'VNC:LTct']) { const i = A.roiIndex[n]; if (i !== undefined) this.roiAct[i] = Math.max(this.roiAct[i], cmd * 0.35); }
    this.roiTex.needsUpdate = true;
    for (const line of this.skel) {
      const u = line.userData; let a = 0;
      if (u.key.startsWith('leg:')) { const [, sub, side] = u.key.split(':'); const k = LEG_KEY.findIndex(([s, sd]) => s === sub && sd === side); a = k >= 0 ? legs[k] : 0; }
      else if (u.group === 'DNg100') a = cmd;
      else if (u.group === 'DNa02') a = u.side === 'L' || u.side === 'R' ? (u.side === 'L' ? turnL : turnR) : Math.max(turnL, turnR);
      line.material.color.copy(u.base).lerp(COLORS.hot, Math.min(1, a * 0.9));
      line.material.opacity = (u.group === 'leg_mn' ? 0.16 : 0.32) + a * 0.5;
    }
  }
  frame(t) { if (!this.cloudMat) return; this.cloudMat.uniforms.uTime.value = t; this.controls.update(); this.renderer.render(this.scene, this.camera); }
}

// ---------------------------------------------------------------- fly body view
class FlyBody {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(2, devicePixelRatio));
    this.renderer.shadowMap.enabled = true; this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 400);
    this.scene.add(new THREE.HemisphereLight(0xfffaf0, 0xcfc4ae, 1.25));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(-6, 14, 8); sun.castShadow = true;
    Object.assign(sun.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 60 }); sun.shadow.mapSize.set(2048, 2048); sun.shadow.radius = 6; sun.shadow.bias = -0.0004;
    this.sun = sun; this.scene.add(sun, sun.target);
    // floor: museum paper with a fine millimetre grid
    const c = document.createElement('canvas'); c.width = c.height = 512; const x = c.getContext('2d');
    x.fillStyle = '#efe9dd'; x.fillRect(0, 0, 512, 512); x.strokeStyle = 'rgba(27,33,39,.10)'; x.lineWidth = 1;
    for (let i = 0; i <= 512; i += 51.2) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, 512); x.stroke(); x.beginPath(); x.moveTo(0, i); x.lineTo(512, i); x.stroke(); }
    x.strokeStyle = 'rgba(27,33,39,.2)'; x.lineWidth = 2; x.strokeRect(0, 0, 512, 512);
    const tex = new THREE.CanvasTexture(c); tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.repeat.set(20, 20); tex.colorSpace = THREE.SRGBColorSpace;
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; this.scene.add(floor);
    this.root = new THREE.Group(); this.root.rotation.x = -Math.PI / 2; this.scene.add(this.root);   // MuJoCo z-up -> three y-up
    this.trailGeo = new THREE.BufferGeometry(); this.trailPos = new Float32Array(3 * 4000);
    this.trailGeo.setAttribute('position', new THREE.BufferAttribute(this.trailPos, 3));
    this.trail = new THREE.Line(this.trailGeo, new THREE.LineBasicMaterial({ color: 0xe0462b, transparent: true, opacity: 0.8 }));
    this.scene.add(this.trail);
    this.camTarget = new THREE.Vector3(); this.camPos = new THREE.Vector3(7, 6.5, 9);
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement);
  }
  async init() {
    const [meshes, verts, faces] = await Promise.all([json('data/fly_meshes.json'), bin('data/fly_verts.bin', Float32Array), bin('data/fly_faces.bin', Uint32Array)]);
    const mat = (name) => {
      if (/eye/.test(name)) return new THREE.MeshStandardMaterial({ color: 0x8e2016, roughness: 0.35, metalness: 0.05 });
      if (/wing|haltere/.test(name)) return new THREE.MeshPhysicalMaterial({ color: 0xdfe7ea, roughness: 0.2, transmission: 0.6, transparent: true, opacity: 0.45 });
      if (/tibia|tarsus|femur|trochanter|coxa/.test(name)) return new THREE.MeshStandardMaterial({ color: 0x6f5237, roughness: 0.6 });
      if (/abdomen|a\d/.test(name)) return new THREE.MeshStandardMaterial({ color: 0x9c7445, roughness: 0.55 });
      return new THREE.MeshStandardMaterial({ color: 0xb58a55, roughness: 0.55 });
    };
    this.parts = meshes.map((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(verts.slice(m.voff * 3, (m.voff + m.vcount) * 3), 3));
      g.setIndex(new THREE.BufferAttribute(faces.slice(m.foff * 3, (m.foff + m.fcount) * 3), 1));
      g.computeVertexNormals();
      const mesh = new THREE.Mesh(g, mat(m.name)); mesh.castShadow = true; mesh.matrixAutoUpdate = true;
      this.root.add(mesh); return mesh;
    });
    this.resize(); return this;
  }
  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect(); if (!r.width) return;
    this.renderer.setSize(r.width, r.height, false); this.camera.aspect = r.width / r.height; this.camera.updateProjectionMatrix();
  }
  setRun(run, motion) { this.run = run; this.motion = motion; this.snap = true; }
  pose(f) {
    const { run, motion } = this; if (!run) return;
    const G = run.geoms, o = f * G * 7;
    for (let g = 0; g < G; g++) {
      const k = o + g * 7, m = this.parts[g];
      m.position.set(motion[k], motion[k + 1], motion[k + 2]);
      m.quaternion.set(motion[k + 4], motion[k + 5], motion[k + 6], motion[k + 3]);   // MuJoCo (w,x,y,z) -> three (x,y,z,w)
    }
    const p = run.path;
    const n = Math.min(f + 1, 3999);
    for (let i = 0; i < n; i++) { this.trailPos[i * 3] = p[i][0]; this.trailPos[i * 3 + 1] = 0.02; this.trailPos[i * 3 + 2] = -p[i][1]; }
    this.trailGeo.setDrawRange(0, n); this.trailGeo.attributes.position.needsUpdate = true;
    const head = new THREE.Vector3(p[f][0], 0.4, -p[f][1]);
    this.camTarget.lerp(head, this.snap ? 1 : 0.08);
    const want = head.clone().add(new THREE.Vector3(5.5, 5.2, 7.5));
    this.camPos.lerp(want, this.snap ? 1 : 0.05); this.snap = false;
    this.camera.position.copy(this.camPos); this.camera.lookAt(this.camTarget);
    this.sun.position.set(head.x - 6, 14, head.z + 8); this.sun.target.position.copy(head);
  }
  frame() { this.renderer.render(this.scene, this.camera); }
}

// ---------------------------------------------------------------- footfall diagram
function drawGait(canvas, run, f) {
  const dpr = Math.min(2, devicePixelRatio), r = canvas.getBoundingClientRect();
  canvas.width = r.width * dpr; canvas.height = r.height * dpr;
  const x = canvas.getContext('2d'); x.scale(dpr, dpr);
  const W = r.width, H = r.height, left = 34, rowH = (H - 8) / 6, win = Math.round(run.fps * 1.6);
  x.clearRect(0, 0, W, H);
  x.font = '500 11px JetBrains Mono, monospace'; x.textBaseline = 'middle';
  const order = [0, 4, 2, 3, 1, 5];   // L1 R2 L3 | R1 L2 R3 : tripods adjacent
  order.forEach((leg, row) => {
    const y = 4 + row * rowH;
    x.fillStyle = row < 3 ? '#e0462b' : '#1f6f86'; x.fillText(LEG_LABEL[leg], 2, y + rowH / 2);
    x.fillStyle = 'rgba(27,33,39,.05)'; x.fillRect(left, y + 2, W - left, rowH - 4);
    const start = Math.max(0, f - win);
    const cw = (W - left) / win;
    x.fillStyle = '#1b2127';
    for (let t = start; t <= f; t++) if (run.swing[t][leg]) x.fillRect(left + (t - start) * cw, y + 3, Math.ceil(cw), rowH - 6);
  });
  x.fillStyle = 'rgba(224,70,43,.9)'; const cx = left + Math.min(f, win) * ((W - left) / win); x.fillRect(cx, 0, 2, H);
}

// ---------------------------------------------------------------- charts
function drawEvo(canvas, evo) {
  const dpr = Math.min(2, devicePixelRatio), r = canvas.getBoundingClientRect();
  canvas.width = r.width * dpr; canvas.height = r.height * dpr;
  const x = canvas.getContext('2d'); x.scale(dpr, dpr);
  const W = r.width, H = r.height, pad = { l: 44, r: 12, t: 12, b: 30 };
  const G = Math.max(evo.real.length, evo.scrambled.length);
  const X = (g) => pad.l + (g / (G - 1)) * (W - pad.l - pad.r), Y = (v) => pad.t + (1 - (v + 0.25) / 1.25) * (H - pad.t - pad.b);
  x.strokeStyle = 'rgba(27,33,39,.12)'; x.fillStyle = '#77808a'; x.font = '500 11px JetBrains Mono, monospace';
  for (const v of [-0.25, 0, 0.25, 0.5, 0.75, 1]) { x.beginPath(); x.moveTo(pad.l, Y(v)); x.lineTo(W - pad.r, Y(v)); x.stroke(); x.fillText(v.toFixed(2), 4, Y(v) + 4); }
  x.fillText('generation →', W - 110, H - 8);
  const line = (arr, col, w) => { x.strokeStyle = col; x.lineWidth = w; x.beginPath(); arr.forEach((v, g) => (g ? x.lineTo(X(g), Y(v)) : x.moveTo(X(g), Y(v)))); x.stroke(); };
  line(evo.scrambled, '#9aa3ab', 2.2); line(evo.real, '#e0462b', 2.6);
}

function renderDials(el, dials) {
  const max = Math.max(...dials.map((d) => Math.abs(d.log2)), 1);
  el.innerHTML = dials.map((d) => {
    const w = (Math.abs(d.log2) / max) * 50, left = d.log2 >= 0 ? 50 : 50 - w;
    return `<div class="dial" title="${d.name === 'unassigned' ? 'Nerve-cord neurons without a hemilineage label' : d.name.length <= 7 && /\d/.test(d.name) ? 'Hemilineage ' + d.name + ': neurons born from the same stem cell' : d.name}"><span>${d.name}</span><span class="bar"><i class="fill" style="left:${left}%;width:${w}%;background:${d.log2 >= 0 ? '#e0462b' : '#1f6f86'}"></i></span><span class="v">×${d.factor.toFixed(2)}</span></div>`;
  }).join('');
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function renderBattery(sb) {
  $('#battery-run').textContent = sb.run;
  $('#battery-table').innerHTML = `<div class="bt-row bt-head" role="row"><span>Behaviour</span><span>Real wiring</span><span>Scrambled fake</span><span>Random-settings fake</span><span>Result</span></div>` +
    sb.items.map((it) => `<div class="bt-row ${esc(it.status)}" role="row">
      <span class="bt-name">${esc(it.plain)}<small>${esc(it.note)}</small></span>
      <span data-k="Real wiring">${esc(it.real)}</span><span data-k="Scrambled fake">${esc(it.shuffled)}</span><span data-k="Random-settings fake">${esc(it.random)}</span>
      <span class="bt-verdict ${esc(it.status)}">${esc(it.label)}</span></div>`).join('') +
    `<div class="bt-foot">Each count is the number of trials, out of 30, in which the predicted behaviour appeared. The random-settings fake is shown as its lowest and highest count across the five loudness levels.</div>`;
}
json('data/scoreboard.json').then(renderBattery).catch(() => {});

function renderCards(el, cards) {
  el.innerHTML = cards.map((c) => `
    <article class="card">
      <span class="verdict ${c.verdict}">${c.verdict_label}</span>
      <div class="big">${c.big}<small>${c.big_unit || ''}</small></div>
      <h3>${c.title}</h3>
      <p>${c.body}</p>
      ${c.bars ? `<div class="vs">${c.bars.map((b) => `<div><span>${b.label}</span><span class="t"><i style="width:${Math.max(2, b.pct)}%;background:${b.color}"></i></span><span>${b.text}</span></div>`).join('')}</div>` : ''}
      <span class="src">${c.source}</span>
    </article>`).join('');
}

// ---------------------------------------------------------------- app
const state = { model: 'evolved_real', cmd: 'walk', f: 0, t: 0, playing: true, runs: new Map() };
async function loadRun(model, cmd) {
  const id = `${model}_${cmd}`;
  if (!state.runs.has(id)) state.runs.set(id, Promise.all([json(`data/runs/${id}.json`), bin(`data/runs/${id}_motion.bin`, Float32Array)]));
  return state.runs.get(id);
}
const captions = await json('data/captions.json').catch(() => ({}));

async function main() {
  const hero = await new Specimen($('#hero-brain'), { distance: 5.5 }).init();
  $('#loader').classList.add('done');
  const brain = await new Specimen($('#brain'), { distance: 5.1 }).init();
  const body = await new FlyBody($('#body')).init();

  const select = async (patch) => {
    Object.assign(state, patch);
    document.querySelectorAll('#seg-model button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === state.model)));
    document.querySelectorAll('#seg-cmd button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === state.cmd)));
    const [run, motion] = await loadRun(state.model, state.cmd);
    state.run = run; state.f = 0; state.t = 0; body.setRun(run, motion);
    $('#r-speed').textContent = run.stats.speed_mm_s.toFixed(1);
    $('#r-hz').textContent = run.stats.step_hz.toFixed(1);
    $('#r-tripod').textContent = run.stats.tripod_index.toFixed(2);
    $('#caption').textContent = captions[`${state.model}_${state.cmd}`] || '';
    loadRun(state.model, state.cmd === 'walk' ? 'left' : 'walk');
  };
  document.querySelectorAll('#seg-model button').forEach((b) => (b.onclick = () => select({ model: b.dataset.v })));
  document.querySelectorAll('#seg-cmd button').forEach((b) => (b.onclick = () => select({ cmd: b.dataset.v })));
  $('#play').onclick = () => { state.playing = !state.playing; $('#play').textContent = state.playing ? '❚❚' : '▶'; };
  $('#scrub').onclick = (e) => { const r = $('#scrub').getBoundingClientRect(); state.f = Math.floor(((e.clientX - r.left) / r.width) * (state.run.frames - 1)); state.t = 0; body.snap = true; };
  await select({});

  json('data/evo.json').then((evo) => { drawEvo($('#evo-chart'), evo); $('#pull-evo').textContent = evo.pull; addEventListener('resize', () => drawEvo($('#evo-chart'), evo)); }).catch(() => {});
  json('data/dials.json').then((d) => renderDials($('#dial-grid'), d)).catch(() => {});
  json('data/evidence.json').then((c) => renderCards($('#cards'), c)).catch(() => {});

  // idle activity for the hero: a slow command wave down into the nerve cord
  let last = performance.now();
  const visible = new Map();
  const io = new IntersectionObserver((es) => es.forEach((e) => visible.set(e.target, e.isIntersecting)));
  [$('#hero-brain'), $('#brain'), $('#body'), $('#gait')].forEach((c) => io.observe(c));

  function tick(now) {
    const dt = Math.min(0.1, (now - last) / 1000); last = now; const t = now / 1000;
    if (visible.get($('#hero-brain'))) {
      const wave = (k) => Math.max(0, Math.sin(t * 2.4 + (k % 2 ? Math.PI : 0) + (k === 1 || k === 4 ? Math.PI : 0)));
      hero.setActivity({ legs: [0, 1, 2, 3, 4, 5].map((k) => 0.55 * wave(k)), cmd: 0.5 + 0.5 * Math.sin(t * 1.3), ambient: 0.2 });
      hero.frame(t);
    }
    const run = state.run;
    if (run && (visible.get($('#brain')) || visible.get($('#body')) || visible.get($('#gait')))) {
      if (state.playing) {
        state.t += dt * PLAYBACK * run.fps;
        while (state.t >= 1) { state.t -= 1; state.f++; if (state.f >= run.frames) { state.f = 0; body.snap = true; } }
      }
      const f = state.f, tsec = f / run.fps, on = tsec > 0.02 ? 1 : 0;
      const legs = run.leg_activity[f];
      brain.setActivity({ legs, cmd: on, turnL: state.cmd === 'left' ? on : 0, turnR: state.cmd === 'right' ? on : 0, ambient: legs.reduce((a, b) => a + b, 0) / 6 });
      brain.frame(t); body.pose(f); body.frame();
      drawGait($('#gait'), run, f);
      $('#scrub-fill').style.width = `${(f / (run.frames - 1)) * 100}%`;
      $('#clock').textContent = `${tsec.toFixed(2)} s`;
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
main().catch((e) => { console.error(e); document.body.insertAdjacentHTML('beforeend', `<p style="position:fixed;bottom:10px;left:10px;background:#fff;padding:8px;border:1px solid #e0462b">Exhibit failed to load: ${e.message}</p>`); });
