/* Did the 2a passive hand actually take the handshape the export asked for?
 *
 * Applying a template and then reporting "template applied" is a check with no power — it
 * confirms the code ran, not that the hand is the right shape. So: read the rendered hand
 * back out of the clip, express it in the same canonical palm frame the template lives in,
 * and measure the distance to the requested shape.
 *
 * The number only means something against a control, so every rendered hand is ALSO scored
 * against every OTHER unmarked handshape. If the requested shape is not reliably the closest,
 * the placement is wrong however small the absolute error looks.
 *
 * Usage: node template-check.mjs model.glb templates.json wordsDir clip.json [clip.json ...]
 */
import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { loadRig, wp } from './vrm-load.mjs';

const [modelPath, tplPath, wordsDir, ...clips] = process.argv.slice(2).filter(a => !a.startsWith('--'));
const T = JSON.parse(readFileSync(tplPath, 'utf8'));
const TPL = T.handshapes, RES = T.resolution || {};
const { scene, byName, roleBone } = await loadRig(modelPath);
const rest = new Map();
scene.traverse(o => { if (o.isBone) rest.set(o, o.quaternion.clone()); });
scene.updateMatrixWorld(true);

const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
const at = (doc, t) => {
  for (const [b, q] of rest) b.quaternion.copy(q);
  for (const tr of doc.tracks) {
    const b = byName.get(tr.bone); if (!b) continue;
    const Ts = tr.times;
    let i = 0; while (i < Ts.length - 1 && Ts[i+1] <= t) i++;
    const j = Math.min(i+1, Ts.length-1), sp = Ts[j]-Ts[i];
    const u = sp > 1e-9 ? Math.min(1, Math.max(0, (t-Ts[i])/sp)) : 0;
    qa.set(tr.values[i*4], tr.values[i*4+1], tr.values[i*4+2], tr.values[i*4+3]);
    qb.set(tr.values[j*4], tr.values[j*4+1], tr.values[j*4+2], tr.values[j*4+3]);
    b.quaternion.copy(qa).slerp(qb, u);
  }
  scene.updateMatrixWorld(true);
};

const FING = { Thumb:[1,2,3,4], Index:[5,6,7,8], Middle:[9,10,11,12],
               Ring:[13,14,15,16], Little:[17,18,19,20] };

/* read the rendered hand back into the template's palm frame */
function readShape(side) {
  const wr = roleBone(side+'Hand');
  const idx = roleBone(side+'IndexProximal'), mid = roleBone(side+'MiddleProximal'),
        pnk = roleBone(side+'LittleProximal');
  if (!wr || !idx || !mid || !pnk) return null;
  const W = wp(wr);
  const xh = wp(idx).clone().sub(W); const pk = wp(pnk).clone().sub(W);
  const scale = wp(mid).distanceTo(W);
  if (xh.lengthSq() < 1e-12 || pk.lengthSq() < 1e-12 || scale < 1e-9) return null;
  xh.normalize();
  const zh = new THREE.Vector3().crossVectors(xh, pk.clone().normalize());
  if (zh.lengthSq() < 1e-12) return null;
  zh.normalize();
  const yh = new THREE.Vector3().crossVectors(zh, xh).normalize();
  const zs = side === 'left' ? -1 : 1;
  const out = new Array(21).fill(null);
  out[0] = [0,0,0];
  for (const [f, ids] of Object.entries(FING)) {
    let b = roleBone(side + (f === 'Little' ? 'Little' : f) + 'Proximal');
    if (!b) continue;
    const chain = [b];
    let c = b;
    while (c.children.find(x => x.isBone) && chain.length < 4) {
      c = c.children.find(x => x.isBone); chain.push(c);
    }
    for (let i = 0; i < ids.length && i < chain.length; i++) {
      const v = wp(chain[i]).clone().sub(W).divideScalar(scale);
      out[ids[i]] = [v.dot(xh), v.dot(yh), v.dot(zh) * zs];
    }
  }
  return out;
}

const dist = (a, b) => {
  let n = 0, s = 0;
  for (let i = 1; i < 21; i++) {
    if (!a[i] || !b[i]) continue;
    s += Math.hypot(a[i][0]-b[i][0], a[i][1]-b[i][1], a[i][2]-b[i][2]); n++;
  }
  return n ? s/n : NaN;
};

const shapes = Object.keys(TPL).filter(k => TPL[k].template_xyz);
let checked = 0, correctNearest = 0;
const rows = [];
for (const cp of clips) {
  const doc = JSON.parse(readFileSync(cp, 'utf8'));
  const word = doc.name.replace(/^RETARGET_/, '');
  let src; try { src = JSON.parse(readFileSync(path.join(wordsDir, word + '.json'), 'utf8')); }
  catch { continue; }
  const syn = (src.segments || [{}])[0].synthesis || {};
  if (syn.class !== '2a' || !syn.passiveHandshape) continue;
  const want = (RES[syn.passiveHandshape.shape]?.use) || syn.passiveHandshape.shape;
  const side = syn.passiveHand === 'L' ? 'left' : 'right';

  const mid = doc.tracks[0].times[Math.floor(doc.tracks[0].times.length/2)];
  at(doc, mid);
  const got = readShape(side);
  if (!got) continue;
  const scored = shapes.map(k => [k, dist(got, TPL[k].template_xyz)])
                       .filter(x => !Number.isNaN(x[1]))
                       .sort((a,b) => a[1]-b[1]);
  if (!scored.length) continue;
  checked++;
  const nearest = scored[0][0];
  const wantD = (scored.find(x => x[0] === want) || [null, NaN])[1];
  if (nearest === want) correctNearest++;
  rows.push([word, want, nearest, wantD, scored[0][1], scored[scored.length-1][1]]);
}

console.log(`\n2a words checked: ${checked}`);
console.log(`requested shape is the NEAREST of ${shapes.length} templates: ` +
            `${correctNearest}/${checked} = ${(100*correctNearest/Math.max(1,checked)).toFixed(0)}%`);
console.log(`(chance would be ~${(100/shapes.length).toFixed(0)}%)\n`);
console.log(`${'word'.padEnd(14)} ${'want'.padEnd(5)} ${'nearest'.padEnd(8)} ${'err(want)'.padStart(9)} ${'err(best)'.padStart(9)} ${'err(worst)'.padStart(10)}`);
for (const [w, want, near, wd, bd, worst] of rows.slice(0, 14))
  console.log(`${w.padEnd(14)} ${want.padEnd(5)} ${near.padEnd(8)} ${wd.toFixed(3).padStart(9)} ${bd.toFixed(3).padStart(9)} ${worst.toFixed(3).padStart(10)}`);
process.exit(correctNearest === checked ? 0 : 1);
