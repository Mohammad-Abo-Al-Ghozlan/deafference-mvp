/* Landmarks -> bone rotations. The animation-side half of the contract.
 *
 *   node retarget.mjs model.glb handoff/animation_handoff/words/hello.json
 *   node retarget.mjs model.glb handoff/animation_handoff/words/{hello,snow,black}.json
 *
 * INPUT   contract §1: 75 landmarks/frame, x,y shoulder-width-normalised (y DOWN),
 *         z raw MediaPipe units.
 * OUTPUT  our clip.json: quaternion tracks per bone, ready for rig-studio.html.
 *
 * ------------------------------------------------------------------------------
 * WHY NOT SCALE THE LANDMARKS ONTO THE AVATAR
 *
 * The obvious approach — scale landmark positions by the shoulder-width ratio and
 * use them as IK targets — inherits the signer's proportions. It needs a per-limb
 * calibration, and any mismatch shows up as a bent elbow.
 *
 * This takes only DIRECTIONS from the data and all LENGTHS from the avatar:
 *
 *   elbow = shoulder + L1_avatar * unit( dx, dy, dz )      dz from |dz| = sqrt(L1² - d2d²)
 *   wrist = elbow    + L2_avatar * unit( dx, dy, dz )
 *
 * The reconstructed limb is exactly the avatar's own length by construction, so the
 * proportion problem disappears and no per-limb scale factor is needed. That is also
 * why depth comes out for free: the out-of-plane component is whatever it must be to
 * make the bone reach, which is precisely the foreshortening the 2D data encodes.
 *
 * Measured on this rig vs this dataset the proportions agree closely anyway —
 * signer upper arm 0.631 shoulder-widths vs avatar 0.624 — so clamping is rare.
 *
 * ------------------------------------------------------------------------------
 * Z IS USED FOR ITS SIGN ONLY
 *
 * Calibration (`calibrate-z.py`) showed z carries NO recoverable magnitude: fitting
 * L² = dx²+dy²+(k·dz)² gives R² = 0.002–0.045, and one bone yields a physically
 * impossible positive slope. Applying the best-fit k leaves bone-length variation
 * unchanged (13.6% -> 13.6%). So magnitudes come from the rig; z supplies one bit
 * per segment — which side of the image plane the joint is on.
 *
 * That bit IS real: the sign flips only 4.0% of frames for the elbow and 1.1% for the
 * forearm, versus 12.2% / 2.8% when the same values are shuffled, and 141/250 words
 * never change elbow sign at all. Slowly-varying = physical. It is still smoothed
 * over a window, because a flicker costs a whole-arm swing.
 */
import * as THREE from 'three';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { loadRig, wp } from './vrm-load.mjs';
import { solveTwoBone, aim, orientHand, wpos, palmInward } from './ik.mjs';
import { measureBody, refreshBody, torsoClearance, headClearance } from './body-volumes.mjs';
import { clean } from './smooth.mjs';

const args = process.argv.slice(2);
const modelPath = args[0], wordPaths = args.slice(1);
if (!modelPath || !wordPaths.length){
  console.error('usage: node retarget.mjs model.glb word.json [word.json ...]');
  process.exit(2);
}

const ALLOW_NO_FINGERS = args.includes('--body-only');

/* Handedness lexicon (asl_handedness_250.json). Handedness is NOT derivable from these
 * landmarks — four landmark-based classifiers were tested against hand-labelled words and
 * all failed, the best at AUC 0.335 (i.e. inverted). It is supplied as lexical knowledge
 * instead. Class drives what we do about the passive hand, which is absent in every take:
 *    1   -> relaxed curl        (no second hand in the sign)
 *    2s  -> mirror the dominant (Symmetry Condition: same handshape, so this is exact)
 *    2a  -> unmarked handshape  (Dominance Condition: a DIFFERENT shape; never mirror) */
const lexArg = args.find(a => a.startsWith('--handedness='));
let LEX = {};
if (lexArg){
  LEX = JSON.parse(readFileSync(lexArg.slice('--handedness='.length), 'utf8')).words || {};
  console.log(`handedness lexicon: ${Object.keys(LEX).length} words`);
}
const other = s => (s === 'left' ? 'right' : 'left');

/* Unmarked handshape templates for class 2a (contract §6.1). 21 points in a canonical PALM
 * FRAME: origin at the wrist, x toward the index MCP, z the palm normal (index x pinky), y
 * right-handed, scaled by |wrist -> middle MCP| = 1, right-hand chirality.
 *
 * template_xyz is used rather than template_xy. The file warns that z is raw MediaPipe
 * relative depth and noisier, and for every shape agreement_xyz is indeed slightly worse than
 * agreement_xy (B 0.143 vs 0.131) — but template_xy is PLANAR, and a planar C or O is not the
 * handshape, it is a flat hand. The small extra noise is worth a shape that exists in 3D. */
const tplArg = args.find(a => a.startsWith('--templates='));
let TPL = null, TPL_RES = {};
if (tplArg){
  const t = JSON.parse(readFileSync(tplArg.slice('--templates='.length), 'utf8'));
  TPL = t.handshapes || {};
  TPL_RES = t.resolution || {};
  const usable = Object.entries(TPL).filter(([, v]) => v.usable).map(([k]) => k);
  console.log(`handshape templates: ${usable.length} usable (${usable.join(' ')})`);
}
/* Finger -> MediaPipe landmark indices comes from MP_FINGER, which already exists below.
 * I first wrote a second copy of that table here and keyed the pinky as 'Pinky'; this rig
 * names it 'Little', so the lookup silently returned undefined and the whole 2a branch never
 * fired — no error, just a relaxed hand where a template should have been. Duplicating a
 * mapping that already exists is how that happens. */
/* Output directory, so retargeting a second avatar cannot silently overwrite the first
 * one's clips -- which it did, because the filename is derived only from the word. */
const outArg = args.find(a => a.startsWith('--out='));
const OUT_DIR = outArg ? outArg.slice(6) : '.';
const wordPathsClean = wordPaths.filter(p => !p.startsWith('--'));
const { scene, byName, roleBone, roleSource, hasFingers, fingerCount } = await loadRig(modelPath);
if (!roleSource){ console.error('not a humanoid rig'); process.exit(2); }

/* A rig with no finger joints can carry location, movement and palm orientation, but not
 * HANDSHAPE — and handshape is one of the five phonemic parameters of a sign. CAT and
 * FATHER share location and movement and differ only by handshape, so roughly half the
 * vocabulary becomes ambiguous on a mitten hand. Refusing by default, with --body-only as
 * an explicit override, keeps that a decision someone made rather than something that
 * quietly shipped. */
if (!hasFingers){
  const msg = `${path.basename(modelPath)} has ${fingerCount}/30 finger joints — ` +
    `handshape cannot be expressed on this rig.`;
  if (!ALLOW_NO_FINGERS){
    console.error(`\nREFUSED: ${msg}`);
    console.error('Handshape is phonemic: CAT and FATHER differ by it alone, so ~half the');
    console.error('vocabulary would be ambiguous. Re-run with --body-only if you want arm and');
    console.error('body motion anyway (for preview or comparison), knowing handshape is lost.\n');
    process.exit(2);
  }
  console.warn(`\nWARNING: ${msg}`);
  console.warn('Proceeding --body-only: arms, torso and head only. NOT usable for signing.\n');
}
if (OUT_DIR !== '.') mkdirSync(OUT_DIR, { recursive: true });
const V = (x, y, z) => new THREE.Vector3(x, y, z);

/* ---------------- avatar frame + bone lengths ---------------- */
scene.updateMatrixWorld(true);
const UP    = wp(roleBone('head')).sub(wp(roleBone('hips'))).normalize();
const RIGHT = wp(roleBone('rightUpperArm')).sub(wp(roleBone('leftUpperArm'))).normalize();
const FWD   = new THREE.Vector3().crossVectors(UP, RIGHT).normalize();

const rest = new Map();
scene.traverse(o => { if (o.isBone) rest.set(o, o.quaternion.clone()); });
const toRest = () => { for (const [b, q] of rest) b.quaternion.copy(q); scene.updateMatrixWorld(true); };
toRest();

/* ---------------- hand rig + MediaPipe hand topology ----------------
 * MediaPipe gives 21 points per hand: wrist(0) then 4 per finger. Four points define
 * exactly three bone directions, and this rig has exactly three bones per finger, so
 * the mapping is 1:1 with nothing to solve — MCP->PIP, PIP->DIP, DIP->TIP. The thumb
 * uses VRM's metacarpal/proximal/distal naming for the same three bones. */
const MP_FINGER = { Thumb: [1,2,3,4], Index: [5,6,7,8], Middle: [9,10,11,12],
                    Ring: [13,14,15,16], Little: [17,18,19,20] };
const SEG_OF = f => f === 'Thumb' ? ['Metacarpal','Proximal','Distal']
                                  : ['Proximal','Intermediate','Distal'];

const SHOULDER_W = wp(roleBone('rightUpperArm')).distanceTo(wp(roleBone('leftUpperArm')));
const LIMB = {};
for (const s of ['left', 'right']){
  const u = roleBone(s + 'UpperArm'), l = roleBone(s + 'LowerArm'), h = roleBone(s + 'Hand');
  const chains = {};
  for (const f of Object.keys(MP_FINGER)){
    const bones = SEG_OF(f).map(g => roleBone(s + f + g));
    if (bones.every(Boolean)){
      // bone lengths: joint to next joint, last one estimated from the previous
      const len = [];
      for (let i = 0; i < 3; i++){
        const nxt = bones[i + 1];
        len.push(nxt ? wp(nxt).distanceTo(wp(bones[i]))
                     : wp(bones[2]).distanceTo(wp(bones[1])) * 0.8);
      }
      chains[f] = { bones, len, mp: MP_FINGER[f] };
    }
  }
  LIMB[s] = { upper: u, lower: l, hand: h, chains,
              knuckle: roleBone(s + 'MiddleProximal'),
              across: [roleBone(s + 'IndexProximal'), roleBone(s + 'LittleProximal')],
              L1: wp(l).distanceTo(wp(u)), L2: wp(h).distanceTo(wp(l)) };
}
console.log(`rig ${path.basename(modelPath)}: shoulder ${(SHOULDER_W*100).toFixed(1)} cm · ` +
  `upper arm ${(LIMB.right.L1*100).toFixed(1)} cm · forearm ${(LIMB.right.L2*100).toFixed(1)} cm ` +
  `(= ${(LIMB.right.L1/SHOULDER_W).toFixed(3)} / ${(LIMB.right.L2/SHOULDER_W).toFixed(3)} shoulder-widths)`);

/* ---------------- body collision volumes ----------------
 * Imported from the same module the anatomy gate uses, so the solver optimises exactly
 * what the gate measures. Fitting them separately in each tool let the two drift, and a
 * solver scored against a slightly different body than the checker is how the sign solve
 * "improved" motion quality while gate failures went UP from 19 to 23.
 *
 * Clearances are calibrated against the REST pose, not zero: the shoulder joint sits
 * inside a capsule fitted to the torso, so the shipped T-pose already reads as ~7 cm of
 * penetration. Rest is by definition valid, so only penetrating MORE than rest is a
 * defect. Same convention as pose-check.mjs. */
