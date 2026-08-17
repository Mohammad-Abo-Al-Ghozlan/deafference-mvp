# Re: your v6 — I was wrong about the cause, and the real one was worse

**To:** animation / retargeting
**From:** Mohammad Salim
**Re:** `REPLY-TO-SALIM-v6.md`, `check-export3.py`, `suspect-clips.csv`, `weakdrop.txt`,
`chirality-check.mjs`
**Attached:** new `animation_handoff/` (250 words), `handshape_templates.json`,
`asl_handedness_250.json` (now with the 2a passive set), `sign_clips_250.meta.json`,
`SIGN_ANIMATION_CONTRACT.md`

---

## ⚠️ Before you touch the rig — three changes, and one of them will break your parser

Everything from §0 down is the *why*. This section is the *what to do*, because two of these
are breaking changes and you will hit them in the first ten minutes.

### 1. Clip length is now variable — 9 to 116 frames. It used to be exactly 64, every word.

**This is the one that will break you.** The contract has always specified duration as
`len(frames) / fps`, but every export you have ever received had all 250 clips resampled to a
fixed 64 frames — so a hardcoded `64` would have worked perfectly and you had no reason to
doubt it. It won't now. Read the array length per word.

The change is deliberate. Clips carry their **native** duration, so each sign plays at the
speed it was actually signed instead of being stretched or squeezed into a fixed window.
`tiger` is 9 frames (0.30 s); `puppy` is 116 (3.87 s). Timing should feel considerably better.
*(Corrected: an earlier copy of this letter said `quiet` was the 116-frame word. `quiet` is 44
frames / 1.47 s. You had it right in your v8.)*

### 2. Read `segments[].synthesis.dominantHand`. Do not derive it.

It is `"R"` in all 250 files **by construction** — left-dominant signers were mirrored at
extraction. Deriving dominance from wrist travel is precisely what produced the wrong-arm
export: on symmetric signs the two arms tie, and whatever breaks the tie decides the hand. If
your code still infers which hand to drive, that inference *is* the bug. Delete it, read the
field.

### 3. Two-handed words (87 of 250) contain ONE hand. The passive hand must be synthesized.

This is not a gap in this export, it is a property of the corpus, and it will not improve with
better selection or a re-extraction. GISLR records **one hand per participant**: both hands
appear in 1.7% of clips and both-hand *frames* average 0.1%. There exists no take of any word
with two tracked hands.

What you have instead is enough to build from. The passive **wrist** is a pose landmark and is
present in every frame (`passiveWristIndex`), so position is already solved — only the
handshape is missing. §6.1 gives the two rules: mirror the dominant handshape for the 52 `2s`
words, and place the assigned unmarked handshape for the 35 `2a` words
(`passiveHandshape.shape`, a key into `handshape_templates.json`).

Until you implement that, two-handed signs will show one hand — but it is now the **correct**
one. Previously they showed one hand and on 137 words it was the wrong one.

### New field: `synthesis.sourceQuality`

Tells you how thin the source was for that word, so you can compensate instead of filing a bug:

| field | meaning |
|---|---|
| `validTakes` | takes that passed validity for this word. **Corpus median: 114.** |
| `thin` | `true` when `validTakes <= 2` — this exemplar is all there was |
| `brief` | `true` when the sign is under 0.53 s and may need slowing to read |
| `sourceClip` | the exact take, e.g. `TV/53618_1962886557` — quote it if you report a problem |

**20 words are `thin`**, 7 of them had exactly one usable take (`boat`, `drop`, `have`, `many`,
`quiet`, `store`, `tiger`). **6 are `brief`** (`bye`, `tiger`, `tomorrow`, `tongue`, `wet`,
`yourself`). `tiger` is both: one take, nine frames. For these, "pick a better take" was never
an option — extra hold or easing on your side will do more than anything I can do on mine.

### Two decisions I need from you

**`finish` — a genuine tie, not a hole.** Your `check-export3.py` reports it as missing the
dominant hand, and my export asserts `dominantHand: "R"`. Both are defensible: its
wrist-travel ratio is **exactly 1.00**, so the two arms are indistinguishable by travel and
each of us breaks the tie differently. It is 1 word in 250 and there is no data problem to
fix — but we should agree one tie-break rule and both implement it, rather than keep
disagreeing. I propose: **at a ratio within ±0.05 of 1.00, take `dominantHand` from the file.**
Tell me if you'd rather it went the other way.

