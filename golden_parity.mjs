// golden_parity.mjs — MODEL_CONTRACT.md task #26, the frontend half.
//
// Run:  node golden_parity.mjs [path/to/golden_fixtures.json]
//
// Replace `normalize` below with an IMPORT of the real frontend implementation. Editing this
// copy until it passes proves nothing — the point is to test the code that ships.
//
// NaN arrives as `null`, because JSON cannot carry NaN and a bare NaN token is invalid JSON.
import { readFileSync } from 'node:fs';

const FIX = process.argv[2] ?? 'golden_fixtures.json';
const doc = JSON.parse(readFileSync(FIX, 'utf8'));
const L = doc.layout, TOL = doc.tolerances.normalize;

const dec = (m) => m.map((r) => r.map((v) => (v === null ? NaN : v)));

// ── THE IMPLEMENTATION UNDER TEST — swap this for your real one ──────────────────────────
// Contract §3: centre every landmark on the shoulder MIDPOINT, scale by shoulder WIDTH,
// x and y only. Return null when either shoulder is missing or the width is ~0 — the frame
// is then DROPPED by the caller, never passed through unnormalized.
function normalize(frame) {
  const [lx, ly] = frame[L.l_shoulder];
  const [rx, ry] = frame[L.r_shoulder];
  if ([lx, ly, rx, ry].some(Number.isNaN)) return null;
  const mx = (lx + rx) / 2, my = (ly + ry) / 2;
  const w = Math.hypot(lx - rx, ly - ry);
  if (w < 1e-6) return null;
  return frame.map(([x, y, z]) => [(x - mx) / w, (y - my) / w, z]);
}
// ─────────────────────────────────────────────────────────────────────────────────────────

let ok = true;
const say = (good, name, detail = '') => {
  if (!good) ok = false;
  console.log(`  ${good ? 'ok  ' : 'FAIL'} ${name.padEnd(44)} ${detail}`);
};

for (const c of doc.stage1_and_2_normalize) {
  const got = normalize(dec(c.input));
  if (c.dropped) {
    say(got === null, c.name, got === null ? 'dropped' : 'NOT dropped — returned an array');
    continue;
  }
  if (got === null) { say(false, c.name, 'dropped, but a normalized frame is expected'); continue; }
  const want = dec(c.expected);
  let worst = 0, nanMismatch = 0;
  for (let i = 0; i < want.length; i++)
    for (let j = 0; j < want[i].length; j++) {
      const a = got[i][j], b = want[i][j];
      if (Number.isNaN(a) !== Number.isNaN(b)) { nanMismatch++; continue; }
      if (!Number.isNaN(b)) worst = Math.max(worst, Math.abs(a - b));
    }
  say(worst <= TOL && nanMismatch === 0, c.name,
      `max|d| ${worst.toExponential(2)}${nanMismatch ? `, ${nanMismatch} NaN mismatches` : ''}`);
}

// The invariants, asserted on our OWN output — these need no fixture at all.
const probe = dec(doc.stage1_and_2_normalize[0].input);
const n = normalize(probe);
if (n) {
  const [ax, ay] = n[L.l_shoulder], [bx, by] = n[L.r_shoulder];
  say(Math.abs((ax + bx) / 2) < TOL && Math.abs((ay + by) / 2) < TOL,
      'shoulder midpoint is the origin');
  say(Math.abs(Math.hypot(ax - bx, ay - by) - 1) < TOL, 'shoulder distance is exactly 1');
  const twice = normalize(n);
  let idem = 0;
  for (let i = 0; i < n.length; i++)
    for (let j = 0; j < 3; j++)
      if (!Number.isNaN(n[i][j])) idem = Math.max(idem, Math.abs(n[i][j] - twice[i][j]));
  say(idem < TOL, 'normalize is idempotent', `max|d| ${idem.toExponential(2)}`);
}

console.log('\n' + (ok ? 'PARITY OK' : 'PARITY FAILED — the browser would predict differently'));
process.exit(ok ? 0 : 1);
