#!/usr/bin/env python3
"""
Google ASL Fingerspelling -> our 75-point convention. The step nothing else can start without.

WHY THIS IS THE FIRST FILE
--------------------------
The competition parquets are ~190 GB across 1,631 columns: 543 MediaPipe Holistic landmarks x3,
plus `frame` and `sequence_id`. Our convention uses pose(33) + left_hand(21) + right_hand(21) =
**75 points = 225 columns = 13.8%**, which turns 190 GB of I/O into **~26 GB**. That single
subset is what makes this corpus tractable on a Kaggle session at all. No model, no CTC head,
no augmentation matters until the data can be read.

`verify_fingerspelling_parity.py` already proved (13/13, 2026-08-27) that the convention really
is ours: `{axis}_{group}_{index}` naming, pose 11/12 really are the shoulders, both hand blocks
verified against their own pose wrist, and the missing-value sentinel is **NaN, not GISLR's
zero** — so `canonicalize_missing()` is a free no-op here and must NOT be re-run (rewriting
zeros would corrupt real coordinates that happen to sit at 0).

RAGGED BY DESIGN
----------------
Sequences are variable length and a CTC model consumes them that way, so this does NOT resize to
a fixed frame count. Storage is the standard ragged layout: one concatenated `frames` array plus
`starts`/`lengths`. The 250-word pipeline's 64-frame resize is exactly the operation that would
destroy the timing a letter sequence is made of — do not reach for it here out of habit.

THE PROBLEM THIS FILE MEASURES BUT DOES NOT SOLVE
-------------------------------------------------
**~45% of frames have no tracked hand** — the hand that is actively spelling — and the gaps are
entirely interior (leading 0.1%, trailing 0.0%), so trimming buys nothing. Interpolation does not
rescue it either: 55% of gaps are <=3 frames but hold only 12.4% of lost frames, while ~64% of
lost frames sit in gaps >10 frames, where filling them would FABRICATE handshapes — that is,
invent letters. Root cause is R5 again, at 3.60x: the tracker loses the hand that is moving.

So this writes the gap structure per sequence (`hand_rate`, `max_gap`, `n_gaps`) and leaves the
decision to the model stage. Deciding what the model sees where the hand isn't matters more than
the head on top of it, and it is not a decision to make silently inside a data loader.

USAGE
  # measure first, write nothing
  python subset_landmarks.py --base /kaggle/input/asl-fingerspelling --report --limit-files 1

  # then subset
  python subset_landmarks.py --base ... --out /kaggle/working/fs75 --limit-files 4

  # self-test on a synthetic parquet, no competition data needed
  python subset_landmarks.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

POSE_N, HAND_N = 33, 21
N_POINTS = 75                       # pose 0-32 | left_hand 33-53 | right_hand 54-74
POSE_SLICE = slice(0, 33)
L_HAND_SLICE = slice(33, 54)
R_HAND_SLICE = slice(54, 75)


def our_columns() -> list[str]:
    """The 225 column names, in the order our (T,75,3) layout expects them."""
    cols = [f"{a}_pose_{i}" for i in range(POSE_N) for a in "xyz"]
    for grp in ("left_hand", "right_hand"):
        cols += [f"{a}_{grp}_{i}" for i in range(HAND_N) for a in "xyz"]
    return cols


def to_clip(df, columns: list[str]) -> np.ndarray:
    """(T rows) -> (T,75,3) float32 in our landmark order, NaN where untracked."""
    arr = df[columns].to_numpy(dtype=np.float32, copy=False)
    return arr.reshape(len(df), N_POINTS, 3)


def hand_gaps(clip: np.ndarray) -> dict:
    """Gap structure of the DOMINANT hand — the one doing the spelling.

    Dominant is whichever block is tracked in more frames. A sequence can legitimately have
    both (a few frames of the passive hand entering), so this is a per-sequence decision, not
    a per-signer one — and unlike Sem-Lex there is no bilateral hold to confuse it.
    """
    l_seen = np.isfinite(clip[:, L_HAND_SLICE, 0]).any(axis=1)
    r_seen = np.isfinite(clip[:, R_HAND_SLICE, 0]).any(axis=1)
    dom_is_right = r_seen.sum() >= l_seen.sum()
    seen = r_seen if dom_is_right else l_seen
    T = len(seen)

    gaps, run = [], 0
    for s in seen:
        if s:
            if run:
                gaps.append(run)
            run = 0
        else:
            run += 1
    if run:
        gaps.append(run)
    return {
        "T": int(T),
        "dominant": "R" if dom_is_right else "L",
        "hand_rate": float(seen.mean()) if T else 0.0,
        "n_gaps": len(gaps),
        "max_gap": int(max(gaps)) if gaps else 0,
        "median_gap": float(np.median(gaps)) if gaps else 0.0,
        # leading/trailing are ~0 on this corpus; recorded so a future change is visible
        "lead": int(np.argmax(seen)) if seen.any() else T,
        "trail": int(np.argmax(seen[::-1])) if seen.any() else T,
    }


def write_subset(out: Path, all_frames: list, total: int,
                 starts, lengths, ids, phrases, parts) -> tuple[Path, Path]:
    """Write `frames.npy` (mmap-able) beside a metadata-only `fs75.npz`.

    The split is not tidiness. `np.load` CANNOT mmap a member of an .npz, so a trainer handed
    one self-contained fs75.npz has to materialise the entire frame block — 14.07 GB at 68
    shards against a Kaggle GPU notebook's ~13 GB of host RAM. It OOMs on memory it never
    uses, because train_ctc.py only ever reads `frames[s:s+n]`, one sequence at a time, which
    is exactly what mmap serves. As its own .npy the block stays on disk.

    ⚠️ CONSUMES `all_frames`: each clip is set to None once copied, so peak RAM is the input
    list alone. `np.concatenate` held the list AND its result — 2x peak, ~28 GB at 68 shards
    against ~30 GB on the CPU box.
    """
    frames_path, npz_path = out / "frames.npy", out / "fs75.npz"
    fp = np.lib.format.open_memmap(frames_path, mode="w+", dtype=np.float32,
                                   shape=(total, N_POINTS, 3))
    # Assigning None per index, not list.pop(0) — pop(0) is O(n) per call and would make
    # this O(n^2) over ~34k sequences.
    off = 0
    for i, clip in enumerate(all_frames):
        fp[off:off + len(clip)] = clip
        off += len(clip)
        all_frames[i] = None
    if off != total:
        sys.exit(f"[err] wrote {off:,} frames but counted {total:,} — starts/lengths would "
                 f"index past the end of frames.npy")
    fp.flush()
    mm = getattr(fp, "_mmap", None)      # release the handle; Windows keeps it open otherwise
    del fp
    if mm is not None:
        mm.close()

    # Metadata ONLY — deliberately no `frames` key, which is also how train_ctc.py tells the
    # two layouts apart. frames_shape lets the reader prove the sidecar it found belongs to
    # THIS manifest and not to another run left in the same folder.
    np.savez(npz_path,
             starts=np.array(starts, np.int64), lengths=np.array(lengths, np.int32),
             sequence_id=np.array(ids, np.int64), phrase=np.array(phrases),
             participant=np.array(parts, np.int32),
             frames_file=np.array("frames.npy"),
             frames_shape=np.array([total, N_POINTS, 3], np.int64))
    return frames_path, npz_path


def selftest() -> int:
    """Round-trip a synthetic parquet. Proves the reshape puts each landmark where we claim."""
    import pandas as pd

    cols = our_columns()
    assert len(cols) == 225, len(cols)
    T = 7
    # every value encodes its own (point, axis) so a transposed reshape cannot pass
    data = {}
    for p in range(N_POINTS):
        grp, i = (("pose", p) if p < 33 else
                  ("left_hand", p - 33) if p < 54 else ("right_hand", p - 54))
        for a, ax in enumerate("xyz"):
            data[f"{ax}_{grp}_{i}"] = np.full(T, p * 10 + a, dtype=np.float32)
    df = pd.DataFrame(data)

    clip = to_clip(df, cols)
    ok = True
    for p in range(N_POINTS):
        for a in range(3):
            if not np.allclose(clip[:, p, a], p * 10 + a):
                print(f"  FAIL point {p} axis {a}: got {clip[0, p, a]}, want {p*10+a}")
                ok = False
    print(f"  {'ok  ' if ok else 'FAIL'} every one of 75x3 lands in the right slot")

    # gap structure, hand-crafted so the expected answer is not in doubt
    c = np.full((10, N_POINTS, 3), np.nan, dtype=np.float32)
    c[[0, 1, 5, 9], R_HAND_SLICE, :] = 1.0            # gaps of 3 (frames 2-4) and 3 (6-8)
    g = hand_gaps(c)
    checks = [(g["dominant"] == "R", "dominant hand identified"),
              (abs(g["hand_rate"] - 0.4) < 1e-6, f"hand_rate 0.4 (got {g['hand_rate']})"),
              (g["n_gaps"] == 2, f"2 interior gaps (got {g['n_gaps']})"),
              (g["max_gap"] == 3, f"max gap 3 (got {g['max_gap']})"),
              (g["lead"] == 0, f"no leading gap (got {g['lead']})")]
    for cond, label in checks:
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")
        ok &= cond

    # a left-dominant sequence must not be silently read as right
    c2 = np.full((6, N_POINTS, 3), np.nan, dtype=np.float32)
    c2[:, L_HAND_SLICE, :] = 1.0
    left_ok = hand_gaps(c2)["dominant"] == "L"
    print(f"  {'ok  ' if left_ok else 'FAIL'} left-dominant sequence reads as L")
    ok &= left_ok

    # the two-file write: it must equal np.concatenate exactly, and free as it goes
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        d = Path(td)
        rng = np.random.default_rng(0)
        clips = [rng.random((n, N_POINTS, 3)).astype(np.float32) for n in (12, 5, 23)]
        want = np.concatenate(clips, axis=0)          # the old behaviour, as the oracle
        st, ln, total = [0, 12, 17], [12, 5, 23], 40
        fpth, npth = write_subset(d, list(clips), total, st, ln,
                                  [1, 2, 3], ["ab", "c", "de"], [7, 7, 8])

        got = np.load(fpth, mmap_mode="r")
        w = [(np.array_equal(np.asarray(got), want),
              "streamed frames.npy is byte-identical to np.concatenate"),
             (got.shape == (total, N_POINTS, 3) and got.dtype == np.float32,
              f"frames.npy is {(total, N_POINTS, 3)} float32"),
             (isinstance(got, np.memmap), "frames.npy loads as a memmap (the whole point)")]
        mm = getattr(got, "_mmap", None)
        del got
        if mm is not None:
            mm.close()

        z = np.load(npth, allow_pickle=False)
        w += [("frames" not in z.files,
               "fs75.npz carries NO frames key — that is how the reader picks the layout"),
              (tuple(int(v) for v in z["frames_shape"]) == (total, N_POINTS, 3),
               "fs75.npz records frames_shape so a foreign sidecar can be caught"),
              (npth.stat().st_size < fpth.stat().st_size,
               "the npz is now metadata-sized, far smaller than the frame block")]
        z.close()

        # the memory claim has to be checked, not asserted: the caller's list is emptied
        again = d / "again"
        again.mkdir()
        consumed = list(clips)
        write_subset(again, consumed, total, st, ln, [1, 2, 3], ["ab", "c", "de"], [7, 7, 8])
        w.append((all(c is None for c in consumed),
                  "write_subset RELEASES each clip as it copies (peak is the list, not 2x)"))

        for cond, label in w:
            print(f"  {'ok  ' if cond else 'FAIL'} {label}")
            ok &= bool(cond)

    print("\nALL CHECKS PASSED" if ok else "\nFAILURES ABOVE")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="subset ASL Fingerspelling to our 75 points")
    ap.add_argument("--base", default="/kaggle/input/asl-fingerspelling")
    ap.add_argument("--out", type=Path, help="output dir (omit with --report)")
    ap.add_argument("--report", action="store_true", help="measure only, write nothing")
    ap.add_argument("--limit-files", type=int, help="process at most N parquet shards")
    ap.add_argument("--limit-seq", type=int, help="at most N sequences per shard")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.report and not args.out:
        ap.error("pass --out, or --report to measure without writing")

    import pandas as pd
    import pyarrow.parquet as pq

    base = Path(args.base)
    if not base.exists():
        sys.exit(f"[err] not found: {base} — attach the competition or pass --base")
    files = sorted(glob.glob(str(base / "train_landmarks" / "*.parquet")))
    if not files:
        sys.exit(f"[err] no parquets under {base / 'train_landmarks'}")
    if args.limit_files:
        files = files[:args.limit_files]

    cols = our_columns()
    schema = pq.ParquetFile(files[0]).schema_arrow.names
    missing = [c for c in cols if c not in schema]
    if missing:
        sys.exit(f"[err] {len(missing)} expected columns absent, e.g. {missing[:4]} — the "
                 f"naming scheme changed; re-run verify_fingerspelling_parity.py")
    print(f"[cfg] {len(cols)}/{len(schema)} columns = {len(cols)/len(schema)*100:.1f}%"
          f"  -> ~{190 * len(cols)/len(schema):.0f} GB effective, not 190 GB")

    meta = pd.read_csv(base / "train.csv")
    print(f"[cfg] {len(meta):,} sequences, {meta.participant_id.nunique()} participants, "
          f"{len(files)} shard(s) this run\n")

    all_frames, starts, lengths, ids, phrases, parts, stats = [], [], [], [], [], [], []
    total = 0
    for fi, f in enumerate(files):
        rel = "train_landmarks/" + os.path.basename(f)
        rows = meta[meta.path == rel]
        if args.limit_seq:
            rows = rows.head(args.limit_seq)
        # ONE read per shard, then split by sequence. Reading per-sequence re-opens the file
        # once per row group and is the difference between minutes and hours.
        df = pd.read_parquet(f, columns=cols)
        # sequence_id is the parquet INDEX on this corpus, but tolerate it as a column too.
        if df.index.name == "sequence_id":
            idx = df.index.to_numpy()
        else:
            idx = pd.read_parquet(f, columns=["sequence_id"])["sequence_id"].to_numpy()
        # Group ONCE. `idx == seq_id` inside the loop is O(sequences x rows) — on a shard with
        # ~1k sequences and ~1M rows that is a billion comparisons per shard, for no reason.
        groups = pd.Series(np.arange(len(idx)), index=idx).groupby(level=0).indices

        for _, r in rows.iterrows():
            pos = groups.get(int(r.sequence_id))
            if pos is None or len(pos) == 0:
                continue
            n = len(pos)
            clip = to_clip(df.iloc[pos], cols)
            g = hand_gaps(clip)
            g.update(sequence_id=int(r.sequence_id), participant=int(r.participant_id),
                     phrase_len=len(str(r.phrase)))
            stats.append(g)
            if not args.report:
                all_frames.append(clip)
                starts.append(total)
                lengths.append(n)
                ids.append(int(r.sequence_id))
                phrases.append(str(r.phrase))
                parts.append(int(r.participant_id))
            total += n
        print(f"[{fi+1}/{len(files)}] {os.path.basename(f)}: {len(rows)} sequences, "
              f"{total:,} frames so far", flush=True)

    if not stats:
        sys.exit("[err] no sequences matched — check train.csv's `path` column")

    hr = np.array([s["hand_rate"] for s in stats])
    mg = np.array([s["max_gap"] for s in stats])
    T = np.array([s["T"] for s in stats])
    print(f"\n=== {len(stats)} sequences, {total:,} frames ===")
    print(f"length   median {np.median(T):.0f}  p90 {np.percentile(T, 90):.0f}  max {T.max()}")
    print(f"DOMINANT-HAND presence   mean {hr.mean():.3f}  median {np.median(hr):.3f}  "
          f"p10 {np.percentile(hr, 10):.3f}")
    print(f"  -> {(1-hr.mean())*100:.0f}% of frames have no tracked spelling hand")
    print(f"max interior gap   median {np.median(mg):.0f}  p90 {np.percentile(mg, 90):.0f}  "
          f"max {mg.max()}")
    print(f"sequences with a gap >10 frames: {(mg > 10).mean():.0%}  "
          f"(interpolating those FABRICATES letters — do not)")
    print(f"dominant hand: R {sum(s['dominant']=='R' for s in stats)}  "
          f"L {sum(s['dominant']=='L' for s in stats)}")

    if args.report:
        print("\n[report] nothing written. Re-run with --out to subset.")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    frames_path, npz_path = write_subset(args.out, all_frames, total,
                                         starts, lengths, ids, phrases, parts)
    (args.out / "gap_stats.json").write_text(json.dumps(stats))
    gb = frames_path.stat().st_size / 1e9
    kb = npz_path.stat().st_size / 1e3
    print(f"\n[ok] {frames_path}  ({total}, {N_POINTS}, 3) float32  {gb:.2f} GB  <- mmap-able")
    print(f"[ok] {npz_path}  metadata only  {kb:.0f} KB")
    print(f"[ok] {args.out / 'gap_stats.json'}  {len(stats)} sequences")
    print("\n⚠️  BOTH files are required. A Kaggle dataset built from only fs75.npz will fail "
          "at load\n    time, because the frames are no longer inside it.")
    print("\nRagged on purpose: frames are concatenated with starts/lengths. Do NOT resize to a "
          "fixed frame count —\nthat is what would destroy the timing a letter sequence is made of.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