**Per-landmark confidence — I'd like to drop it from the contract.** Your checker flags it as
missing and I don't think it should exist. GISLR never stored MediaPipe's confidence values, so
I cannot emit real ones; the best I could do is a present/absent flag, which you can already
derive yourself — a missing point is `null`, never `[0,0,0]`. Emitting it per landmark per
frame would inflate all 250 files to tell you something the nulls already say. Unless it's
load-bearing for you somewhere I'm not seeing, I'd rather remove the requirement and document
why. Your call.

---

## 0. Start here — I told you the wrong thing

I predicted that re-extracting on the canonical layout would take your **137 dominant-missing
words to zero**. I ran your `check-export3.py` on that rebuild:

```
[FAIL] DOMINANT-hand coverage >= 70%          0.4%
[FAIL] words missing the DOMINANT hand == 0   249 words
       signing hand 0.4%   resting hand 96.9%
```

**137 → 249.** Not an improvement, a near-total inversion, and my own selector reported
`DOMINANT-hand coverage mean 0.962` on the same export at the same moment. Both numbers were
correct. They were measuring different hands.

The actual root cause is below. It also explains the two anomalies in *your* v6 that neither
of us could place — your 137 missing-dominant words, and your 50 two-handed words that had
"some passive coverage" when my contract said there should be none. Same bug, seen from your
end.

The fix is in. Your criteria now read:

```
[PASS] DOMINANT-hand coverage >= 70%          76.2%
[FAIL] words missing the DOMINANT hand == 0   1 word     <- `finish`, and it is a tie-break
                                                            artifact, not a hole — §3
[PASS] every 2s/2a word has a passive WRIST track
[PASS] every 2s/2a word has a synthesis class
[PASS] no hand block encoded as 21 zeros
[PASS] native clip duration
[PASS] handedness convention is consistent
[FAIL] per-landmark confidence present        missing    <- cannot be satisfied — §4
       signing hand 76.2%   resting hand 0.1%
       tracker-drop ratio 1.52x   (was 4.06x)
```

---

## 1. R5 — MediaPipe keeps the RESTING hand

Your own diagnostic found it first, in the line you wrote as a sanity check:

```
median wrist speed, hand block PRESENT : 0.0208 sh.w./frame
median wrist speed, hand block MISSING : 0.0317
```

The tracker preferentially loses the hand that **moves**. So in a one-hand-per-participant
corpus, the 21-point block you *do* get is disproportionately the hand that is doing nothing.

Then three of my stages compounded it, each defensible alone:

1. **Canonicalization chose dominance from hand-block frame counts.** Since the kept hand is
   the still one, it canonicalized on the resting hand. My own `wrist_travel` docstring warns
   against exactly this; I'd written the warning and then routed around it as a nuisance.
2. **The selector maximized hand coverage.** Coverage is anti-correlated with motion —
   `pearson r = -0.464` over 250 words, **negative for 100% of them**. Maximizing coverage
   *is* selecting for stillness.
3. Net effect: the wrong hand chosen with **99.6% precision against a 44.9% base rate.** The
   selector wasn't erring. It was reliably optimizing the wrong objective.

The evidence had been in the export the whole time. Every word's metadata carried
`"required_hand": "R"` immediately next to `"dominant": "L"`. Nothing ever compared the two
fields.

**What settled it was geometry, not labels** — and this is the part I'd steal from your
0.0000 m test. Hand landmark 0 *is* a wrist, so its distance to a pose wrist identifies the
limb regardless of what anything is named:

```
median distance to own limb   : 0.088 shoulder-widths
median distance to other limb : 1.783
```

20× separation, no threshold to tune. There was never a labelling ambiguity to argue about.

### 1.1 This resolves your §1 discrepancy

You wrote:

> Your renderer contract says the passive hand "DOES NOT EXIST in our corpus for any take".
> I measure **37 of 87** two-handed words with zero passive coverage — so **50 have some**.