const BODY = measureBody(scene, roleBone);
if (!BODY.head || !BODY.torso){ console.error('could not measure body volumes'); process.exit(2); }
const SH_POS = {}, REST_CLEAR = {}, LIMB_R = {};
for (const s of ['left', 'right']){
  const L = LIMB[s], lb = BODY.limbs.find(x => x.side === s);
  LIMB_R[s] = lb ? lb.r : 0.03;
  /* Rest shoulder position. This used to be exact -- only bones BELOW the shoulder were
   * animated -- but the spine and the shoulder girdle now move too, so this is the Viterbi
   * cost's starting estimate, refreshed per frame in the solve. The anatomy gate measures
   * the real posed skeleton and remains the authority. */
  SH_POS[s] = wp(L.upper).clone();
  const sh = wp(L.upper), el = wp(L.lower), wr = wp(L.hand);
  REST_CLEAR[s] = {
    upperTorso: torsoClearance(BODY, sh, el, LIMB_R[s]),
    foreTorso:  torsoClearance(BODY, el, wr, LIMB_R[s]),
    upperHead:  headClearance (BODY, sh, el, LIMB_R[s]),
    foreHead:   headClearance (BODY, el, wr, LIMB_R[s]),
  };
}
/* Denoise tuning. Windows in FRAMES at 30 fps. Arms carry the fast signal and are well
 * tracked, so they get the shortest window; hands are noisier; head/torso are slow and can
 * take the widest. spikeK is in robust (MAD) units. */
const ARM_OPT  = { spikeWin: 5, spikeK: 3.5, sgWindow: 5 };
const HAND_OPT = { spikeWin: 5, spikeK: 3.0, sgWindow: 7 };
const BODY_OPT = { spikeWin: 7, spikeK: 3.5, sgWindow: 11 };

/* legacy One-Euro tuning, kept only so the sweep harness still runs. ARM and HAND are
 * deliberately DIFFERENT, and the sweep showed why: they
 * control independent things. Arm cutoff sets how much of the sign's motion survives; hand
 * cutoff sets how much finger noise gets through. Measured over 10 words:
 *
 *    aCut  hCut   amplitude%   arm jerk/vel
 *     1.6   1.3      32.6          0.301      <- old: two thirds of the motion thrown away
 *     4.5   1.3      49.4          0.446      <- chosen
 *       8   1.3      56.5          0.514      <- past the knee, arms start to buzz
 *
 * 4.5 Hz is where the SIGNAL lives: a power spectrum of the wrist offsets puts 90% of the
 * sign's energy below 3.75 Hz and 95% below 6.1 Hz, so a cutoff just past that knee keeps
 * the sign and drops the tail. The signer's own raw jerk/vel is 0.909, so 0.446 is still
 * half as jittery as the source.
 *
 * Amplitude is the avatar's wrist path length as a fraction of the signer's. The structural
 * ceiling is ~74% because the avatar's arm is 1.261 shoulder-widths against the signer's
 * 1.705 — the same angles simply sweep a shorter arc. 65.2% is 88% of what is achievable.
 *
 * The old 1.6/0.02 was throwing away two thirds of the motion, which is why signs read as a
 * held pose with a wobble rather than as movement. Arm landmarks are large and 99.2%
 * present, so they do not need that protection; hand landmarks are small and noisy and
 * still do. */
const ARM_CUT   = +(process.env.ARM_CUT   ?? 4.5);
const ARM_BETA  = +(process.env.ARM_BETA  ?? 0.4);
const HAND_CUT  = +(process.env.HAND_CUT  ?? 1.3);
const HAND_BETA = +(process.env.HAND_BETA ?? 0.02);
/* Relaxed-hand curl per joint, in degrees, applied when a hand has no landmark data.
 * These are the resting angles of a hand hanging by the side — the fingers curl
 * progressively and the thumb rests alongside rather than sticking out. Deliberately
 * modest: a strong fist would assert a handshape the data never contained, whereas a soft
 * curl reads as "no particular handshape", which is the honest state. */
const RELAX_CURL = {
  Thumb:  [14, 10,  8],
  Index:  [22, 28, 16],
  Middle: [25, 32, 18],
  Ring:   [26, 33, 19],
  Pinky:  [27, 34, 20],
  default:[24, 30, 18],
};
const CONTACT_ALLOW = 0.05;   // 5 cm; sign language legitimately touches the body

/* ---------------- head / spine / shoulder ----------------
 * Gains convert a normalised landmark offset into degrees; maxima are human joint limits.
 * Both are intentionally conservative. The landmark measurements are noisiest exactly at
 * the extremes, and an over-rotated head reads as broken while an under-rotated one merely
 * reads as calm — so the failure mode is chosen deliberately. */
const BONE = {
  neck: roleBone('neck'), head: roleBone('head'),
  spine: roleBone('spine'), chest: roleBone('chest'), upperChest: roleBone('upperChest'),
  shoulder: { left: roleBone('leftShoulder'), right: roleBone('rightShoulder') },
};
const HEAD_ON    = !!(BONE.neck || BONE.head);
const YAW_GAIN   = 150, YAW_MAX   = 38;   // nose crosses an ear at ~0.5 -> ~75 deg
const PITCH_GAIN = 190, PITCH_MAX = 24;
const ROLL_MAX   = 20;
const LEAN_GAIN  = 55,  LEAN_MAX  = 11;
const clampDeg = (v, m) => Math.max(-m, Math.min(m, v));

/* Scapulohumeral rhythm: the shoulder girdle contributes roughly a third of total arm
 * elevation past horizontal. Rigs that pin the clavicle and rotate only the humerus
 * collapse the deltoid and look stiff exactly when the arm goes high — which in ASL is
 * most signs. This is derived from the solved arm rather than from landmarks, because the
 * shoulder landmark barely moves while the scapula rotates underneath it. */
/* Rest bracket. Long enough to read as the arm arriving and leaving, short enough not to
 * pad the vocabulary: 0.25 s each side against a 2.13 s sign. */
/* Rest lead-in / lead-out, in seconds — but CAPPED as a fraction of the sign.
 *
 * 0.25 s each was tuned when every clip in the handoff was time-normalised to 64 frames
 * (2.13 s), where the lead is 12% of the clip. The v7 export ships native durations spanning
 * 9 to 116 frames, and at 9 frames `tiger` is 0.30 s — so a fixed 0.25 s lead-in would be
 * most of the clip and the two eases together would be 1.5x the sign itself. The sign would
 * be a brief event inside a long approach.
 *
 * This is the class of thing the switch to native duration breaks silently: nothing errors,
 * the clip just stops reading as a sign. Anything else tuned against 2.13 s belongs here. */
const LEAD_MAX = 0.25, LEAD_FRAC = 0.15;
const leadFor = dur => Math.min(LEAD_MAX, LEAD_FRAC * Math.max(0, dur));
/* ---------------- idle pose ----------------
 * The clip brackets used to ease to and from the rig's REST pose — which on this avatar is
 * a T-POSE, arms straight out sideways. So every sign began and ended with the avatar
 * standing like a scarecrow and snapping in and out of it. No signer has ever done that,
 * and it is the single most unnatural thing in the output.
 *
 * A signer's rest is arms hanging down, slightly away from the body, elbows a little bent.
 * Built here by aiming rather than hardcoding Euler angles, so it works on any rig whose
 * arms are resolved, whatever its bind pose. */
const IDLE = new Map();
{
  toRest();
  const DOWNV = UP.clone().negate();
  for (const s of ['left', 'right']){
    const L = LIMB[s];
    const out = RIGHT.clone().multiplyScalar(s === 'left' ? -1 : 1);
    const upperDir = DOWNV.clone().addScaledVector(out, 0.20).addScaledVector(FWD, 0.04).normalize();
    const foreDir  = DOWNV.clone().addScaledVector(out, 0.10).addScaledVector(FWD, 0.20).normalize();
    aim(L.upper, L.lower, upperDir, scene);
    aim(L.lower, L.hand,  foreDir,  scene);
  }
  scene.traverse(o => { if (o.isBone && !o.quaternion.equals(rest.get(o))) IDLE.set(o, o.quaternion.clone()); });
  toRest();
}
/** Pose a clip should relax into: the idle where it exists, the bind pose elsewhere. */
const idleQuat = b => IDLE.get(b) || rest.get(b);

const SHRUG_MAX = 20;
const SHRUG_N = { n: 0 };   // module-level: shrug() runs outside retarget()'s report scope
const DOWN = UP.clone().negate();
/* Elevation is measured from ARMS-HANGING, which is the anatomical reference — not from
 * the rig's rest, which is a T-pose. That distinction matters: a T-pose is already 90 deg
 * of abduction and therefore already carries ~20 deg of scapular rotation. Measuring the
 * delta from the T-pose instead made the shrug fire only for arms raised ABOVE horizontal,
 * which almost never happens in signing (the elbow stays low even when the hand is at the
 * face), so it never fired at all.
 *
 * Below ~30 deg the scapula barely moves; past that the humerus and scapula share the
 * motion roughly 2:1. */
const scap = eDeg => Math.max(0, Math.min(35, (eDeg - 30) / 3));
const REST_ELEV = {};
for (const s of ['left', 'right']){
  const rd = wp(LIMB[s].lower).clone().sub(wp(LIMB[s].upper)).normalize();
  REST_ELEV[s] = THREE.MathUtils.radToDeg(Math.acos(
    Math.max(-1, Math.min(1, rd.dot(DOWN)))));
}

/** Rotate the shoulder by the scapular share of this frame's arm elevation, relative to
 *  whatever the rig's own rest pose already implies. */
function shrug(side, targetDir){
  const sb = BONE.shoulder[side]; if (!sb) return;
  const e = THREE.MathUtils.radToDeg(Math.acos(
    Math.max(-1, Math.min(1, targetDir.dot(DOWN)))));
  const deltaDeg = Math.max(-SHRUG_MAX, Math.min(SHRUG_MAX, scap(e) - scap(REST_ELEV[side])));
  if (Math.abs(deltaDeg) < 0.05) return;
  /* rotate about the axis that carries the arm away from hanging */
  const axis = new THREE.Vector3().crossVectors(DOWN, targetDir);
  if (axis.lengthSq() < 1e-10) return;
  const q = new THREE.Quaternion().setFromAxisAngle(axis.normalize(),
    THREE.MathUtils.degToRad(deltaDeg));
  const d0 = wp(LIMB[side].upper).clone().sub(wp(sb));
  if (d0.lengthSq() < 1e-12) return;
  aim(sb, LIMB[side].upper, d0.normalize().applyQuaternion(q), scene);
  SHRUG_N.n++;
}

/* Palm axis per hand, measured once in the rest pose and stored in the hand bone's LOCAL
 * frame so it follows the wrist without being re-derived (and re-guessed) each frame.
 * Direction comes from the thumb via palmInward(), which is cross-checked against the
 * mesh centroid by checkPalmPad() and agrees on both rigs. Finger joints flex toward
 * this direction and essentially never away from it. */
