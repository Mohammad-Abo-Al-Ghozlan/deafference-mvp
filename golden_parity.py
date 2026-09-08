#!/usr/bin/env python
"""Golden fixtures: prove a TF.js implementation matches this pipeline BEFORE it ships.

WHY THIS EXISTS
---------------
`docs/MODEL_CONTRACT.md` §3 ends with: *"Task #26 (verify live == training normalization) is
the checkpoint — test by feeding a known recorded clip through both and confirming identical
arrays. **Do not skip #26.**"* This file is #26's instrument. Until it passes, no browser
inference number can be trusted.

The failure it exists to prevent is not a crash. A normalization mismatch feeds the model
out-of-distribution input, and the model answers anyway — **no exception, no warning, just
quietly wrong predictions.** A frontend that centres on the nose instead of the shoulder
midpoint, or scales by image width instead of shoulder width, or substitutes 0 for a missing
landmark, produces a demo that "works" and is wrong. Every one of those is a plausible reading
of a prose spec, which is why the spec is not enough.

THE ONE DESIGN RULE: STAGES ARE SEPARATE, AND SO ARE THEIR TOLERANCES
--------------------------------------------------------------------
Normalization is pure arithmetic and must agree to ~1e-6. Model inference runs different
kernels in TF.js and cannot be held that tight. If both are checked under one loose tolerance,
a real normalization bug hides inside "well, the model is only approximate" — so they are
checked separately and a failure says which stage broke.

  stage 1  normalize      atol 1e-6     pure arithmetic, no excuse for drift
  stage 2  NaN semantics  exact         structural: dropped / preserved / padding
  stage 3  model logits   atol 2e-3     different kernels — plus argmax MUST agree

Stage 3 also asserts on the *decision*, not only the numbers: the argmax has to match and the
softmax confidence has to land within 5e-3. Logits agreeing while the prediction flips would
be a passing test of nothing.

FIXTURES ARE HAND-BUILT, NOT SAMPLED
------------------------------------
Every stage-1 and stage-2 case has an expected answer derivable by hand, so a fixture cannot
"pass" by agreeing with a bug that generated it. Random clips are added only on top of that,
to catch what hand-built cases miss.

NaN CROSSES THE WIRE AS `null`
------------------------------
JSON has no NaN. Python's json emits a bare `NaN` token with allow_nan=True, which is invalid
JSON and `JSON.parse` rejects outright. So NaN is encoded as `null` and decoded back on both
sides. This matters because NaN is not incidental here — it is the contract's value for "not
detected", and the bug that once shipped 19,002 hand blocks as `[0,0,0]` was exactly a NaN
that got turned into a zero in transit.

USAGE
    python golden_parity.py --emit                 # write golden_fixtures.json
    python golden_parity.py --check                # verify THIS repo still matches them
    python golden_parity.py --emit --with-model     # add stage 3 (needs the SavedModel)
    python golden_parity.py --emit-js              # write golden_parity.mjs for the frontend
    python golden_parity.py --selftest             # prove the harness itself is sound
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "golden_fixtures.json"
JS_CHECKER = HERE / "golden_parity.mjs"

# Reuse the SHIPPING implementation. Reimplementing the spec here would test this file against
# itself and pass while the demo is wrong — the mistake verify_fingerspelling_parity.py
# deliberately avoids by calling our own functions too.
sys.path.insert(0, str(HERE))
import live_demo as LD  # noqa: E402

ATOL_NORM = 1e-6      # stage 1: float32-vs-float64 arithmetic on values of order 1
ATOL_LOGIT = 2e-3     # stage 3: TF.js kernels differ from TF Python
ATOL_CONF = 5e-3      # stage 3: the decision, which is what actually ships


# ── NaN <-> null, both directions, because JSON cannot carry NaN ──────────────────────────
def enc(a: np.ndarray) -> list:
    """float array -> nested lists with NaN as None (JSON `null`)."""
    return json.loads(json.dumps(np.where(np.isnan(a), None, a).tolist()))


def dec(x) -> np.ndarray:
    """nested lists with None -> float32 array with NaN."""
    return np.array([[np.nan if v is None else v for v in row] for row in x], np.float32)


def _frame(shoulders=(0.4, 0.5, 0.6, 0.5), fill=0.25) -> np.ndarray:
    """A (75,3) frame with both shoulders placed exactly where we say.

    shoulders = (lx, ly, rx, ry). Every other point is `fill`, so the effect of centring and
    scaling is arithmetic anyone can check on paper.
    """
    f = np.full((LD.N_POINTS, 3), fill, np.float32)
    f[LD.L_SHOULDER, :2] = shoulders[0], shoulders[1]
    f[LD.R_SHOULDER, :2] = shoulders[2], shoulders[3]
    return f


# ── the fixtures ──────────────────────────────────────────────────────────────────────────
def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(name, frame, why, expect_dropped=False):
        out = LD.normalize(frame)
        if expect_dropped and out is not None:
            sys.exit(f"[bug] fixture '{name}' expected the frame to be DROPPED but "
                     f"normalize() returned an array. The implementation changed; fix the "
                     f"code or the fixture deliberately, never silently.")
        if not expect_dropped and out is None:
            sys.exit(f"[bug] fixture '{name}' expected a normalized frame but normalize() "
                     f"dropped it.")
        cases.append({"name": name, "why": why, "input": enc(frame),
                      "dropped": out is None,
                      "expected": None if out is None else enc(out)})

    # 1. the arithmetic, checkable by hand. Shoulders at x=0.4 and x=0.6, same y:
    #    mid = (0.5, 0.5), width = 0.2. A point at (0.25,0.25) -> ((0.25-0.5)/0.2) = -1.25.
    add("centre_and_scale", _frame(),
        "shoulders (0.4,0.5)-(0.6,0.5) => mid (0.5,0.5), width 0.2; fill 0.25 -> -1.25 on x "
        "and y. Shoulders themselves land at -0.5 and +0.5, width 1 by construction.")

    # 2. asymmetric + non-unit width, so a hard-coded 0.2 or a mid-point typo cannot pass
    add("centre_and_scale_asymmetric", _frame((0.30, 0.42, 0.70, 0.58), fill=0.10),
        "mid (0.5,0.5), width = hypot(0.4,0.16) — a diagonal shoulder line, which catches an "
        "implementation that takes |dx| instead of the Euclidean distance.")

    # 3. THE SEMANTIC A JS PORT WILL MOST LIKELY GET WRONG: an unnormalizable frame is DROPPED
    f = _frame(); f[LD.L_SHOULDER, :2] = np.nan
    add("left_shoulder_nan_DROPS_the_frame", f,
        "Either shoulder missing => the frame cannot be placed in the training coordinate "
        "space at all, so live_demo.normalize returns None and the caller DROPS it. Keeping "
        "it and passing raw 0-1 pixel coords instead is silent out-of-distribution input.",
        expect_dropped=True)

    f = _frame(); f[LD.R_SHOULDER, :2] = np.nan
    add("right_shoulder_nan_DROPS_the_frame", f, "the mirror case, so neither side is special.",
        expect_dropped=True)

    # 4. degenerate width: dividing by ~0 would produce inf, not an error
    add("zero_shoulder_width_DROPS_the_frame", _frame((0.5, 0.5, 0.5, 0.5)),
        "width < 1e-6 => division would yield inf and the model would eat it. Dropped.",
        expect_dropped=True)

    # 5. NaN must SURVIVE normalization. This is the [0,0,0] bug, restated as a test.
    f = _frame()
    f[33:54, :] = np.nan                       # the whole left-hand block, per contract §2
    add("nan_hand_is_PRESERVED_not_zeroed", f,
        "An absent hand stays NaN. Substituting 0 places it at the shoulder midpoint — a "
        "real, plausible position — which is how 19,002 hand blocks once shipped as [0,0,0]. "
        "The model builds its own detection mask from NaN and then zeroes it internally.")

    # 6. z is carried, never transformed
    f = _frame()
    f[:, 2] = np.linspace(-1, 1, LD.N_POINTS, dtype=np.float32)
    add("z_channel_passes_through_untouched", f,
        "Normalization touches x,y only; the model drops z internally via "
        "PreprocessLayer(keep_z=False). A JS port that scales z too still 'works' and is "
        "silently off-contract.")

    # 7. random frames, on top of the hand-built ones rather than instead of them
    rng = np.random.default_rng(20260908)
    for i in range(3):
        f = rng.uniform(-0.5, 1.5, (LD.N_POINTS, 3)).astype(np.float32)
        f[LD.L_SHOULDER, :2] = rng.uniform(0.2, 0.45, 2)
        f[LD.R_SHOULDER, :2] = rng.uniform(0.55, 0.8, 2)
        if i == 2:                              # one with scattered dropouts
            m = rng.random((LD.N_POINTS,)) < 0.3
            m[[LD.L_SHOULDER, LD.R_SHOULDER, 0]] = False
            f[m] = np.nan
        add(f"random_{i}", f, "unstructured input — catches what the hand-built cases miss.")

    return cases


def build_properties() -> list[dict]:
    """Invariants stated as their own checks, because a JS port can match every fixture
    above and still violate them on inputs no fixture happens to contain."""
    props = []

    # idempotence. After one pass the shoulders sit at +-0.5 with width exactly 1, so a second
    # pass subtracts 0 and divides by 1. Worth pinning: it means a double-normalize is HARMLESS,
    # which is the difference between a frontend bug and a frontend disaster.
    once = LD.normalize(_frame((0.31, 0.44, 0.69, 0.57), fill=0.12))
    twice = LD.normalize(once)
    props.append({
        "name": "normalize_is_idempotent",
        "why": "normalize(normalize(f)) == normalize(f). After one pass width is 1 and mid is "
               "the origin, so the second is a no-op. A frontend that normalizes twice is "
               "therefore still correct — do not 'fix' that by removing a needed call.",
        "input": enc(once), "expected": enc(twice), "holds": bool(
            np.allclose(once, twice, atol=ATOL_NORM, equal_nan=True)),
    })

    # the normalized shoulder geometry is fully determined, whatever the input
    n = LD.normalize(_frame((0.1, 0.9, 0.8, 0.2), fill=0.5))
    ls, rs = n[LD.L_SHOULDER, :2], n[LD.R_SHOULDER, :2]
    props.append({
        "name": "normalized_shoulders_are_unit_apart_around_the_origin",
        "why": "Whatever the input, after normalization the shoulder midpoint is (0,0) and the "
               "shoulder distance is 1. Two numbers a JS port can assert on its own output "
               "without any fixture at all.",
        "midpoint": enc(((ls + rs) / 2).reshape(1, 2))[0],
        "distance": float(np.linalg.norm(ls - rs)),
        "holds": bool(np.allclose((ls + rs) / 2, 0, atol=ATOL_NORM)
                      and abs(np.linalg.norm(ls - rs) - 1) < ATOL_NORM),
    })
    return props


def build_model_stage(n_frames: int) -> dict | None:
    """Stage 3: a full window through the real SavedModel. Optional — needs the artifacts."""
    try:
        words = LD.load_vocab()
        _, fns = LD.load_models(LD.SINGLE_MODELS)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[skip] stage 3: could not load the model ({type(e).__name__}: {e})")
        return None

    rng = np.random.default_rng(7)
    win = rng.uniform(-2, 2, (1, n_frames, LD.N_POINTS, LD.N_RAW_CH)).astype(np.float32)
    probs = LD.predict(fns, win)
    probs = np.asarray(probs, np.float64)
    idx = int(np.argmax(probs))
    return {
        "why": "One fixed window through savedmodel_fold0. TF.js kernels differ from TF "
               "Python, so logits are compared at atol 2e-3 — but the ARGMAX must match "
               "exactly and the confidence within 5e-3. Numbers agreeing while the "
               "prediction flips would be a passing test of nothing.",
        "input_shape": list(win.shape),
        "input": enc(win.reshape(-1, LD.N_RAW_CH)),   # flattened; JS reshapes with input_shape
        "probs": probs.tolist(),
        "argmax": idx,
        "argmax_word": words[idx] if idx < len(words) else None,
        "confidence": float(probs[idx]),
        "n_classes": len(probs),
        "atol_logit": ATOL_LOGIT, "atol_conf": ATOL_CONF,
    }


# ── emit / check ──────────────────────────────────────────────────────────────────────────
def emit(with_model: bool) -> int:
    doc = {
        "schema": "deafference/golden-parity/v1",
        "purpose": "MODEL_CONTRACT.md task #26 — prove a TF.js port matches this pipeline.",
        "generated_by": "golden_parity.py",
        "nan_encoding": "null (JSON has no NaN; a bare NaN token is invalid JSON)",
        "layout": {"n_points": LD.N_POINTS, "n_channels": LD.N_RAW_CH,
                   "window": LD.MAX_LEN,
                   "pose": [0, 32], "left_hand": [33, 53], "right_hand": [54, 74],
                   "l_shoulder": LD.L_SHOULDER, "r_shoulder": LD.R_SHOULDER},
        "tolerances": {"normalize": ATOL_NORM, "logit": ATOL_LOGIT, "confidence": ATOL_CONF},
        "stage1_and_2_normalize": build_cases(),
        "properties": build_properties(),
    }
    if with_model:
        m = build_model_stage(LD.MAX_LEN)
        if m:
            doc["stage3_model"] = m

    FIXTURES.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    n_drop = sum(c["dropped"] for c in doc["stage1_and_2_normalize"])
    print(f"[ok] {FIXTURES}")
    print(f"     {len(doc['stage1_and_2_normalize'])} normalize cases "
          f"({n_drop} of them must be DROPPED), {len(doc['properties'])} properties, "
          f"stage 3 {'included' if 'stage3_model' in doc else 'omitted'}")
    print(f"     {FIXTURES.stat().st_size/1e3:.0f} KB")
    return 0


def check() -> int:
    """Re-run the committed fixtures against the CURRENT implementation.

    This is the regression direction: it catches a change to live_demo.normalize that nobody
    meant to make. The JS direction is golden_parity.mjs.
    """
    if not FIXTURES.exists():
        sys.exit(f"[err] {FIXTURES} not found — run --emit first.")
    doc = json.loads(FIXTURES.read_text(encoding="utf-8"))
    ok = True

    for c in doc["stage1_and_2_normalize"]:
        got = LD.normalize(dec(c["input"]))
        if c["dropped"]:
            good = got is None
            detail = "dropped" if good else "NOT dropped — returned an array"
        elif got is None:
            good, detail = False, "dropped, but the fixture expects a normalized frame"
        else:
            want = dec(c["expected"])
            good = np.allclose(got, want, atol=ATOL_NORM, equal_nan=True)
            if good:
                detail = f"max|d| {np.nanmax(np.abs(got - want)):.2e}"
            else:
                detail = (f"max|d| {np.nanmax(np.abs(got - want)):.2e} > {ATOL_NORM:g}; "
                          f"NaN pattern {'matches' if np.array_equal(np.isnan(got), np.isnan(want)) else 'DIFFERS'}")
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'} {c['name']:44} {detail}")

    for p in doc["properties"]:
        print(f"  {'ok  ' if p['holds'] else 'FAIL'} {p['name']:44} (recorded as holding)")
        ok &= bool(p["holds"])

    if "stage3_model" in doc:
        m = doc["stage3_model"]
        try:
            _, fns = LD.load_models(LD.SINGLE_MODELS)
            win = dec(m["input"]).reshape(m["input_shape"])
            probs = np.asarray(LD.predict(fns, win), np.float64)
            same_arg = int(np.argmax(probs)) == m["argmax"]
            dconf = abs(float(probs[m["argmax"]]) - m["confidence"])
            dmax = float(np.max(np.abs(probs - np.array(m["probs"]))))
            good = same_arg and dconf <= ATOL_CONF and dmax <= ATOL_LOGIT
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} {'stage3_model':44} "
                  f"argmax {'==' if same_arg else '!='} {m['argmax']}, "
                  f"dconf {dconf:.2e}, max|dprob| {dmax:.2e}")
        except Exception as e:
            print(f"  skip  stage3_model — model not loadable here ({type(e).__name__})")

    print("\n" + ("ALL FIXTURES MATCH" if ok else "MISMATCH — see above"))
    return 0 if ok else 1


def selftest() -> int:
    """Prove the harness can FAIL. A parity test that cannot fail is decoration."""
    print("=== SELFTEST — the harness must detect a broken implementation ===")
    ok = True

    def check_(cond, label):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")

    # NaN must survive the JSON round trip, or every dropout fixture is meaningless
    a = np.array([[1.0, np.nan, -2.5], [np.nan, np.nan, 0.0]], np.float32)
    check_(np.array_equal(np.isnan(dec(enc(a))), np.isnan(a))
           and np.allclose(dec(enc(a))[~np.isnan(a)], a[~np.isnan(a)]),
           "NaN survives the enc/dec round trip as null")
    check_("NaN" not in json.dumps(enc(a)), "the emitted JSON contains no bare NaN token")
    check_(json.loads(json.dumps(enc(a))) == enc(a), "the encoding is strict, parseable JSON")

    # the three sentinel behaviours, asserted against the real function
    check_(LD.normalize(_frame()) is not None, "a well-formed frame normalizes")
    f = _frame(); f[LD.L_SHOULDER, :2] = np.nan
    check_(LD.normalize(f) is None, "a missing shoulder DROPS the frame")
    check_(LD.normalize(_frame((0.5, 0.5, 0.5, 0.5))) is None, "zero shoulder width DROPS it")

    f = _frame(); f[33:54] = np.nan
    n = LD.normalize(f)
    check_(np.isnan(n[33:54]).all(), "an absent hand is still NaN after normalization")
    check_(not np.isnan(n[LD.L_SHOULDER, :2]).any(), "present points are still present")

    z = np.linspace(-1, 1, LD.N_POINTS, dtype=np.float32)
    f = _frame(); f[:, 2] = z
    check_(np.allclose(LD.normalize(f)[:, 2], z), "z is untouched")

    # the hand-computed answer, so the fixture cannot agree with a bug
    n = LD.normalize(_frame())
    check_(abs(n[1, 0] - (-1.25)) < 1e-6 and abs(n[1, 1] - (-1.25)) < 1e-6,
           "fill 0.25 with mid 0.5 / width 0.2 lands at -1.25, computed by hand")
    check_(abs(np.linalg.norm(n[LD.L_SHOULDER, :2] - n[LD.R_SHOULDER, :2]) - 1) < 1e-6,
           "normalized shoulders are exactly 1 apart")

    # AND THE POINT OF ALL OF IT: a wrong implementation must be caught
    def nose_centred(frame):
        out = frame.copy()
        out[:, :2] -= frame[0, :2]         # the plausible misreading: centre on the nose
        return out

    good = LD.normalize(_frame())
    bad = nose_centred(_frame())
    check_(not np.allclose(good, bad, atol=ATOL_NORM),
           "a NOSE-centred implementation is REJECTED at atol 1e-6")

    def unscaled(frame):
        out = frame.copy()
        ls, rs = frame[LD.L_SHOULDER, :2], frame[LD.R_SHOULDER, :2]
        out[:, :2] -= (ls + rs) / 2        # centred but never scaled
        return out

    check_(not np.allclose(good, unscaled(_frame()), atol=ATOL_NORM),
           "a centred-but-UNSCALED implementation is REJECTED")

    def zero_filled(frame):
        f2 = frame.copy()
        f2[np.isnan(f2)] = 0.0             # the 19,002-hand-blocks bug
        return LD.normalize(f2)

    f = _frame(); f[33:54] = np.nan
    check_(not np.allclose(LD.normalize(f), zero_filled(f), atol=ATOL_NORM, equal_nan=True),
           "substituting 0 for a missing hand is REJECTED")

    print("\n" + ("ALL CHECKS PASSED" if ok else "SOMETHING FAILED — see above"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--emit", action="store_true", help="write golden_fixtures.json")
    ap.add_argument("--check", action="store_true", help="verify this repo against them")
    ap.add_argument("--with-model", action="store_true", help="--emit also runs the SavedModel")
    ap.add_argument("--emit-js", action="store_true", help="write the frontend's checker")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.emit_js:
        JS_CHECKER.write_text(JS_SOURCE, encoding="utf-8")
        print(f"[ok] {JS_CHECKER}  — `node golden_parity.mjs` beside golden_fixtures.json")
        return 0
    if a.emit:
        return emit(a.with_model)
    if a.check:
        return check()
    ap.error("pass --emit, --check, --emit-js or --selftest")


JS_SOURCE = r"""// golden_parity.mjs — MODEL_CONTRACT.md task #26, the frontend half.
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
"""


if __name__ == "__main__":
    raise SystemExit(main())
