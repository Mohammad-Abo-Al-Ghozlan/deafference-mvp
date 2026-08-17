"""Prove extract_landmarks.py's math is bit-identical to live_demo.py's inference path.
If this fails, a model trained on our extraction will silently mismatch what runs live."""
import sys, os
sys.path.insert(0, r"c:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference")
sys.path.insert(0, r"c:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference\training\medical")
os.chdir(r"c:\Users\1mhmd\OneDrive\Desktop\Deaffearance\Deafference")
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import numpy as np

import live_demo as L
import extract_landmarks as E

rng = np.random.default_rng(0)
fails = []

# ---- constants must agree ----
for name in ("N_POINTS", "POSE_N", "HAND_N", "MAX_LEN", "L_SHOULDER", "R_SHOULDER",
             "MP_COMPLEXITY", "MP_DET_CONF", "MP_TRK_CONF", "MP_MAX_W", "HANDPRESENCE_MIN"):
    a, b = getattr(L, name, "<missing>"), getattr(E, name, "<missing>")
    ok = a == b
    print(f"const {name:14} live={a!r:6} extract={b!r:6} {'OK' if ok else 'MISMATCH'}")
    if not ok: fails.append(f"const {name}")

# ---- normalize() must match exactly, including the None cases ----
print("\nnormalize() on 500 random frames (incl. NaN shoulders):")
n_none_l = n_none_e = 0
maxdiff = 0.0
for i in range(500):
    f = rng.standard_normal((75, 3)).astype(np.float32)
    if i % 7 == 0: f[L.L_SHOULDER, :2] = np.nan          # force the drop path
    if i % 11 == 0: f[L.R_SHOULDER, :2] = np.nan
    if i % 23 == 0: f[L.L_SHOULDER, :2] = f[L.R_SHOULDER, :2]   # zero shoulder width
    a, b = L.normalize(f.copy()), E.normalize(f.copy())
    if (a is None) != (b is None):
        fails.append(f"normalize None-disagreement at {i}"); continue
    if a is None:
        n_none_l += 1; n_none_e += 1; continue
    d = float(np.nanmax(np.abs(a - b)))
    maxdiff = max(maxdiff, d)
print(f"  dropped frames: live={n_none_l} extract={n_none_e}")
print(f"  max abs diff on kept frames: {maxdiff:.3e}  {'OK' if maxdiff == 0.0 else 'MISMATCH'}")
if maxdiff != 0.0: fails.append("normalize values")

# ---- time_resize() must match exactly, at many input lengths ----
print("\ntime_resize() across input lengths:")
worst = 0.0
for t in (1, 2, 3, 5, 17, 31, 63, 64, 65, 100, 237):
    a_in = rng.standard_normal((t, 75, 3)).astype(np.float32)
    a, b = L.time_resize(a_in.copy(), 64), E.time_resize(a_in.copy(), 64)
    if a.shape != b.shape:
        fails.append(f"time_resize shape at T={t}"); continue
    d = float(np.max(np.abs(a - b))); worst = max(worst, d)
    print(f"  T={t:4} -> {b.shape}  diff={d:.3e}  {'OK' if d == 0.0 else 'MISMATCH'}")
if worst != 0.0: fails.append("time_resize values")

# ---- extract_75 slot layout: assert the exact index ranges ----
print("\nextract_75 slot layout:")
class _LM:
    def __init__(s, n): s.landmark = [type("p", (), {"x": float(i), "y": float(i)+.5, "z": float(i)+.25})()
                                      for i in range(n)]
class _Res:
    pose_landmarks = _LM(33); left_hand_landmarks = _LM(21); right_hand_landmarks = _LM(21)
pl, pe = L.extract_75(_Res()), E.extract_75(_Res())
d = float(np.nanmax(np.abs(pl - pe)))
print(f"  live vs extract max diff = {d:.3e}  {'OK' if d == 0.0 else 'MISMATCH'}")
if d != 0.0: fails.append("extract_75")
print(f"  pose slot 0   = {pe[0].tolist()}   (expect [0.0, 0.5, 0.25])")
print(f"  L-hand slot 33= {pe[33].tolist()}  (expect [0.0, 0.5, 0.25] = left hand idx 0)")
print(f"  R-hand slot 54= {pe[54].tolist()}  (expect [0.0, 0.5, 0.25] = right hand idx 0)")
assert pe.shape == (75, 3)

# ---- undetected -> NaN, not zero (zeros would be a silent, learnable lie) ----
class _Empty:
    pose_landmarks = None; left_hand_landmarks = None; right_hand_landmarks = None
e = E.extract_75(_Empty())
allnan = bool(np.isnan(e).all())
print(f"\nundetected frame is all-NaN (not zeros): {allnan}  {'OK' if allnan else 'MISMATCH'}")
if not allnan: fails.append("undetected must be NaN")

print("\n" + ("PARITY OK — extraction matches live_demo exactly" if not fails
             else f"PARITY FAILURES: {fails}"))
sys.exit(1 if fails else 0)
