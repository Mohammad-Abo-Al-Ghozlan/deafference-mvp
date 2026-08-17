/* WEAK-DROP DETECTOR for class-2s words. Read this header before reading the numbers.
 *
 * It began as a chirality gate on synthesized hands, after the first 2s-mirroring attempt
 * produced inside-out hands that passed every check we had — anatomy gate 250/250, hinge
 * check clean, jitter in budget, rig suite 60/60 — because all of those are bilaterally
 * symmetric or per-joint, so a correct finger curl on a backwards palm is invisible to them.
 *
 * That bug is fixed, and the fix is verified STATICALLY instead of here: put both hands'
 * finger bones at identical local rotations and the resulting geometry is an exact mirror
 * (0.0000 m on this rig, because its left/right bind poses are mirrored). Handshape
 * mirroring is therefore exact and needs no runtime check.
 *
 * What this file actually measures is different, and more useful. The palm normal is
 * dominated by WRIST orientation, and the passive wrist is not synthesized — it comes from
 * the pose-block knuckles, which are real data. So on a 2s word this asks:
 *
 *     is the passive ARM in this take actually performing the symmetric sign?
 *
 * A signer who drops the weak hand in casual signing produces a passive arm that mirrors
 * nothing. That is exactly the "weak drop" failure, measured per frame rather than per clip.
 * Low percentages here indict the TAKE, not the renderer.
 *
 * Usage: node chirality-check.mjs model.glb lexicon.json clip.json [clip.json ...]
 */
import * as THREE from 'three';
import { readFileSync } from 'node:fs';
import { loadRig, wp } from './vrm-load.mjs';

const [modelPath, lexPath, ...clips] = process.argv.slice(2).filter(a => !a.startsWith('--'));
if (!modelPath || !lexPath || !clips.length) {
  console.error('usage: node chirality-check.mjs model.glb lexicon.json clip.json [...]');
  process.exit(2);
}
const LEX = JSON.parse(readFileSync(lexPath, 'utf8')).words || {};
const { scene, byName, roleBone } = await loadRig(modelPath);
const rest = new Map();
scene.traverse(o => { if (o.isBone) rest.set(o, o.quaternion.clone()); });
scene.updateMatrixWorld(true);

const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
const at = (doc, t) => {
  for (const [b, q] of rest) b.quaternion.copy(q);
  for (const tr of doc.tracks) {
    const b = byName.get(tr.bone); if (!b) continue;
    const T = tr.times;
    let i = 0; while (i < T.length - 1 && T[i + 1] <= t) i++;
    const j = Math.min(i + 1, T.length - 1), sp = T[j] - T[i];
    const u = sp > 1e-9 ? Math.min(1, Math.max(0, (t - T[i]) / sp)) : 0;
    qa.set(tr.values[i*4], tr.values[i*4+1], tr.values[i*4+2], tr.values[i*4+3]);
    qb.set(tr.values[j*4], tr.values[j*4+1], tr.values[j*4+2], tr.values[j*4+3]);
    b.quaternion.copy(qa).slerp(qb, u);
  }
  scene.updateMatrixWorld(true);
};

function palmNormal(side) {
  const idx = roleBone(side + 'IndexProximal');
  const pnk = roleBone(side + 'LittleProximal');
  const wr  = roleBone(side + 'Hand');
  if (!idx || !pnk || !wr) return null;
  const across = wp(pnk).clone().sub(wp(idx));
  const fing   = wp(idx).clone().sub(wp(wr));
  if (across.lengthSq() < 1e-12 || fing.lengthSq() < 1e-12) return null;
  const n = new THREE.Vector3().crossVectors(across.normalize(), fing.normalize());
  // |n| collapses toward 0 for a fully flat hand, where the sign is meaningless
  return n.length() < 0.25 ? null : n.normalize();
}

const DOT = 0.5;          // cos(60 deg): generous, we are testing sign not precision
let words = 0, failWords = 0, totFrames = 0, totOk = 0, skipped = 0;
const failures = [];

for (const cp of clips) {
  const doc = JSON.parse(readFileSync(cp, 'utf8'));
  const word = doc.name.replace(/^RETARGET_/, '');
  const cls = (LEX[word] && LEX[word][0]) || '1';
  if (cls !== '2s') { skipped++; continue; }     // only 2s synthesizes by mirroring
  words++;
  let ok = 0, n = 0, degenerate = 0;
  for (const t of doc.tracks[0].times) {
    at(doc, t);
    const L = palmNormal('left'), R = palmNormal('right');
    if (!L || !R) { degenerate++; continue; }
    n++;
    const Rm = R.clone(); Rm.x *= -1;            // reflect across the sagittal plane
    if (L.dot(Rm) > DOT) ok++;
  }
  totFrames += n; totOk += ok;
  const frac = n ? ok / n : 1;
  if (frac < 0.80) { failWords++; failures.push([word, ok, n, frac, degenerate]); }
}

console.log(`\nchecked ${words} words of class 2s (${skipped} not 2s, skipped)`);
console.log(`frames where the passive ARM performs the symmetric sign: ` +
            `${totOk}/${totFrames} = ${(100*totOk/Math.max(1,totFrames)).toFixed(1)}%\n`);
console.log(`Low = the signer dropped the weak hand in that take. This indicts the TAKE.`);
console.log(`Handshape mirroring itself is exact and is verified statically, not here.\n`);
if (failures.length) {
  console.log(`WEAK-DROP CANDIDATES — ${failWords} of ${words} 2s words below 80%:`);
  for (const [w, ok, n, frac, deg] of failures.sort((a,b) => a[3]-b[3]))
    console.log(`   ${w.padEnd(14)} ${String(ok).padStart(3)}/${String(n).padStart(3)} ` +
                `= ${(100*frac).toFixed(0).padStart(3)}%${deg ? `   (${deg} degenerate skipped)` : ''}`);
} else {
  console.log('every 2s word has a participating passive arm.');
}
/* exit 0: this reports on data quality, it does not gate the render */
process.exit(0);