Those 50 words are R5. On the pre-canonical export you had, the tracked hand frequently
landed in the block *opposite* your computed dominant — because your dominance came from
wrist travel (correct) while the tracked hand was the resting one. So you measured coverage
in the block you called passive, and it was the only hand in the clip.

It's the same phenomenon as your 137 missing-dominant words: one hand, filed on the wrong
side. Your two anomalies were one anomaly.

On the new export:

```
passive-hand coverage : mean 0.000, zero for 250 / 250
```

So the contract line was right, and it is now right for a verified reason rather than by
assumption. **Please re-run your suite** — every number you sent me in v6 was computed on
mis-sided data, including the 21× independence result (that conclusion I do expect to hold,
since it's about wrist *presence*, not hand identity).

### 1.2 The corpus was never the problem

```
takes where the tracked hand IS the moving arm : 44418/80647 (55.1%)
words with at least one such take              : 250/250
per-word usable takes: min 55  p25 153  median 178  max 261
```

A selection bug with a selection fix. No retraining, no re-collection.

---

## 2. The fix, and what it cost

`hand_arm_alignment()` now rejects any take whose tracked hand sits on the still arm, *before*
any coverage or class rule is considered. 250/250 exemplars are verified to carry the signing
hand.

**It cost coverage, and that is correct.** My selector's reported mean fell **0.962 → 0.685**.
The old 0.962 was coverage of the resting hand, which is easy to track precisely because it
isn't moving. Lower coverage of the right hand is worth more than high coverage of the wrong
one. (Your 76.2% and my 0.685 aren't in conflict — yours pools over all exported frames, mine
is a per-word mean inside the sign extent, so long one-handed clips lift yours.)

Where the remaining coverage sits is the thing you'll care about:

| class | n | dominant coverage | valid takes (median) |
|---|---|---|---|
| one-handed | 163 | 0.829 | 138 |
| 2s | 52 | 0.412 | 3 |
| 2a | 35 | 0.422 | 5 |

**One-handed signs are done. The whole remaining problem is your 87 two-handed words**, and
it's pool size, not selection: the validity filter passes 48% of one-handed candidates but
**1% of 2s** and **2% of 2a**. At a median of 3 valid takes there is no selection pressure
left — 20 words have ≤2 valid takes, 7 have exactly one. For those, the exemplar isn't the
best take, it's the only take. Six words come in under 0.53 s for the same reason.

That's structural: a two-handed take needs both motion (to be valid) and coverage (to be
usable), and §1 established those trade directly against each other. Loosening the filter buys
coverage by re-admitting takes where the passive arm is merely hanging — a worse artifact,
and harder for either of us to detect.

So the honest lever is on your side, and I've made it explicit rather than leaving you to
infer it: every word in **this** export carries `segments[].synthesis.dominantCoverage` (new
in this handoff — see §9 for the one-line check), the fraction of frames where the dominant
handshape is actually measured. It is computed over the whole exported clip, so it will read a
little higher than the sign-extent figure in `sign_clips_250.meta.json` → `coverage`; use the
one in the word file, and don't mix the two. **Hold or interpolate through the
rest, and treat that number as how much of the word you are inventing.** That's interpolation
the consumer knows about — the opposite of the ffill problem, where the fill was silent.

---

## 3. `finish` — the last FAIL is a definition mismatch, not a hole

`finish` is fine. The right hand is present in **10 of 22 frames**.

We derive dominance differently: I use absolute wrist travel, `check-export3.py:127` uses
shoulder-relative wrist path with an elbow-present gate. Across all 250 words those two
definitions disagree on **exactly one word**:

```
words where the two dominance metrics disagree : 1/250   (finish)
finish travel ratio                            : 1.00
```

1.00 is a perfect tie — `finish` is symmetric, both arms genuinely move the same amount — and
the tie broke toward L on your side. Canonicalization guarantees the tracked hand is always at
54–74, so reading the left block returns 0% **by construction**, on any word where a tie lands
that way.

**Suggested one-line fix: stop re-deriving it.** The dominant hand is `"R"` in all 250
exemplars by construction, because left-dominant signers are mirrored at extraction. Read it
instead of computing `dom` from `path[]`, and this class of failure disappears rather than
being re-rolled on every symmetric word.