const PALM = {};
for (const s of ['left', 'right']){
  const L = LIMB[s];
  const thumb = (L.chains.Thumb?.bones || []).filter(Boolean);
  if (!L.hand || !L.knuckle || !L.across.every(Boolean) || !thumb.length) continue;
  const { inward, margin } = palmInward(L.hand, L.knuckle, L.across, thumb);
  PALM[s] = { local: inward.clone()
                .applyQuaternion(L.hand.getWorldQuaternion(new THREE.Quaternion()).invert()),
              margin };
}

/* ---------------- landmark indices (contract §2) ---------------- */
const LM = { LSH: 11, RSH: 12, LEL: 13, REL: 14, LWR: 15, RWR: 16, LHIP: 23, RHIP: 24,
             NOSE: 0, EARL: 7, EARR: 8, EYEL: 2, EYER: 5 };
/* The POSE block also carries three points per hand — pinky, index and thumb knuckles.
 * They are present in 99.2% of frames, including 98.8% of the frames where the detailed
 * 21-point hand block is missing. That is enough to orient the WRIST everywhere, even
 * where handshape is unrecoverable. Without them the hand sat in its bind orientation on
 * a moving arm for ~60% of frames, which is the single most obviously fake thing in the
 * output: a live arm carrying a dead hand. */
const SIDE_LM = { left:  { sh: LM.LSH, el: LM.LEL, wr: LM.LWR, hand: 33,
                           pinky: 17, index: 19, thumb: 21 },
                  right: { sh: LM.RSH, el: LM.REL, wr: LM.RWR, hand: 54,
                           pinky: 18, index: 20, thumb: 22 } };

const okPt = p => Array.isArray(p) && p.length === 3 && p.every(v => typeof v === 'number' && !Number.isNaN(v));

/* ---------------- per-limb calibration (contract §11) ----------------
 * The signer's limb-to-shoulder ratio is not the avatar's. Measured here the signer's
 * upper arm is 0.63 shoulder-widths against the avatar's 0.625, and that 1% is enough
 * to matter: whenever the projected 2D length exceeds the avatar's bone, the solver
 * has to clamp, which drives dz to zero and flattens the elbow into the frontal plane
 * — the exact failure that dropping z would have caused. Uncalibrated, 88% of
 * segments clamped.
 *
 * The signer's true limb length is estimated as the 99th percentile of the projected
 * 2D length over the whole corpus: a projection can never exceed the true length, so
 * the upper tail IS the length (the frames where the limb lies parallel to the image
 * plane). p99 not max, to shrug off tracking spikes. */
function calibrate(files){
  const seg = { upper: [], fore: [] };
  /* Phalanges need the same treatment and need it MORE. The signer's phalanx lengths run
   * 1.3-2.5x the avatar's in shoulder-widths, so reconstructing phalanx depth against the
   * avatar's bone clamped up to 89% of thumb frames and ~70% of distal frames — dz driven
   * to zero, the phalanx flattened into the coronal plane, and fingers that read as
   * rubbery or broken. Same bug as the arm had; the arm was just less extreme. */
  const fing = {};
  for (const f of Object.keys(MP_FINGER)) fing[f] = [[], [], []];
  const head = { yaw: [], pitch: [], roll: [], lean: [] };
  for (const f of files){
    let d; try { d = JSON.parse(readFileSync(f, 'utf8')); } catch { continue; }
    for (const fr of d.frames || []){
      if (!Array.isArray(fr) || fr.length < 75) continue;
      if (!(okPt(fr[LM.LSH]) && okPt(fr[LM.RSH]))) continue;
      const w = Math.hypot(fr[LM.RSH][0] - fr[LM.LSH][0], fr[LM.RSH][1] - fr[LM.LSH][1]) || 1;
      {
        const P = i => V(fr[i][0], -fr[i][1], 0);       // same y-flip as the solve
        const ax = P(LM.RSH).sub(P(LM.LSH)).normalize();
        const ht = headTorso(fr, P, ax, w);
        if (ht) for (const k of Object.keys(head)) head[k].push(ht[k]);
      }
      for (const s of ['left', 'right']){
        const L = SIDE_LM[s];
        if (okPt(fr[L.sh]) && okPt(fr[L.el]) && okPt(fr[L.wr])){
          seg.upper.push(Math.hypot(fr[L.el][0] - fr[L.sh][0], fr[L.el][1] - fr[L.sh][1]) / w);
          seg.fore .push(Math.hypot(fr[L.wr][0] - fr[L.el][0], fr[L.wr][1] - fr[L.el][1]) / w);
        }
        if (!handPresent(fr, L.hand)) continue;
        for (const [fname, idx] of Object.entries(MP_FINGER))
          for (let i = 0; i < 3; i++){
            const a = fr[L.hand + idx[i]], b = fr[L.hand + idx[i + 1]];
            if (okPt(a) && okPt(b)) fing[fname][i].push(Math.hypot(b[0]-a[0], b[1]-a[1]) / w);
          }
      }
    }
  }
  const p = (a, q) => { a.sort((x, y) => x - y); return a[Math.min(a.length - 1, Math.floor(a.length * q))]; };
  const fingP = {};
  for (const f of Object.keys(fing))
    fingP[f] = fing[f].map(a => a.length ? p(a, 0.99) : null);
  /* Head and torso NEUTRALS. A per-clip median would be wrong — a sign whose head is turned
   * throughout would have that turn defined away as its own neutral — so these come from
   * the corpus.
   *
   * But YAW, ROLL and LEAN are CHIRAL: mirroring a word negates all three. Taking their
   * corpus median therefore makes the calibration depend on how many words happen to be
   * mirrored, and dominant-hand normalisation mirrors 147 of 250. Measured consequence:
   * every clip changed, including ones that were never mirrored, and `tooth` flipped which
   * hand it signs with. A batch-wide constant that shifts when you add or flip words is a
   * bad property regardless of normalisation — it means a clip is not reproducible from its
   * own source.
   *
   * A signer facing the camera has no systematic left/right head turn or lean, so the
   * principled neutral for all three is ZERO. Pitch is not chiral (mirroring leaves it
   * alone) and does have a real resting offset, so it keeps its median. */
  const neutral = { yaw: 0, roll: 0, lean: 0,
                    pitch: p(head.pitch, 0.5), n: head.yaw.length };
  return { upper: p(seg.upper, 0.99), fore: p(seg.fore, 0.99), n: seg.upper.length,
           fing: fingP, nHand: fing.Index[0].length, neutral };
}
/* ---------------- head + torso, from landmarks the pipeline never used ----------------
 * Face points 0-10 and hips 23/24 are present in 99.2% of frames and drove nothing: the
 * head and spine sat in bind pose for every sign. A signer whose head never moves reads as
 * a mannequin, and in ASL head position is not decoration — head tilt and shake carry
 * grammar.
 *
 * These are measured as SCALARS from 2D relationships rather than as a 3D head frame,
 * deliberately: z has no usable magnitude (§3), and yaw/pitch/roll are all well determined
 * in the image plane alone.
 *
 *   yaw    nose displaced from the ear midpoint ALONG the ear axis
 *   pitch  nose displaced from the ear midpoint vertically
 *   roll   ear axis tilted against the shoulder axis
 *   lean   shoulder midpoint displaced laterally from the hip midpoint
 *
 * Each is returned in its raw normalised unit; the neutral offset and the mapping to
 * degrees are applied later, so calibration and use share one definition. */
function headTorso(fr, P, ax, w){
  const need = [LM.NOSE, LM.EARL, LM.EARR, LM.LSH, LM.RSH, LM.LHIP, LM.RHIP];
  if (!need.every(i => okPt(fr[i]))) return null;
  const earL = P(LM.EARL), earR = P(LM.EARR);
  const earMid = earL.clone().add(earR).multiplyScalar(0.5);
  const earAx = earR.clone().sub(earL);
  const earW = earAx.length() || 1;
  const d = P(LM.NOSE).sub(earMid);
  const shMid  = P(LM.LSH).clone().add(P(LM.RSH)).multiplyScalar(0.5);
  const hipMid = P(LM.LHIP).clone().add(P(LM.RHIP)).multiplyScalar(0.5);
  return {
    yaw:   d.dot(earAx) / (earW * earW),          // +ve = nose toward signer's right ear
    pitch: d.y / earW,
    roll:  Math.atan2(earAx.y, earAx.x) - Math.atan2(ax.y, ax.x),
    lean:  shMid.sub(hipMid).dot(ax) / w,
  };
}

/** A hand block written as 21 exact zeros is MISSING, not "at the origin". */
const handPresent = (fr, base) => {
  const pts = fr.slice(base, base + 21);
  return pts.every(okPt) && pts.some(p => p.some(v => Math.abs(v) > 1e-9));
};

/* ---------------- One-Euro filter on the 2D landmarks ---------------- */
/* Smoothing is the animator's job per §10, applied BEFORE the IK solve: filtering
   positions is well-posed, filtering the solved rotations afterwards fights the
   solver and smears the handshape. */
class OneEuro {
  constructor(fps, minCutoff = 1.6, beta = 0.02, dCutoff = 1.0){
    Object.assign(this, { fps, minCutoff, beta, dCutoff });
    this.x = null; this.dx = 0;
  }
  alpha(cutoff){ const te = 1 / this.fps, tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / te); }
  /** Forget history. Needed because hand data is INTERMITTENT: the filter only sees the
   *  frames where a hand block exists, so across a 27-frame gap it would treat two poses
   *  27 frames apart as consecutive and smooth between them — inventing a slow drift where
   *  the data actually says nothing at all. */
  reset(){ this.x = null; this.dx = 0; }
  filter(v){
    if (this.x === null){ this.x = v; return v; }
    const dRaw = (v - this.x) * this.fps;
    this.dx += this.alpha(this.dCutoff) * (dRaw - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x += this.alpha(cutoff) * (v - this.x);
    return this.x;
  }
}

/** majority sign over a centred window — one flicker costs a whole-arm swing */
function smoothSigns(raw, win = 5){
  const out = [];
  for (let i = 0; i < raw.length; i++){
    let s = 0;
    for (let j = Math.max(0, i - win >> 1); j <= Math.min(raw.length - 1, i + (win >> 1)); j++)
      s += raw[j] >= 0 ? 1 : -1;
    out.push(s >= 0 ? 1 : -1);
  }
  return out;
}

/* ---------------- per-word retarget ---------------- */
const round6 = n => Math.round(n * 1e6) / 1e6;

