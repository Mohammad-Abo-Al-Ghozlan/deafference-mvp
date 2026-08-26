# The two data licences, and exactly how to unblock them

**Written 2026-08-26.** Both gate real capability, both are pure waiting-on-other-people, and
both have long lead times — send them today even though each takes five minutes.

---

## 1. Sem-Lex — ANSWERED 2026-08-26, and the answer is NO for commercial use

### There is no email to send. There is a form, and it already states the terms.

Access is a Google Form linked from [github.com/leekezar/SemLex](https://github.com/leekezar/SemLex):

```
https://docs.google.com/forms/d/e/1FAIpQLSeFjIcbJcr2kWibgrEdFyLhNADo1ErnVGuQHtGeiDiqe4iteQ/viewform
```

It asks for Name, Email, and Affiliation ("School, company, government agency, or 'personal
use'"), plus agreement to work respectfully with deaf and hard-of-hearing communities. The
licence is **CC BY-NC-SA 4.0**, and the form states it verbatim:

> "I will give credit to the Sem-Lex Benchmark if I use it in my work."
> **"I will not use the Sem-Lex Benchmark for commercial purposes."**
> **"If I build on or modify the Benchmark, I will release this new version under the same
> license."**

### What this actually costs us

**NC blocks deployment in a commercial product.** That was the risk flagged before asking, and it
is confirmed rather than hypothetical.

**SA is the sharper problem, and it is easy to miss.** Share-Alike means a model built on the
Benchmark is arguably a derivative that must carry CC BY-NC-SA too. So it is not only "we cannot
sell it" — a *free* release would lock those weights non-commercial permanently, which forecloses
licensing the medical model later even if the company changes direction.

### Three licences, do not confuse them

| thing | licence | governs |
|---|---|---|
| the GitHub repo | Apache-2.0 | the **code**, not the data |
| the arXiv paper | CC BY-NC-SA 4.0 | the **paper** |
| **the dataset** | **CC BY-NC-SA 4.0** (the form) | **the data — this is the one that binds us** |

Seeing "Apache-2.0" on the repo and concluding the data is permissive would be a costly mistake.

### What is still worth doing

**Fill the form and do the feasibility study.** It is fully permitted, and it is genuinely
valuable: it proves the 130-word clinical vocabulary is learnable, it is publishable with
attribution, and it tells us how many takes per sign a self-recorded corpus actually needs —
which is the number that decides whether recording our own is a two-week or a six-month job.
Put the real affiliation on the form; "commercial company doing a feasibility study" is honest
and is not what the NC clause prohibits (using it *commercially* is).

**Then two options, neither explored yet:**

1. **Ask the authors for separate commercial terms.** CC BY-NC-SA is the *default* grant, not
   necessarily the only one they will offer. Authors of academic datasets do sometimes license
   commercially, especially for an accessibility application. Contacts: Lee Kezar (first author),
   Naomi Caselli and Zed Sevcikova Sehyr (senior authors, ASL-LEX lineage). Use the contact route
   on the repo or the paper — do not guess an address.
2. **Check ASL Citizen** (Microsoft Research, 83,399 videos / 2,731 signs / 52 signers). A
   completely separate licence question, untested. It may or may not be friendlier; MSR research
   datasets often carry their own restrictions, so read its terms with the same care.

Corrected figures from the source: Sem-Lex is **3,149 signs / 91,148 videos / 41 Deaf
participants**. The "~2,723 signs" figure used earlier was wrong — 2,731 is ASL Citizen.

---

## 2. Google ASL Fingerspelling (Kaggle) — gates every name and medication

### Why this one is the biggest missing capability

Twenty-six letters covers every name, place and medication — the entire long tail that no
lexicon will ever contain. The current system has **zero** single-letter entries, so it cannot
sign a patient's name. Deaf signers already fingerspell for exactly these words. A 26-class
model is small and accurate, and it makes vocabulary size stop mattering for the tail.

This one needs **no email and no negotiation** — just an acceptance click.

### Steps

1. On Kaggle, open the **Google — American Sign Language Fingerspelling Recognition**
   competition.
2. Go to the **Rules** tab → **I Understand and Accept**. (Competition data stays available
   after a competition closes; accepting the rules is what unlocks it.)
3. Open a **new notebook**. In the right-hand panel: **Add Input → Competitions →** search for
   it → attach.
4. Run this and paste me the output — it tells me the layout before I write anything.

   (An earlier version of this probe printed only `/kaggle/input/competitions  dirs=1 files=0`:
   it had a `break` that stopped it after the first directory, and the competition data sits
   several levels below that. This one walks properly and prunes instead of breaking.)

```python
import os, glob

for r in sorted(glob.glob("/kaggle/input/*")):
    print("ROOT", r)
    for dirpath, dirnames, files in os.walk(r):
        depth = dirpath[len(r):].count(os.sep)
        if depth >= 3:
            dirnames[:] = []              # prune deeper, but still print THIS level
        pad = "  " * (depth + 1)
        print(f"{pad}{os.path.basename(dirpath) or dirpath}/   "
              f"[{len(dirnames)} dirs, {len(files)} files]")
        for f in sorted(files)[:8]:
            p = os.path.join(dirpath, f)
            print(f"{pad}  {f}   {os.path.getsize(p)/1e6:.1f} MB")
        if len(files) > 8:
            print(f"{pad}  ... +{len(files)-8} more files")

# the two things that decide the architecture
import pandas as pd
for csv in glob.glob("/kaggle/input/**/*.csv", recursive=True)[:5]:
    print("\n---", csv)
    d = pd.read_csv(csv, nrows=3)
    print(d.columns.tolist())
    print(d.head(3).to_string()[:600])
```

### Two warnings

**Do not download it.** This dataset is large. Attach it in Kaggle and work in place — the same
way the 250-word corpus is used. Your laptop has ~2.4 GB free.

**It is a different problem shape from the 250-word model.** Fingerspelling is a *continuous
sequence* of letters, not one isolated sign, so the head is not a 26-way softmax over a clip —
it is sequence prediction (CTC or seq2seq) over a stream. Reusing the isolated-sign architecture
unchanged will not work, and pretending otherwise is how this turns into three wasted weeks. The
26-class framing is right about the *alphabet* being finite; it is wrong about the *decoding*.