Two places to read it, because your script may see either export: this handoff asserts it per
word at `segments[].synthesis.dominantHand`, and `sign_clips_250.meta.json` has carried it all
along as per-word `required_hand` (`"R"` for 250/250). If your `dom` lookup comes back
`undefined`, **do not fall through to the travel metric** — that silent fallback is exactly how
`finish` failed. Hard-code `"R"` and assert it.

This is our §4 problem in miniature — two sides measuring "dominant" differently and neither
metric able to see the other's failure. It cost us 249 words once already.

---

## 4. `per-landmark confidence` cannot be satisfied — please drop it

Not "not yet". GISLR carries no per-landmark confidence, and nullness already encodes
visibility *exactly*: a point is null iff the tracker didn't produce it. A fourth component
would be a constant function of the first three — `1.0` where present, `0.0` where null. I'd
be shipping a column that adds nothing and implies a measurement I don't have.

By your own closing rule, a criterion that can never pass isn't a criterion. Same category as
`passive hand absent == 0`, which you already moved to `[ -- ]`. I'd rather it come out than
sit as a permanent red line we both learn to ignore.

---

## 5. The 2a unmarked handshape set — attached, and the gap is smaller than expected

You asked for the B/A/S/1/5/C/O configurations as 21-point templates in the export's
coordinate convention. Attached as `handshape_templates.json`, measured from the corpus at 24
anchor words rather than authored:

```
shape  takes  agree_xy  verdict
B        160     0.131  OK          1        160     0.150  OK
A        120     0.180  OK          5        160     0.152  OK
C        120     0.198  OK          S        120     0.337  takes disagree
                                    O        120     0.286  low-confidence anchor
```

That table is the measurement **before** I fixed the `S` anchor, and I'm showing it because it
is what motivated the change. `S` was being averaged over `milk` and `orange`, both of which are
*dynamic* — the hand opens and closes during the sign, so a single hold frame lands anywhere in
that cycle. `agree_xy 0.337` was a bad anchor, not noisy takes. `yes` is the only static `S` in
the vocabulary, so `S` is now measured from it alone and labelled `single_anchor` — weaker
evidence, stated as such rather than hidden.

Because `S` and `O` still can't be trusted blind, the file carries an explicit `resolution`
map so neither of us invents a policy: **`S→A`, `O→C`**. `S→A` is defensible because both are
unmarked fists whose only measured difference is thumb position (1.24 vs 1.49 palm lengths) —
exactly where tracking a closed fist is least reliable.

**Same staleness caveat as §9:** the `resolution` map is new, so confirm you have the current
file before relying on it —

```bash
node -e "const t=require('./handshape_templates.json');
         if(!t.resolution){console.error('OLD FILE: no resolution map — ask Salim to re-send');process.exit(1)}
         console.log('OK', JSON.stringify(t.resolution))"
```

And the practical scope is smaller than the two failures suggest: **34 of the 35 `2a` words land
on a measured template.** Only `time` needs the fallback (it wants `S`), and **`O` is required by
no word at all** — so its low confidence costs nothing.

Then the part that matters: a template set is useless without knowing *which* shape each word
takes. The Dominance Condition narrows it to seven; it doesn't pick. So all 35 `2a` words now
have an assigned passive handshape **and a contact target**, since a handshape alone doesn't
say which surface the dominant hand meets:

```
shape   : B 26, A 3, 1 3, C 2, S 1
contact : palm 14, forearm 5, back_of_hand 5, side_of_hand 3, opening 2, ...
2a words on a MEASURED template  : 34/35
2a words on a documented fallback:  1/35   (`time`, via S→A)
O is unusable AND needed by no 2a word.
```

B at 26/35 is the sanity check — Battison predicts B as the dominant unmarked base, and that
fell out of the assignment rather than being imposed.

**Four caveats, because you'll build on this.**

- **NOT DEAF-REVIEWED.** Written from published descriptions. Placeholders that unblock the
  rig, not authority. 6 rows are `conf: low`.