function retarget(doc, name){
  const F = doc.frames, fps = doc.fps || 30;
  SHRUG_N.n = 0;
  /* Reset the shared body volumes to the REST pose before solving this word.
   *
   * refreshBody() moves the torso capsule and head sphere onto the current pose, and the
   * depth-sign Viterbi reads them — but the Viterbi runs BEFORE the per-frame loop, so
   * without this it sees the body wherever the PREVIOUS WORD's last frame left it. That
   * made a clip's output depend on what else was in the batch: mirroring 147 words for
   * dominant-hand normalisation silently changed 20 words that were never mirrored, and
   * flipped which hand `tooth` signs with. A clip has to be reproducible from its own
   * source alone. */
  toRest();
  refreshBody(BODY);
  /* Read the class from the export's own synthesis block, NOT by re-deriving it here.
   *
   * Re-deriving cost 249 words once: two sides computed "dominant" differently (absolute
   * wrist travel vs shoulder-relative path with an elbow gate) and neither metric could see
   * the other's failure. They disagree on exactly one word — `finish`, whose travel ratio is
   * 1.00, a perfect tie — and a tie re-rolled independently on each side will keep landing
   * differently forever. The exporter now asserts dominantHand, so read it.
   *
   * Lexicon join kept only as a fallback for pre-v16 exports that carry no synthesis block. */
  const SYN = doc.segments?.[0]?.synthesis || null;
  const HANDCLASS = SYN?.class || (LEX[name] && LEX[name][0]) || '1';
  const DOMINANT = SYN?.dominantHand || null;      // 'R' in all 250 by construction
  const PASSIVE_SHAPE = SYN?.passiveHandshape?.shape || null;
  const report = { name, handClass: HANDCLASS, frames: F.length, dropped: 0, flattened: 0,
    fingClamped: 0, fingSignFlips: 0, fingHingeClamped: 0, outOfReach: 0, spikesRemoved: 0,
    relaxedHands: 0, mirroredHands: 0, templateHands: 0,
    coarseHand: { left: 0, right: 0 },
    hands: { left: 0, right: 0 }, handFrames: { left: 0, right: 0 } };

  /* 1. usable frames. A whole-frame null is dropped and bridged by the track's own
        interpolation — there is no partial-landmark case in this dataset. */
  const valid = F.map(fr => Array.isArray(fr) && fr.length >= 75 &&
    [LM.LSH, LM.RSH, LM.LEL, LM.REL, LM.LWR, LM.RWR, LM.LHIP, LM.RHIP].every(i => okPt(fr[i])));
  report.dropped = valid.filter(v => !v).length;

  /* 2. signer frame per frame, from the shoulders. Rebuilt every frame so a leaning
        or rotating signer does not drag the whole pose with them. y is FLIPPED here
        (§3: image y points down). */
  const F2 = [];                    // per frame: 2D offsets in the signer's own frame
  for (let t = 0; t < F.length; t++){
    if (!valid[t]){ F2.push(null); continue; }
    const fr = F[t];
    const P = i => V(fr[i][0], -fr[i][1], 0);            // flip y
    const sL = P(LM.LSH), sR = P(LM.RSH);
    const across = sR.clone().sub(sL);                    // signer's right, in-plane
    const w = across.length() || 1;
    const ax = across.clone().divideScalar(w);
    /* In-plane UP must come from the body, not from rotating `ax` 90 degrees. A
       rotation flips sign with the shoulder ordering, and in this dataset the signer's
       right is at SMALLER x in 100% of frames (contract §3 claims the opposite), so
       "up" came out pointing DOWN. Vertical was inverted: the resting arm was raised
       and the signing arm driven into the floor. Derived from the torso instead. */
    const hipMid = P(LM.LHIP).add(P(LM.RHIP)).multiplyScalar(0.5);
    const shMid  = sL.clone().add(sR).multiplyScalar(0.5);
    let ay = shMid.clone().sub(hipMid);
    ay.addScaledVector(ax, -ay.dot(ax));                  // orthogonalise against ax
    if (ay.lengthSq() < 1e-9) ay = V(0, 1, 0);            // fallback: +y is up post-flip
    ay.normalize();
    const proj = (p, o) => { const d = p.clone().sub(o); return { x: d.dot(ax) / w, y: d.dot(ay) / w }; };
    const e = {};
    for (const s of ['left', 'right']){
      const L = SIDE_LM[s];
      /* coarse hand frame from the POSE block (present 99.2% of frames) */
      const coarse = [L.pinky, L.index, L.thumb].every(i => okPt(fr[i]))
        ? { pinky: proj(P(L.pinky), P(L.wr)), index: proj(P(L.index), P(L.wr)),
            thumb: proj(P(L.thumb), P(L.wr)),
            zPinky: fr[L.pinky][2] - fr[L.wr][2], zIndex: fr[L.index][2] - fr[L.wr][2] }
        : null;
      e[s] = { el: proj(P(L.el), P(L.sh)), wr: proj(P(L.wr), P(L.el)),
               zEl: fr[L.el][2] - fr[L.sh][2], zWr: fr[L.wr][2] - fr[L.el][2],
               coarse,
               hand: handPresent(fr, L.hand),
               // raw hand block, projected into the same signer frame
               hpts: handPresent(fr, L.hand)
                 ? Array.from({ length: 21 }, (_, i) => {
                     const q = proj(P(L.hand + i), P(L.hand));
                     return { x: q.x, y: q.y, z: fr[L.hand + i][2] - fr[L.hand][2] };
                   })
                 : null };
      if (e[s].hand) report.hands[s]++;
    }
    e.body = headTorso(fr, P, ax, w);
    F2.push(e);
  }

  /* 3. filter the 2D offsets */
  /* One-Euro tuning. beta is what lets FAST motion through: with beta too low the cutoff
   * barely rises with speed and the filter attenuates the sign itself, not just the noise.
   * Swept against measured amplitude (wrist path length vs the signer's) and measured
   * smoothness (jerk/velocity) — see the note above ARM_BETA. */
  const filters = {};
  for (const s of ['left', 'right'])
    filters[s] = { elx: new OneEuro(fps, ARM_CUT, ARM_BETA), ely: new OneEuro(fps, ARM_CUT, ARM_BETA),
                   wrx: new OneEuro(fps, ARM_CUT, ARM_BETA), wry: new OneEuro(fps, ARM_CUT, ARM_BETA) };
  /* ---- 3b. denoise ----
   *
   * Replaces the One-Euro low-pass that used to live here. A low-pass cannot tell a fast
   * REAL movement from a fast FAKE one, so tuning it only slides along a trade: filtering
   * hard enough to kill the landmark noise cost 26.7 points of wrist travel (51% of the
   * signer's path with it, 78% without). Tracking noise is impulsive and limb motion is
   * continuous, so the two are separated explicitly — reject spikes with a median test,
   * then smooth with Savitzky-Golay, which fits a curve THROUGH a peak instead of cutting
   * it off. See smooth.mjs.
   *
   * Runs are cleaned separately across data gaps: a gap is a real discontinuity, and
   * smoothing over one invents a movement between two poses that were never connected. */
  const runsOf = idxs => {
    const runs = []; let cur = [];
    for (let i = 0; i < idxs.length; i++){
      if (cur.length && idxs[i] !== idxs[i-1] + 1){ runs.push(cur); cur = []; }
      cur.push(idxs[i]);
    }
    if (cur.length) runs.push(cur);
    return runs;
  };
  /* read a channel over the given frames, clean it, write it back */
  const cleanChannel = (idxs, get, set, opts) => {
    for (const run of runsOf(idxs)){
      if (run.length < 5) continue;                 // too short to distinguish signal
      const { out, replaced } = clean(run.map(get), opts);
      run.forEach((t, i) => set(t, out[i]));
      report.spikesRemoved += replaced;
    }
  };

  const validIdx = [...F2.keys()].filter(t => F2[t]);
  for (const s of ['left', 'right']){
    /* arms: present on 99.2% of frames, so a light window keeps fast movement */
    cleanChannel(validIdx, t => F2[t][s].el.x, (t,v) => F2[t][s].el.x = v, ARM_OPT);
    cleanChannel(validIdx, t => F2[t][s].el.y, (t,v) => F2[t][s].el.y = v, ARM_OPT);
    cleanChannel(validIdx, t => F2[t][s].wr.x, (t,v) => F2[t][s].wr.x = v, ARM_OPT);
    cleanChannel(validIdx, t => F2[t][s].wr.y, (t,v) => F2[t][s].wr.y = v, ARM_OPT);

    /* detailed hand block: small, noisy landmarks, so a wider window and a tighter
     * spike threshold than the arms get */
    const handIdx = validIdx.filter(t => F2[t][s].hpts);
    for (let i = 0; i < 21; i++)
      for (const k of ['x','y','z'])
        cleanChannel(handIdx, t => F2[t][s].hpts[i][k],
                     (t,v) => F2[t][s].hpts[i][k] = v, HAND_OPT);

    /* coarse knuckles from the pose block */
    const cIdx = validIdx.filter(t => F2[t][s].coarse);
    for (const [g, st] of [
      [t => F2[t][s].coarse.pinky.x, (t,v) => F2[t][s].coarse.pinky.x = v],
      [t => F2[t][s].coarse.pinky.y, (t,v) => F2[t][s].coarse.pinky.y = v],
      [t => F2[t][s].coarse.index.x, (t,v) => F2[t][s].coarse.index.x = v],
      [t => F2[t][s].coarse.index.y, (t,v) => F2[t][s].coarse.index.y = v],
      [t => F2[t][s].coarse.zPinky,  (t,v) => F2[t][s].coarse.zPinky  = v],
      [t => F2[t][s].coarse.zIndex,  (t,v) => F2[t][s].coarse.zIndex  = v],
    ]) cleanChannel(cIdx, g, st, HAND_OPT);
  }
  /* head and torso move slowly and their landmarks are small, so they take the widest
   * window — the one place where heavy smoothing costs nothing, because there is no fast
   * signal to protect. */
  const bodyIdx = validIdx.filter(t => F2[t].body);
  for (const k of ['yaw','pitch','roll','lean'])
    cleanChannel(bodyIdx, t => F2[t].body[k], (t,v) => F2[t].body[k] = v, BODY_OPT);

  /* 4. depth signs — chosen by ANATOMY and CONTINUITY, with z as a prior.
   *
   * forward = -z (smaller z is nearer the camera, §"heads-up").
   *
   * Smoothing the elbow bit and the wrist bit independently — which is what this did
   * before — treats them as independent when they are not. The arm is a chain: an
   * elbow-in-front / wrist-behind combination folds the elbow BACKWARD, which no human
   * elbow does. Measured over the corpus, independent smoothing produced 270 backward-
   * folding frames across 23 words, and 28 angular jumps of up to 153 deg/frame (4590
   * deg/s) where one bit flipped between adjacent frames. Both read as exactly the
   * "non-physical" motion they are.
   *
   * z cannot arbitrate this — it carries one bit and no magnitude (§3). But two
   * constraints are available that z knows nothing about:
   *
   *   ANATOMY     the elbow folds toward the front of the body, and ASL is performed in
   *               front of the body, so the wrist does not sit behind the shoulder plane
   *   CONTINUITY  consecutive frames must be reachable from one another
   *
   * So all four sign combinations are scored per frame and the sequence is solved
   * EXACTLY over the whole clip by Viterbi — not greedily, so one bad frame cannot drag
   * the rest of the sequence after it. z stays as the prior, because it is right most of
   * the time; it is simply no longer the only vote. depth-probe.mjs showed the correct
   * sign reconstructs the pose to 0 mm, so this recovers poses rather than approximating.
   *
   * Weights: a backward elbow is the grossest violation so it dominates; disagreeing with
   * z costs a fixed amount per segment; a flip must buy its way past the continuity term. */
  const W_BACK = 3.0, W_BEHIND = 0.8, W_PRIOR = 1.0, W_SMOOTH = 1.2, W_PEN = 4.0;
  const BEND_MIN = 0.35;            // ~20 deg; below this the fold direction is undefined
  const STATES = [[1, 1], [1, -1], [-1, 1], [-1, -1]];

  const signs = {};
  for (const s of ['left', 'right']){
    const idx = [...F2.keys()].filter(t => F2[t]);
    if (!idx.length){ signs[s] = { el: [], wr: [], idx }; continue; }

    /* per-frame geometry in the signer's own frame: x lateral, y up, z FORWARD */
    const G = idx.map(t => {
      const e = F2[t][s];
      const d2El = Math.hypot(e.el.x, e.el.y), d2Wr = Math.hypot(e.wr.x, e.wr.y);
      return { el: e.el, wr: e.wr,
        dzEl: Math.sqrt(Math.max(0, CAL.upper ** 2 - Math.min(d2El, CAL.upper) ** 2)),
        dzWr: Math.sqrt(Math.max(0, CAL.fore  ** 2 - Math.min(d2Wr, CAL.fore ) ** 2)),
        pEl: -e.zEl >= 0 ? 1 : -1,                  // z's opinion on each segment
        pWr: -e.zWr >= 0 ? 1 : -1 };
    });
    const REACH = CAL.upper + CAL.fore;
    const unit = a => { const n = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0]/n, a[1]/n, a[2]/n]; };
    const dot3 = (p, q) => p[0]*q[0] + p[1]*q[1] + p[2]*q[2];
    const ang  = (p, q) => Math.acos(Math.max(-1, Math.min(1, dot3(p, q))));
    const dirs = (g, se, sw) => [ unit([g.el.x, g.el.y, se * g.dzEl]),
                                  unit([g.wr.x, g.wr.y, sw * g.dzWr]) ];

    /* the candidate's actual joint positions. Exact, not an approximation: direct aiming
     * places the elbow at shoulder + L1*u and the wrist at elbow + L2*f by construction,
     * so the collision test here sees the same pose aim() will produce. */
    const SH = SH_POS[s], L1 = LIMB[s].L1, L2 = LIMB[s].L2, LR = LIMB_R[s];
    const RC = REST_CLEAR[s];
    const toWorld = a => V(0, 0, 0)
      .addScaledVector(RIGHT, a[0]).addScaledVector(UP, a[1]).addScaledVector(FWD, a[2]);
    const joints = (u, f) => {
      const el = SH.clone().addScaledVector(toWorld(u), L1);
      return [el, el.clone().addScaledVector(toWorld(f), L2)];
    };

    const emit = (g, se, sw) => {
      const [u, f] = dirs(g, se, sw);
      let c = 0;
      const d = dot3(u, f);
      if (ang(u, f) > BEND_MIN){                    // meaningfully bent
        const perp = [f[0] - u[0]*d, f[1] - u[1]*d, f[2] - u[2]*d];
        const np = Math.hypot(perp[0], perp[1], perp[2]);
        if (np > 1e-6 && perp[2] / np < 0) c += W_BACK * (-perp[2] / np);
      }
      /* ASL is performed in front of the body: a wrist behind the shoulder plane is
       * suspect even when it clears the torso (e.g. out to the side and back). Kept as a
       * weak prior now that real collision does the heavy lifting. */
      const wristFwd = se * g.dzEl + sw * g.dzWr;
      if (wristFwd < 0) c += W_BEHIND * (-wristFwd) / REACH;

      /* real penetration, against the gate's own volumes and rest baseline */
      const [elP, wrP] = joints(u, f);
      const over = (now, restVal) => Math.max(0, Math.min(0, restVal) - now);
      const pen = over(torsoClearance(BODY, SH,  elP, LR), RC.upperTorso)
                + over(torsoClearance(BODY, elP, wrP, LR), RC.foreTorso)
                + over(headClearance (BODY, SH,  elP, LR), RC.upperHead)
                + over(headClearance (BODY, elP, wrP, LR), RC.foreHead);
      c += W_PEN * pen / CONTACT_ALLOW;             // 5 cm of penetration costs W_PEN

      if (se !== g.pEl) c += W_PRIOR;
      if (sw !== g.pWr) c += W_PRIOR;
      return c;
    };
    const trans = (g0, a, g1, b) => {
      const [u0, f0] = dirs(g0, a[0], a[1]), [u1, f1] = dirs(g1, b[0], b[1]);
      return W_SMOOTH * (ang(u0, u1) + ang(f0, f1));
    };

    const n = G.length;
    const cost = Array.from({ length: n }, () => new Float64Array(4).fill(Infinity));
    const back = Array.from({ length: n }, () => new Int8Array(4).fill(-1));
    for (let q = 0; q < 4; q++) cost[0][q] = emit(G[0], STATES[q][0], STATES[q][1]);
    for (let t = 1; t < n; t++)
      for (let q = 0; q < 4; q++){
        const e = emit(G[t], STATES[q][0], STATES[q][1]);
        for (let p = 0; p < 4; p++){
          const c = cost[t-1][p] + trans(G[t-1], STATES[p], G[t], STATES[q]) + e;
          if (c < cost[t][q]){ cost[t][q] = c; back[t][q] = p; }
        }
      }
    let q = 0;
    for (let i = 1; i < 4; i++) if (cost[n-1][i] < cost[n-1][q]) q = i;
    const el = new Array(n), wr = new Array(n);
    for (let t = n - 1; t >= 0; t--){
      el[t] = STATES[q][0]; wr[t] = STATES[q][1];
      if (back[t][q] >= 0) q = back[t][q];
    }
    /* how often anatomy had to overrule z — worth seeing, it is the error rate of z */
    report.signOverrides = (report.signOverrides || 0) +
      el.reduce((a, v, i) => a + (v !== G[i].pEl ? 1 : 0), 0) +
      wr.reduce((a, v, i) => a + (v !== G[i].pWr ? 1 : 0), 0);
    signs[s] = { el, wr, idx };
  }

  /* 5. solve */
  const samples = [];
  for (let t = 0; t < F.length; t++){
    const e = F2[t];
    if (!e){ samples.push(null); continue; }
    toRest();

    /* ---- HEAD + SPINE ----
     * Applied before the arms so the shoulder positions the arms hang from are already
     * correct for this frame. Every channel is clamped to a human range: the landmark
     * measurements are noisy at the tails and an over-rotated head is far more obviously
     * wrong than an under-rotated one. */
    if (e.body && HEAD_ON){
      const N = CAL.neutral;
      const yaw   = clampDeg((e.body.yaw   - N.yaw)   * YAW_GAIN,   YAW_MAX);
      const pitch = clampDeg((e.body.pitch - N.pitch) * PITCH_GAIN, PITCH_MAX);
      const roll  = clampDeg(THREE.MathUtils.radToDeg(e.body.roll - N.roll), ROLL_MAX);
      const lean  = clampDeg((e.body.lean  - N.lean)  * LEAN_GAIN,  LEAN_MAX);

      /* Split head rotation between neck and head the way a neck actually works: the
       * cervical spine contributes roughly a third, the atlanto-occipital joint the rest.
       * Putting it all on one bone makes the neck look broken. */
      const applyEuler = (bone, degX, degY, degZ) => {
        if (!bone) return;
        const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(
          THREE.MathUtils.degToRad(degX), THREE.MathUtils.degToRad(degY),
          THREE.MathUtils.degToRad(degZ), 'YXZ'));
        bone.quaternion.copy(rest.get(bone)).multiply(q);
      };
      applyEuler(BONE.neck, pitch * 0.35, yaw * 0.35, roll * 0.35);
      applyEuler(BONE.head, pitch * 0.65, yaw * 0.65, roll * 0.65);
      /* Lateral lean spread over the spine, most at the top — bending only at the waist
       * reads as a hinge rather than a spine. */
      applyEuler(BONE.spine,      0, 0, lean * 0.25);
      applyEuler(BONE.chest,      0, 0, lean * 0.35);
      applyEuler(BONE.upperChest, 0, 0, lean * 0.40);
      scene.updateMatrixWorld(true);
      /* the torso just moved, so the collision volumes must move with it */
      refreshBody(BODY);
    }

    for (const s of ['left', 'right']){
      const L = LIMB[s], sgn = signs[s], k = sgn.idx.indexOf(t);
      const mySign = side => k < 0 ? 1 : sgn[side][k];
      const shoulder = wp(L.upper);
      /* DIRECT AIMING, NOT IK.
       *
       * Reaching for IK here was a mistake. IK solves for an end-effector target and
       * invents the elbow via a swivel hint — but the data gives shoulder, elbow AND
       * wrist, i.e. two directions for two bones. The chain is over-determined, so
       * there is nothing to solve. Worse, the swivel is degenerate precisely when the
       * arm is raised (elbow direction nearly parallel to the shoulder->wrist axis),
       * which is how the forearm ended up 18.9 cm inside the chest on "black".
       *
       * Aiming each bone along its own measured direction removes the ambiguity
       * entirely: no hint, no swivel, no reach/proportion trade. Bone LENGTHS stay the
       * avatar's, directions come from the data. Depth per segment: magnitude from the
       * bone-length identity, sign from z. */
      /* Depth is reconstructed in the SIGNER's units against the SIGNER's calibrated limb
       * length — NOT the avatar's bone. Mixing the two was a real bug: the in-plane offset
       * carries the signer's proportions (upper arm 0.869 sh.w.) while the avatar's bone is
       * 0.625 sh.w., so d2 exceeded len on 37% of segments, dz collapsed to 0, and the arm
       * was flattened into the coronal plane — driving forearms into the torso on 82 of 250
       * words. Clamping destroyed direction AND location, so it got the worst of both.
       *
       * In signer space the result is a pure unit DIRECTION; the avatar's bone length is
       * supplied by aim(), which preserves it by construction. Clamping now fires only on
       * genuine tracking spikes above the signer's own p99 limb length. */
      const dir = (off, signerLen, sign) => {
        const d2 = Math.hypot(off.x, off.y);
        if (d2 > signerLen) report.flattened++;
        const dz = Math.sqrt(Math.max(0, signerLen ** 2 - Math.min(d2, signerLen) ** 2));
        return V(0, 0, 0)
          .addScaledVector(RIGHT, off.x)
          .addScaledVector(UP,    off.y)
          .addScaledVector(FWD,   sign * dz)
          .normalize();
      };
      /* Shoulder first: it moves the socket the arm hangs from. */
      const upDir = dir(e[s].el, CAL.upper, mySign('el'));
      const foreDir = dir(e[s].wr, CAL.fore, mySign('wr'));
      shrug(s, upDir);

      /* Direction transfer, NOT location. Tried and measured the alternative: placing the
       * wrist where the signer's wrist was and solving IK to reach it made fidelity far
       * worse (wrist lateral correlation 0.978 -> 0.263), because the targets are simply
       * out of reach. The signer measures 1.705 shoulder-widths of arm against this
       * avatar's 1.261 — 35% longer, and longer than a typical human's ~1.38, so the
       * calibration is picking up MediaPipe's medial shoulder placement as much as real
       * proportions. IK then clamps to full extension on most frames and the elbow lands
       * nowhere near where it was measured.
       *
       * The hand therefore lands ~15% short of the signer's absolute location. That is a
       * genuine limitation of this avatar's proportions, not a solver defect: no solve can
       * put the hand somewhere the arm does not reach. Signing reads smaller than the
       * source, but every angle is right and the elbow is where it was measured. */
      aim(L.upper, L.lower, upDir, scene);
      aim(L.lower, L.hand,  foreDir, scene);

      const H = e[s].hpts;

      /* ---- WRIST ORIENTATION, on every frame ----
       * The detailed 21-point block covers only 38-41% of frames. The POSE block's three
       * hand knuckles cover 99.2%, so the wrist is oriented from whichever is available,
       * preferring the detailed one. Previously the wrist was only oriented when the
       * detailed block existed, leaving it in its BIND rotation for ~60% of frames — a
       * dead hand on a live arm, which reads as more broken than a merely approximate
       * handshape does.
       *
       * Two directions fix a rotation: where the knuckles point, and which way the palm
       * faces. A single direction would leave the roll free. */
      const toW = (p, len) => {
        const inPlane = V(0, 0, 0)
          .addScaledVector(RIGHT, p.x * SHOULDER_W).addScaledVector(UP, p.y * SHOULDER_W);
        const d2 = inPlane.length();
        if (d2 > len) inPlane.multiplyScalar(len / d2);
        const dz = Math.sqrt(Math.max(0, len * len - Math.min(d2, len) ** 2));
        return inPlane.addScaledVector(FWD, (p.z <= 0 ? 1 : -1) * dz).normalize();
      };
      const palmLen = L.knuckle ? wp(L.knuckle).distanceTo(wp(L.hand)) : 0;
      if (L.knuckle && L.across.every(Boolean) && palmLen > 1e-9){
        let fingerDir = null, acrossV = null;
        if (H){                                   // detailed block: middle MCP + index/little
          fingerDir = toW(H[9], palmLen);
          acrossV = V(0, 0, 0)
            .addScaledVector(RIGHT, (H[17].x - H[5].x) * SHOULDER_W)
            .addScaledVector(UP,    (H[17].y - H[5].y) * SHOULDER_W).normalize();
        } else if (e[s].coarse){                  // pose block: wrist -> knuckles
          const c = e[s].coarse;
          const mid = { x: (c.pinky.x + c.index.x) / 2, y: (c.pinky.y + c.index.y) / 2,
                        z: (c.zPinky + c.zIndex) / 2 };
          fingerDir = toW(mid, palmLen);
          /* index minus pinky matches the detailed block's little->index convention */
          acrossV = V(0, 0, 0)
            .addScaledVector(RIGHT, (c.index.x - c.pinky.x) * SHOULDER_W)
            .addScaledVector(UP,    (c.index.y - c.pinky.y) * SHOULDER_W);
          acrossV = acrossV.lengthSq() > 1e-12 ? acrossV.normalize() : null;
          report.coarseHand[s]++;
        }
        if (fingerDir && acrossV){
          const palmDir = V(0, 0, 0).crossVectors(acrossV, fingerDir);
          if (palmDir.lengthSq() > 1e-9)
            orientHand(scene, L.hand, L.knuckle, L.across, fingerDir, palmDir.normalize());
        }
      }

      /* ---- 2s: MIRROR THE DOMINANT HANDSHAPE ONTO THE PASSIVE HAND ----
       *
       * GISLR records one hand per participant, so for a two-handed sign the passive hand
       * does not exist in ANY take — no exemplar selection can recover it. For a SYMMETRIC
       * two-handed sign that is fine: Battison's Symmetry Condition says both hands carry
       * the same handshape, so the passive hand is DETERMINED by the dominant one rather
       * than guessed. This is the one case where synthesis is exact.
       *
       * Mirroring is done on world-space bone DIRECTIONS, not on local quaternions. Local
       * rotations depend on each rig's bind-pose conventions for left vs right, which vary;
       * a direction mirrored across the sagittal plane is rig-independent. The existing
       * aim() then does the work, so this inherits the same hinge clamps and anatomy gate
       * as solved fingers.
       *
       * Only applies when the sign is 2s AND this side has no data AND the other side does. */
      if (!H && HANDCLASS === '2s' && e[other(s)].hpts && PALM[s]){
        /* Copy LOCAL joint rotations, not world directions.
         *
         * The world-direction version of this was wrong and every check passed it —
         * anatomy gate, hinge check, jitter, rig suite. aim() constrains one axis per
         * bone, but a reflection has determinant -1: the chirality lives in the roll about
         * the finger axis, which aim() leaves free. The result was a hand whose fingers
         * curled correctly and whose palm faced the wrong way. Measured on palm normals it
         * matched a true sagittal mirror in 7/80 frames on `book` and 0/80 on `bath`.
         *
         * Handshape is a WRIST-RELATIVE quantity. This rig's left and right finger bones
         * carry mirrored bind poses, so the same local rotation on both sides already
         * produces mirrored world geometry — and the passive wrist keeps its own
         * orientation, which is real data from the pose-block knuckles rather than
         * synthesized. Verified on palm-normal chirality, not assumed. */
        const src = LIMB[other(s)];
        for (const [fname, ch] of Object.entries(L.chains)){
          const sch = src.chains[fname];
          if (!sch) continue;
          for (let i = 0; i < ch.bones.length; i++){
            const b = ch.bones[i], sb = sch.bones[i];
            if (!b || !sb) break;
            b.quaternion.copy(sb.quaternion);
          }
        }
        scene.updateMatrixWorld(true);
        report.mirroredHands++;
      }

      /* ---- NO FINGER DATA: relax the hand instead of leaving it at rest ----
       *
       * 165 of 250 words have ZERO hand-block frames on the hand that signs, so their
       * fingers were staying in the rig's bind pose — straight, and splayed apart. That is
       * an anatomical reference pose, not a pose any hand actually holds. Whenever such a
       * hand turned toward the camera it read as a rigid splayed claw, and that, not
       * jitter, is what makes most of the corpus look inhuman: side by side, the clips
       * that look right are the ones where the flat hand happens to be edge-on.
       *
       * A human hand with no instruction sits in the RELAXED position: fingers softly
       * curled and close together, thumb resting alongside. It is not the correct
       * handshape for the sign — nothing can recover that from absent data — but it is a
       * pose a hand can be in, which a flat splayed paddle is not. */
      /* ---- 2a: UNMARKED HANDSHAPE AT THE BASE (contract §6.1) ----
       *
       * The passive hand of an asymmetric sign is a static base drawn from a small set of
       * unmarked handshapes, so it is predictable — but it is NOT a mirror of the dominant
       * hand, which is why this is a separate branch from 2s.
       *
       * The template is applied by AIMING phalanges, which is safe here for the reason it was
       * not safe for 2s: the wrist keeps its own orientation from the pose-block knuckles, so
       * chirality is carried by the wrist rather than by the finger directions. This is the
       * same path the real-landmark solver uses, and it inherits the same hinge clamps. */
      else if (!H && HANDCLASS === '2a' && TPL && PASSIVE_SHAPE && PALM[s]){
        const key = (TPL_RES[PASSIVE_SHAPE]?.use) || PASSIVE_SHAPE;
        const tpl = TPL[key]?.template_xyz;
        const wrB = L.hand;
        const idxB = L.chains.Index?.bones[0], midB = L.chains.Middle?.bones[0],
              pnkB = L.chains.Little?.bones[0];
        if (tpl && idxB && midB && pnkB){
          const W = wp(wrB);
          const xh = wp(idxB).clone().sub(W);
          const pk = wp(pnkB).clone().sub(W);
          const scale = wp(midB).distanceTo(W);
          if (xh.lengthSq() > 1e-12 && pk.lengthSq() > 1e-12 && scale > 1e-9){
            xh.normalize();
            const zh = V(0,0,0).crossVectors(xh, pk.normalize());
            if (zh.lengthSq() > 1e-12){
              zh.normalize();
              const yh = V(0,0,0).crossVectors(zh, xh).normalize();
              /* templates are right-hand chirality; reflect in z for the left hand */
              const zs = (s === 'left') ? -1 : 1;
              const at = i => W.clone()
                .addScaledVector(xh, tpl[i][0] * scale)
                .addScaledVector(yh, tpl[i][1] * scale)
                .addScaledVector(zh, tpl[i][2] * scale * zs);
              for (const [fname, ch] of Object.entries(L.chains)){
                const ids = ch.mp; if (!ids) continue;
                for (let i = 0; i < ch.bones.length && i < 3; i++){
                  const b = ch.bones[i], child = ch.bones[i+1] || b.children.find(c => c.isBone);
                  if (!b || !child) break;
                  const d = at(ids[i+1]).sub(at(ids[i]));
                  if (d.lengthSq() < 1e-12) break;
                  aim(b, child, d.normalize(), scene);
                }
              }
              report.templateHands++;
            }
          }
        }
      }

      else if (!H && PALM[s]){
        const inwardW = PALM[s].local.clone()
          .applyQuaternion(L.hand.getWorldQuaternion(new THREE.Quaternion()));
        for (const [fname, ch] of Object.entries(L.chains)){
          const curl = RELAX_CURL[fname] || RELAX_CURL.default;
          let parent = ch.bones[0].parent;
          for (let i = 0; i < ch.bones.length; i++){
            const b = ch.bones[i], child = ch.bones[i + 1]
              || b.children.find(c => c.isBone);
            if (!b || !child || !parent) break;
            const u = wp(b).clone().sub(wp(parent));
            if (u.lengthSq() < 1e-12) break;
            u.normalize();
            /* rotate the segment toward the palm by the relaxed angle for this joint */
            const perp = inwardW.clone().addScaledVector(u, -inwardW.dot(u));
            if (perp.lengthSq() < 1e-12) break;
            perp.normalize();
            const th = THREE.MathUtils.degToRad(curl[i]);
            const dir = u.clone().multiplyScalar(Math.cos(th))
                         .addScaledVector(perp, Math.sin(th)).normalize();
            aim(b, child, dir, scene);
            parent = b;
          }
        }
        report.relaxedHands++;
      }

      /* ---- FINGERS, only where the detailed block exists ----
       * 4 landmarks per finger give 3 bone directions and this rig has 3 bones per
       * finger, so the mapping is 1:1 with nothing to solve. */
      if (H){
        /* FINGERS. Two changes from aiming each phalanx at whatever z says:
         *
         * 1. Depth is reconstructed against the SIGNER's calibrated phalanx length, in
         *    signer units, giving a unit direction — the avatar's bone length comes from
         *    aim(). Against the avatar's bone it clamped up to 89% of thumb frames.
         * 2. The depth SIGN is chosen by the hinge, not by z. A finger's PIP and DIP flex
         *    toward the palm and do not extend past straight; the MCP hyperextends only
         *    slightly. Raw per-frame z had no such constraint and no smoothing either, so
         *    it both inverted joints and flickered between adjacent frames. z is kept as a
         *    tie-breaker for joints that are nearly straight, where the fold direction is
         *    genuinely undefined and z is the only information available. */
        const inwardW = PALM[s]
          ? PALM[s].local.clone().applyQuaternion(L.hand.getWorldQuaternion(new THREE.Quaternion()))
          : null;
        for (const f of Object.keys(L.chains)){
          const ch = L.chains[f];
          const cal = CAL.fing[f] || [];
          /* The first joint (MCP) hinges off THIS finger's own metacarpal, taken from the
           * already-oriented rig — not off a shared palm axis. Using the middle-finger
           * palm axis for every finger was wrong by a wide margin on the thumb, whose
           * metacarpal points across the palm, and the thumb was exactly where the
           * residual hyperextension concentrated. */
          const p0 = ch.bones[0].parent;
          let parentDir = p0 && p0.isBone
            ? wp(ch.bones[0]).clone().sub(wp(p0)).normalize()
            : (L.knuckle ? wp(L.knuckle).clone().sub(wp(L.hand)).normalize() : null);
          if (parentDir && parentDir.lengthSq() < 1e-12) parentDir = null;
          for (let i = 0; i < 3; i++){
            const a0 = H[ch.mp[i]], a1 = H[ch.mp[i + 1]];
            if (!a0 || !a1) continue;
            const seg = { x: a1.x - a0.x, y: a1.y - a0.y, z: a1.z - a0.z };
            const sLen = cal[i];
            let dirW;
            if (!sLen || !inwardW || !parentDir){
              dirW = toW(seg, ch.len[i]);                        // no calibration: as before
            } else {
              const d2 = Math.hypot(seg.x, seg.y);
              if (d2 > sLen) report.fingClamped++;
              const dz = Math.sqrt(Math.max(0, sLen ** 2 - Math.min(d2, sLen) ** 2));
              const zPref = seg.z <= 0 ? 1 : -1;                 // forward = -z
              const cand = [1, -1].map(sg => V(0, 0, 0)
                .addScaledVector(RIGHT, seg.x).addScaledVector(UP, seg.y)
                .addScaledVector(FWD, sg * dz).normalize());
              /* how far each candidate folds the joint the WRONG way, in degrees */
              const backness = c => {
                const d = c.dot(parentDir);
                const bend = Math.acos(Math.max(-1, Math.min(1, d)));
                if (bend < 0.05) return 0;                       // straight: undefined
                const perp = c.clone().addScaledVector(parentDir, -d);
                if (perp.lengthSq() < 1e-12) return 0;
                const along = perp.normalize().dot(inwardW);
                return along < 0 ? THREE.MathUtils.radToDeg(bend) * (-along) : 0;
              };
              /* The thumb is not a finger. It opposes, so it flexes ACROSS the palm rather
               * than toward the palm normal, and its CMC has two extra degrees of freedom.
               * Judging it against the four-finger palm axis would clamp legitimate
               * opposition, so it gets wide slack and is effectively only protected from
               * gross inversion. The four fingers get a tight limit. */
              const MCP_SLACK = f === 'Thumb' ? 45 : (i === 0 ? 20 : 5);
              const cost = cand.map((c, k) => Math.max(0, backness(c) - MCP_SLACK)
                                            + (([1, -1][k]) !== zPref ? 6 : 0));
              const pick = cost[0] <= cost[1] ? 0 : 1;
              dirW = cand[pick];
              if (cost[0] !== cost[1] && [1, -1][pick] !== zPref) report.fingSignFlips++;

              /* Choosing the better of two signs is only a preference. When BOTH signs
               * fold the joint backward — which happens when the 2D landmarks themselves
               * imply it, i.e. tracking noise on a small finger — the lesser evil still
               * hyperextends. So clamp as a hard constraint: keep the bend's AZIMUTH (the
               * lateral splay the data asked for) and reduce only its MAGNITUDE until the
               * backward component is within slack. Continuous, and it never invents a
               * curl the data did not have. */
              const over = backness(dirW);
              if (over > MCP_SLACK){
                const d = dirW.dot(parentDir);
                const perp = dirW.clone().addScaledVector(parentDir, -d);
                if (perp.lengthSq() > 1e-12){
                  perp.normalize();
                  const along = -perp.dot(inwardW);              // > 0 since we hyperextend
                  const th = THREE.MathUtils.degToRad(MCP_SLACK / Math.max(1e-6, along));
                  dirW = parentDir.clone().multiplyScalar(Math.cos(th))
                          .addScaledVector(perp, Math.sin(th)).normalize();
                  report.fingHingeClamped++;
                }
              }
            }
            aim(ch.bones[i],
                ch.bones[i + 1] || ch.bones[i].children.find(c => c.isBone) || ch.bones[i],
                dirW, scene);
            parentDir = dirW;                                    // next joint hinges off this
          }
        }
        report.handFrames[s]++;
      }
    }
    const q = new Map();
    for (const b of [BONE.neck, BONE.head, BONE.spine, BONE.chest, BONE.upperChest])
      if (b && !b.quaternion.equals(rest.get(b))) q.set(b, b.quaternion.clone());
    for (const s of ['left', 'right']){
      const L = LIMB[s];
      const touched = [BONE.shoulder[s], L.upper, L.lower, L.hand,
                       ...Object.values(L.chains).flatMap(c => c.bones)];
      for (const b of touched)
        if (b && !b.quaternion.equals(rest.get(b))) q.set(b, b.quaternion.clone());
    }
    samples.push({ t: t / fps, q });
  }

  /* 6. emit tracks.
   *
   * A DROPPED FRAME — whole-frame tracking loss, 1-2 frames in this corpus — contributes no
   * sample and the track's own slerp bridges it. That is the §6 "interpolate, never blink"
   * rule and it is right for the arms, which are 99.2% present.
   *
   * A MISSING HAND BLOCK is a different thing and must NOT be treated the same way. Hand
   * coverage is 41% with gaps up to 27 frames, so leaving finger tracks sparse made the
   * player slerp between two solved handshapes across the whole gap — sweeping the fingers
   * through orientations that were never solved and never tested against the hinge
   * constraint. That is where the residual hyperextension lived: every SOLVED frame obeyed
   * the constraint, and the frames in between were invented at playback. It is also what
   * "the fingers go abnormal during the sign" looks like.
   *
   * Handshape is phonemic on top of that — CAT and FATHER differ by it — so interpolating
   * across a gap does not recover a handshape, it fabricates one.
   *
   * So hand and finger tracks are keyed on EVERY frame and HELD across gaps: the last
   * solved pose persists, with a short blend into the next solved pose so the change reads
   * as motion rather than a glitch. Every pose the player can show is then one the solver
   * actually produced, apart from a <=BLEND-frame transition. */
  const HELD = new Set();
  for (const s of ['left', 'right']){
    const L = LIMB[s];
    if (L.hand) HELD.add(L.hand);
    for (const c of Object.values(L.chains)) for (const b of c.bones) if (b) HELD.add(b);
  }
  /* Blend length follows the SIZE of the pose change rather than being fixed.
   *
   * A fixed 2-frame blend was fine for small changes and wrong for large ones: across a
   * long data gap the held handshape and the next solved one can be 100 deg apart, and
   * slerping that in 2 frames (66 ms) both exceeds any real finger's angular velocity and
   * sweeps through hyperextended configurations on the way. Every violation left in the
   * corpus was of exactly this kind — 0 at solved keys, all of them between keys.
   *
   * Human finger joints top out around 500-800 deg/s, so ~25 deg/frame at 30 fps is a
   * generous ceiling. Requiring the blend to respect it bounds the excursion by
   * construction instead of hoping the endpoints are close. */
  const ease = u => u * u * (3 - 2 * u);           // smoothstep
  const MAX_DEG_PER_FRAME = 25;
  const BLEND_MAX = 8;
  const blendFramesFor = (qa_, qb_) => {
    const dot = Math.abs(qa_.x*qb_.x + qa_.y*qb_.y + qa_.z*qb_.z + qa_.w*qb_.w);
    const deg = THREE.MathUtils.radToDeg(2 * Math.acos(Math.min(1, dot)));
    return Math.max(1, Math.min(BLEND_MAX, Math.ceil(deg / MAX_DEG_PER_FRAME)));
  };

  const bones = [...new Set(samples.filter(Boolean).flatMap(s => [...s.q.keys()]))];
  const nameOf = b => { for (const [n, o] of byName) if (o === b) return n; return b.name; };
  const tracks = bones.map(b => {
    const times = [], values = [];
    const push = (t, q) => { times.push(round6(t));
      values.push(round6(q.x), round6(q.y), round6(q.z), round6(q.w)); };

    if (HELD.has(b)){
      /* which frames actually solved this bone */
      const solved = samples.map((s, i) => (s && s.q.has(b)) ? i : -1).filter(i => i >= 0);
      if (!solved.length) return { bone: nameOf(b), type: 'quaternion', times, values };
      const firstQ = samples[solved[0]].q.get(b);
      let last = firstQ;                                  // fills backward to frame 0 too
      const solvedSet = new Set(solved);
      for (let i = 0; i < samples.length; i++){
        const s = samples[i]; if (!s) continue;
        if (solvedSet.has(i)){ last = s.q.get(b); push(s.t, last); continue; }
        /* Inside a gap: hold, and write the transition EXPLICITLY rather than leaving a
         * hole for the player's slerp to fill. Every frame is keyed, so "between keys"
         * stops existing as a category — which matters because that is where every
         * remaining hinge violation lived. The blend values are still slerps, so they can
         * still pass through hyperextension; the clamp pass below fixes that. */
        let next = -1;
        for (const j of solved) if (j > i){ next = j; break; }
        if (next >= 0){
          const span = blendFramesFor(last, samples[next].q.get(b));
          if (next - i <= span){
            const u = 1 - (next - i) / (span + 1);
            push(s.t, last.clone().slerp(samples[next].q.get(b), ease(u)));
            continue;
          }
        }
        push(s.t, last);
      }
    } else {
      for (const s of samples){
        if (!s || !s.q.has(b)) continue;
        push(s.t, s.q.get(b));
      }
    }
    return { bone: nameOf(b), type: 'quaternion', times, values };
  }).filter(t => t.times.length).sort((a, b) => a.bone.localeCompare(b.bone));

  /* ---- hinge clamp over the FINISHED tracks ----
   *
   * The solver constrains every frame it solves, and measurement confirmed it: 0 violations
   * at solved keys. Every remaining one was at a blend frame, because a slerp between two
   * valid finger poses can pass through hyperextension — and subdividing it does not help,
   * since the PATH is wrong rather than the speed. (Making the blend adaptive on pose
   * distance made it worse: same bad path, more frames spent on it.)
   *
   * So the clip itself is validated, not just the solve. This poses the rig at every frame
   * of the emitted tracks and clamps any finger joint folding backward past its limit,
   * writing the corrected quaternion back. What the player shows is then what was checked. */
  {
    const fingerBones = [];
    for (const s of ['left', 'right'])
      for (const c of Object.values(LIMB[s].chains))
        c.bones.forEach((b, i) => { if (b) fingerBones.push({ b, s, i }); });
    /* Resolve bone<->track ONCE. Doing this lookup inside the frame loop made the pass
     * O(frames x tracks x bones) and cost 7.8 s per clip. */
    const trackOf = new Map(), pairs = [];
    for (const tr of tracks){
      const bone = byName.get(tr.bone) || [...byName.values()].find(o => o.name === tr.bone);
      if (bone){ trackOf.set(bone, tr); pairs.push([bone, tr]); }
    }
    /* A hand with no finger tracks stays in its rest pose for the whole clip, which is
     * valid by definition, so it does not need checking at every frame. */
    const drivenHand = {};
    for (const s of ['left', 'right'])
      drivenHand[s] = Object.values(LIMB[s].chains)
        .some(c => c.bones.some(b => b && trackOf.has(b)));
    const times = tracks.length ? tracks[0].times : [];
    const qtmp = new THREE.Quaternion();
    let clamped = 0;

    for (let k = 0; k < times.length; k++){
      /* pose from the tracks exactly as the player would */
      for (const [b, q] of rest) b.quaternion.copy(q);
      for (const [bone, tr] of pairs){
        let i = 0; while (i < tr.times.length - 1 && tr.times[i + 1] <= times[k]) i++;
        bone.quaternion.set(tr.values[i*4], tr.values[i*4+1], tr.values[i*4+2], tr.values[i*4+3]);
      }
      scene.updateMatrixWorld(true);

      for (const s of ['left', 'right']){
        if (!PALM[s] || !drivenHand[s]) continue;   // no finger tracks -> at rest -> valid
        const inwardW = PALM[s].local.clone()
          .applyQuaternion(LIMB[s].hand.getWorldQuaternion(new THREE.Quaternion()));
        for (const [fname, ch] of Object.entries(LIMB[s].chains)){
          const slack = fname === 'Thumb' ? 45 : 20;         // j1; deeper joints below
          for (let i = 0; i < ch.bones.length - 1; i++){
            const b = ch.bones[i], child = ch.bones[i + 1];
            if (!b || !child) continue;
            const parent = i === 0 ? b.parent : ch.bones[i - 1];
            if (!parent) continue;
            const u = wp(b).clone().sub(wp(parent));
            if (u.lengthSq() < 1e-12) continue;
            u.normalize();
            const f = wp(child).clone().sub(wp(b));
            if (f.lengthSq() < 1e-12) continue;
            f.normalize();
            const d = u.dot(f);
            const bend = Math.acos(Math.max(-1, Math.min(1, d)));
            if (bend < 0.05) continue;
            const perp = f.clone().addScaledVector(u, -d);
            if (perp.lengthSq() < 1e-12) continue;
            perp.normalize();
            const along = -perp.dot(inwardW);
            const lim = fname === 'Thumb' ? 45 : (i === 0 ? slack : 5);
            const back = along > 0 ? THREE.MathUtils.radToDeg(bend) * along : 0;
            if (back <= lim) continue;
            /* same construction the solver uses: keep the azimuth, cut the magnitude */
            const th = THREE.MathUtils.degToRad(lim / Math.max(1e-6, along));
            const want = u.clone().multiplyScalar(Math.cos(th))
                          .addScaledVector(perp, Math.sin(th)).normalize();
            /* update only this finger's subtree, not the whole scene: aim() refreshing
             * every bone in the rig for each corrected joint dominated the runtime */
            aim(b, child, want, null);
            b.updateMatrixWorld(true);
            const tr = trackOf.get(b);
            if (tr){
              let ki = 0; while (ki < tr.times.length - 1 && tr.times[ki + 1] <= times[k]) ki++;
              qtmp.copy(b.quaternion);
              tr.values[ki*4] = round6(qtmp.x); tr.values[ki*4+1] = round6(qtmp.y);
              tr.values[ki*4+2] = round6(qtmp.z); tr.values[ki*4+3] = round6(qtmp.w);
            }
            clamped++;
          }
        }
      }
    }
    report.clipHingeClamped = clamped;
  }

  /* ---- rest lead-in and lead-out ----
   * Every clip in the handoff is time-normalised to 64 frames and begins and ends MID
   * MOTION — there is no neutral pose at either end (§5). Played from bind pose the avatar
   * therefore snaps into the sign and snaps back out, which is the least natural thing in
   * the whole result and makes clips impossible to play in sequence.
   *
   * So each track is bracketed with a rest key: hold rest briefly, ease into frame 0, and
   * mirror it at the end. The sign's own timing is untouched — the lead is prepended, not
   * blended into the sign — so nothing phonemic is altered. The hold before the ease keeps
   * the start readable rather than launching from the first frame.
   *
   * Eased with a smoothstep rather than linearly: constant angular velocity from a dead
   * stop reads as mechanical, and the arm has to accelerate out of rest like a limb. */
  const restQuatOf = b => idleQuat(b);   // relax into the idle, not the T-pose
  /* lead scaled to THIS clip's length, not a constant tuned against 2.13 s */
  const signDur = tracks.length && tracks[0].times.length
    ? tracks[0].times[tracks[0].times.length - 1] : 0;
  const LEAD_IN = leadFor(signDur), LEAD_OUT = leadFor(signDur);
  if (LEAD_IN > 0 || LEAD_OUT > 0){
    const dt = 1 / fps;
    for (const tr of tracks){
      const b = byName.get(tr.bone) || [...byName.values()].find(o => o.name === tr.bone);
      const rq = b ? restQuatOf(b) : null;
      if (!rq || !tr.times.length) continue;
      const T = tr.times.slice(), Vv = tr.values.slice();
      const firstQ = new THREE.Quaternion(Vv[0], Vv[1], Vv[2], Vv[3]);
      const n = T.length;
      const lastQ = new THREE.Quaternion(Vv[(n-1)*4], Vv[(n-1)*4+1], Vv[(n-1)*4+2], Vv[(n-1)*4+3]);
      /* lead-in occupies [-LEAD_IN, 0); the sign's own first key stays exactly at 0 */
      const pre = [], preV = [];
      const steps = Math.max(1, Math.round(LEAD_IN * fps));
      for (let i = 0; i < steps; i++){
        const q = rq.clone().slerp(firstQ, ease(i / steps));
        pre.push(round6(-LEAD_IN + (i * LEAD_IN) / steps));
        preV.push(round6(q.x), round6(q.y), round6(q.z), round6(q.w));
      }
      /* lead-out occupies (end, end+LEAD_OUT] */
      const post = [], postV = [];
      const osteps = Math.max(1, Math.round(LEAD_OUT * fps));
      const end = T[n - 1];
      for (let i = 1; i <= osteps; i++){
        const q = lastQ.clone().slerp(rq, ease(i / osteps));
        post.push(round6(end + (i * LEAD_OUT) / osteps));
        postV.push(round6(q.x), round6(q.y), round6(q.z), round6(q.w));
      }
      tr.times = [...pre, ...T, ...post];
      tr.values = [...preV, ...Vv, ...postV];
    }
    /* shift everything so the clip still starts at t=0 */
    for (const tr of tracks) tr.times = tr.times.map(t => round6(t + LEAD_IN));
  }

  const allBones = []; scene.traverse(o => { if (o.isBone) allBones.push(o); });
  const namesJoined = allBones.map(nameOf).sort().join('|');
  let h = 2166136261;
  for (let i = 0; i < namesJoined.length; i++){ h ^= namesJoined.charCodeAt(i); h = Math.imul(h, 16777619); }

  const lastKey = tracks.reduce((m, t) => Math.max(m, t.times[t.times.length - 1] ?? 0), 0);
  report.shrugFrames = SHRUG_N.n;
  return { report, doc: {
    format: 'deafference.clip/1',
    name,
    source: path.basename(modelPath),
    rig: 'humanoid',
    authoredBy: 'retarget.mjs (landmarks -> IK -> quaternions; z sign-only)',
    landmarkSource: { schema: doc.schema, glosses: doc.glosses, frames: F.length,
                      droppedFrames: report.dropped,
                      handFramesLeft: report.hands.left, handFramesRight: report.hands.right },
    skeleton: { joints: allBones.length, naming: 'normalized', profile: 'humanoid',
                signature: 'r' + (h >>> 0).toString(16) },
    /* Duration comes from the EMITTED TRACKS, not from the frame count. Frame count
     * overstates it two ways: N frames span N-1 intervals, and several clips end with
     * dropped (null) landmark frames — `down` loses its last 21 — so the real motion stops
     * early. Asserting 2.13 s for a clip whose last key is at 1.65 s leaves the player
     * scrubbing through dead time and holding the final pose before looping. */
    fps, duration: round6(lastKey), interpolation: 'slerp',
    signStart: round6(LEAD_IN), signEnd: round6(Math.max(LEAD_IN, lastKey - LEAD_OUT)),
    hierarchyFixed: [], keyframeTimes: tracks[0]?.times ?? [],
    tracks, expressionTracks: [],
    boneNameMap: Object.fromEntries(tracks.map(t => [t.bone, t.bone])),
  } };
}

import { readdirSync } from 'node:fs';
const wordsDir = path.dirname(wordPaths[0]);
const corpus = readdirSync(wordsDir).filter(f => f.endsWith('.json')).map(f => path.join(wordsDir, f));
const CAL = calibrate(corpus);
console.log(`calibration over ${corpus.length} words / ${CAL.n} samples: signer upper arm ` +
  `${CAL.upper.toFixed(3)} sh.w., forearm ${CAL.fore.toFixed(3)} sh.w.`);
/* No per-limb scale factor is applied, and that is deliberate. CAL is used as the
 * denominator of the depth reconstruction (see dir()), which makes the solve
 * scale-free: proportions cancel and only the direction transfers. A scale factor
 * would re-introduce the signer's proportions that the direction solve removes. */
console.log(`  avatar upper arm ${(LIMB.right.L1 / SHOULDER_W).toFixed(3)} sh.w. — ` +
  `proportions differ by x${(CAL.upper / (LIMB.right.L1 / SHOULDER_W)).toFixed(2)}, ` +
  `absorbed by solving for direction in signer space`);

for (const wp_ of wordPathsClean){
  const doc = JSON.parse(readFileSync(wp_, 'utf8'));
  const name = path.basename(wp_).replace(/\.json$/, '');
  const { report, doc: out } = retarget(doc, name);
  const file = path.join(OUT_DIR, `RETARGET_${name}.clip.json`);
  writeFileSync(file, JSON.stringify(out, null, 1));
  console.log(`\n${name}: ${report.frames} frames, ${out.tracks.length} tracks -> ${file}`);
  console.log(`   dropped (null) frames: ${report.dropped}` +
              `   segments clamped (2D projection exceeded signer p99 limb length): ` +
              `${report.flattened}/${report.frames*4}`);
  console.log(`   hand data present: left ${report.hands.left}/${report.frames}` +
              `  right ${report.hands.right}/${report.frames}` +
              (report.hands.left + report.hands.right === 0
                ? '   <-- NO HAND DATA: arms only, handshape is lost' : ''));
  const fingJoints = (report.hands.left + report.hands.right) * 15;
  const ch = report.coarseHand.left + report.coarseHand.right;
  if (report.shrugFrames) console.log(`   shoulder girdle driven on ${report.shrugFrames} frame-sides (scapulohumeral rhythm)`);
  if (ch) console.log(`   wrist oriented from pose-block knuckles on ${ch} frame-sides (no detailed hand block)`);
  if (report.mirroredHands)
    console.log(`   passive hand MIRRORED from the dominant on ${report.mirroredHands} frame-sides (class 2s)`);
  if (report.templateHands)
    console.log(`   passive hand set to an unmarked TEMPLATE on ${report.templateHands} frame-sides (class 2a)`);
  if (report.relaxedHands)
    console.log(`   passive hand relaxed on ${report.relaxedHands} frame-sides (class ${report.handClass})`);
  if (fingJoints)
    console.log(`   phalanges: ${report.fingClamped}/${fingJoints} clamped, ` +
                `${report.fingSignFlips} depth signs overruled, ${report.fingHingeClamped} hinge-clamped`);
}