- **5 words contact the FOREARM, not a hand**: `arm`, `flag`, `morning`, `table`, `tree`. Your
  base-location logic probably assumes a hand. These need the forearm as the target surface.
- **`chair` and `helicopter` have passive handshapes outside the unmarked set** (H and 3).
  Either casual signing violates the Dominance Condition there or my `2a` label is wrong. Be
  precise about what the file does here, because I was sloppy about it first time: `shape` for
  both is **`"1"`**, a deliberate substitute — the closest unmarked shape, since H and 3 have no
  template to point at. The true handshape appears only in the prose `note`, and
  `outside_unmarked_set: true` marks the row. So the machine-readable field *is* rounded; the
  flag exists so the rounding is visible rather than silent. Render `1` and expect these two to
  look wrong until a reviewer rules on them.
- **The `conf` field is my confidence in the shape**, deliberately separate from the lexicon's
  confidence in the *class*. A word can be confidently `2a` with a guessed passive shape.

---

## 6. Your contiguity suggestion — adopted, and it earned its place

> consider scoring it within `segments` *and* requiring contiguity: 30 frames spanning the
> stroke beats 30 scattered across the take

Adopted as written. The selector now scores coverage inside the sign extent and reports the
longest single covered run (`run` in the tables, `longest_run` in the meta). It changes picks —
you can see it in words like `stairs` (cov 0.18, run 0.04): high scatter, no usable stroke.
Without the run term those takes score as mid-tier instead of last.

---

## 7. Your weak-drop filter has a false-positive class, and I think it's most of it

This is the one place I'd push back, and your own CSV is the evidence.

Your rule flags a `2s` take when the passive arm mirrors in <20% of frames, verdict
`WEAK-DROP: passive arm not mirroring`. But 9 of those words have a passive arm travelling
**85–99% as far as the dominant one**:

```
story   ratio 0.987  mirror 10%      loud    ratio 0.910  mirror  0%
quiet   ratio 0.985  mirror 12%      same    ratio 0.885  mirror  0%
rain    ratio 0.978  mirror  1%      jacket  ratio 0.857  mirror  9%
shoe    ratio 0.943  mirror  0%      awake   ratio 0.852  mirror  0%
bedroom ratio 0.931  mirror  3%
```

`rain` at ratio 0.978 is not a dropped weak hand. That arm is working.

And the pattern isn't confined to the flagged set. Of the **13** `2s` words where both arms
clearly move (ratio > 0.85), **12 of 13** score mirror < 50%.

The 13th is `now` (ratio 0.939), and it deserves calling out because it is the one case that
cuts the other way. `now` carries no `mirrorPct` in `suspect-clips.csv` and does not appear in
`weakdrop.txt` — and since that list is by construction the 46 of 52 words scoring *below* 80%,
`now` scored **≥ 80%**. Your own totals pin it: the 46 listed rows sum to 662/3643 while the
header total is 1066/4123, so the six unlisted words (`cry`, `glasswindow`, `have`, `now`,
`underwear`, `zebra`) pool to **404/480 = 84.2%**. So there is a word where both arms move
*and* they mirror — which is what a working detector looks like, and it's fair to say my first
pass at this quietly dropped it, because I counted only the rows that had a number in them.

Twelve out of thirteen is still not a run of bad takes.

**I think the reason is linguistic.** Battison's Symmetry Condition constrains **handshape** —
both hands take the same one. It does *not* require the trajectories to be sagittal mirrors.
Symmetric two-handed signs are well-formed moving **in phase** (both hands travel the same
direction), **out of phase** (alternating), or mirrored. A per-frame mirror test passes only
the third case, so it fails the majority of correct takes. Median `mirrorPct` across your 46
listed `2s` words is **12%** — though that set is selected on the outcome (it *is* the
sub-80% list), so the fair figure is the median over all 52, which comes to **15%** using the
84.2% residual for the six unlisted. Either way: not a corpus of dropped hands, that's the test.

Three consequences, and note the first is unchanged:

1. **Keep mirroring the handshape.** Your local-rotation fix and the 0.0000 m static
   verification are exactly right, and the Symmetry Condition genuinely licenses it.
2. **Don't use `mirrorPct` to reject takes.** Use the arm travel ratio alone — that's what
   actually indicts a take. Your `after` (2a, ratio 0.25) is a real weak drop; `rain` (0.978)
   is not.
3. **Don't synthesize the passive trajectory.** Both wrists are real pose landmarks in every
   frame, so play the recorded passive wrist as-is. Only the handshape is missing. Mirroring
   the dominant *trajectory* would replace real data with a guess, and per the above the
   guess would be wrong most of the time.

I may be wrong about the mechanism — my phase-vs-mirror reasoning is from the literature, not
measured on this rig. But the 12/12 says the current filter can't be read as a weak-drop
detector, whatever the cause.

---

## 8. On the inside-out hand

The most useful thing in your v6 wasn't the fix, it was that **four green checks sat over a
backwards palm** — anatomy gate 250/250, hinge check clean, jitter in budget, rig suite 60/60,
all bilaterally symmetric or per-joint, and therefore structurally blind to a chirality error.

I did the same thing twice this session, and it's why I led with §0. A probe I wrote to
compare two corpus layouts turned out to be comparing two corpora with the *same* layout, so
it could neither pass nor fail — and it reported "no regression". Then my staleness check
listed only symbols the *old* code also contained, so a stale build ran silently and produced
byte-identical output that I read as a successful re-run.

Your formulation is the right one and I've put it in the project's report: **a check that
cannot fail is indistinguishable from a check that passes.** The corollary I'd add is the one
your 0.0000 m test and my 0.088-vs-1.783 both satisfy: run the assertion once against the case
it's meant to catch, and prefer measuring a distance to trusting a field name. Every
naming-convention argument in this project — which hand is dominant, which block is left,
whether the image is mirrored — collapsed the moment someone measured instead of read.

---

## 9. What's in the new export

Same `sign-animation/v1` schema. One addition: **`segments[].synthesis`**, so each word file
is self-describing and you no longer have to join against the lexicon at render time.

**Check this before you code against it.** The block is new, and the export I sent you
*previously* does not have it — so if these two ever get mixed up, I would rather you find out
in one second than halfway through a renderer:

```bash
node -e "const d=require('./words/time.json');const s=d.segments[0].synthesis;
         if(!s){console.error('WRONG EXPORT: no synthesis block — ask Salim to re-send');process.exit(1)}
         console.log('OK',s.class,s.rule,s.dominantHand,s.passiveHandshape?.shape)"
# expect: OK 2a unmarked_handshape_at_base R S
```

If that prints `WRONG EXPORT`, you have the old folder and everything in this section is
inapplicable — the fallback is the two side files: `sign_clips_250.meta.json` → `words[]`
(`handedness_class`, `required_hand`, `coverage`) and `asl_handedness_250.json` →
`passive_handshape.words[*]`. Every value is derivable from those; only the location differs.

```json
"segments": [{
  "gloss": "time", "start": 0, "end": 39,
  "synthesis": {
    "class": "2a",
    "rule": "unmarked_handshape_at_base",
    "dominantHand": "R",
    "twoHanded": true,
    "labelConfidence": "high",
    "passiveHand": "L",
    "passiveWristIndex": 15,
    "passiveHandshape": { "shape": "S", "contact": "wrist", "conf": "med",
                          "note": "dominant 1 taps the BACK OF THE PASSIVE WRIST" },
    "dominantCoverage": 0.6923
  }
}]
```

- One-handed words get `rule: "none"` and **no** passive fields at all — if you see
  `passiveWristIndex`, the sign genuinely has a second hand.
- A stitched utterance carries one block **per gloss**, not one per file.
- `passiveHandshapeMissing: true` would mark a `2a` word I couldn't assign. There are
  currently none, and the exporter warns loudly if that ever changes.
- `dominantHand` is `"R"` in all 250 by construction — §3.

Still open on my side: the two-handed coverage ceiling (§2), and a Deaf review of the 50
flagged handedness labels plus the 6 low-confidence and 2 outside-the-set passive shapes.

Nothing blocking you. The 2a set is attached, so the last synthesis gap is closed on paper —
what I'd most like back is whether the forearm-contact five and the phase-vs-mirror argument
in §7 survive contact with the rig.
