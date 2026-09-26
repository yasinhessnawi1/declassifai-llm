# Synthetic document generation — build spec

**Written for:** an agent working this repository in a separate terminal session, in
parallel with an ongoing re-annotation effort. You own everything under `data/synthetic/`
and the tools that produce it. You must not touch `data/gold/`, `data/slice/`, or
`docs/ANNOTATION_SPEC.md` — another session is actively writing them.

**One assumption to confirm with the project owner before you go deep:** "per spec" is read
here as *the 16 entity types in `docs/ANNOTATION_SPEC.md`*. If a different number or
standard was meant, most of this spec still holds but §5 and §8 change.

---

## 1. Why this exists

The training corpus is 32,439 documents that are really only **two templates**: an
animal-welfare tip-off interview (55%) and a dossier about a named person (45%). Surface
wording varies — 29,836 distinct skeletons — but the document *genres* do not. A model
trained on this learns two form-fillings, not Norwegian PII extraction.

Separately, the corpus's own labels are unusable for five of the sixteen types. Measured
against a 400-document adjudicated gold set, the labeller scores 0.966 relaxed F1 on seven
types and 0.26–0.55 on HEALTH_INFO, CRIMINAL_RECORD, EMPLOYMENT_INFO, ECONOMIC_STATUS and
BEHAVIORAL_PATTERN. See `docs/DATA_QUALITY.md`.

So the gap you are filling is **genre diversity with labels that are correct by
construction**. Quality first; throughput is not a goal.

---

## 2. The hardware, measured

Do not take these from documentation. They were measured on this machine on 2026-09-26.

```
Tesla V100-SXM3-32GB   compute capability 7.0 (Volta)   CUDA 12.9   driver 570.172.08
matmul 4096³ :  fp16  1.46 ms   94.4 TFLOP/s
                bf16 12.88 ms   10.7 TFLOP/s
                fp32  9.37 ms   14.7 TFLOP/s
```

Four consequences, three of them traps:

1. **`torch.cuda.is_bf16_supported()` returns `True` and it is lying to you.** Volta has no
   bf16 tensor cores; PyTorch reports emulation. bf16 measured ~9× slower than fp16 and
   slower than fp32. **Use fp16 everywhere** — `torch_dtype=torch.float16`, `fp16=true`,
   `bf16=false`. A config copied from an Ampere box will silently cost you most of the GPU.
2. **FlashAttention-2 will not run** (`sm80`–`sm90` only). Confirmed: the flash SDPA
   backend raises, mem-efficient and math backends work. Use
   `attn_implementation="sdpa"`, never `"flash_attention_2"`.
3. **bitsandbytes 4-bit does work here.** This was the main risk, since bnb historically
   gated int8 on `sm75`. Verified with bnb 0.49.2: `Linear4bit` (NF4, fp16 compute) and
   `Linear8bitLt` both run a forward pass on `sm70`. QLoRA is available to you.
4. **32 GB is a lot, so quantize only if you must.** An fp16 7–9B model is 14–18 GB and
   leaves ample room for KV cache and generation. Reach for quantization at ~13B+, and
   prefer bnb NF4 or a GPTQ build with the older CUDA kernels. **AWQ and Marlin kernels
   require `sm75`/`sm80` and will not load.** GGUF via llama.cpp is the universal fallback
   and runs fine on Volta.

Environment: `myenv/bin/python` (torch 2.5.1+cu121, transformers 5.3.0, bitsandbytes
0.49.2, peft, trl, accelerate, datasets). The venv interpreter symlink breaks whenever this
workspace is rebuilt; if `myenv/bin/python` disappears, repoint `myenv/bin/python3` at
`/home/coder/.local/bin/python3.12` and fix `home`/`executable` in `myenv/pyvenv.cfg`.
Bare `python3` is also that interpreter.

---

## 3. Choosing the model

Rank candidates by, in this order: **Norwegian fluency → instruction adherence → licence →
speed.** Speed is last on purpose.

The binding constraint is Norwegian. Most multilingual models produce Norwegian that a
native reader immediately clocks as translated — Danish-inflected vocabulary, English
syntax, wrong register for officialese. A document that reads wrong is worse than no
document, because the model you train on it learns to expect text that will never arrive.

Evaluate rather than assume. Worth screening: the Norwegian-specific work from the national
language-model effort (NorMistral / NorBLOOM / NB-family), Nordic-pretrained models such as
Viking and Poro, and the strong general multilingual families (Qwen 2.5/3, Llama 3.x,
Mistral, Gemma). Search Hugging Face directly for current Norwegian instruct fine-tunes —
this list will be stale.

**Licence matters and is a hard gate.** You are generating data to train another model.
Confirm the licence permits that, including any clause restricting use of outputs to train
competing models. Record the licence for each candidate in your report.

**Screening protocol.** Take 8–10 prompts spanning the genres in §4. For each candidate,
generate, then score on:
- Norwegian correctness and register (is this how a Norwegian agency actually writes?)
- Bokmål/Nynorsk consistency within a document
- No English leakage, no `[placeholder]` artifacts, no instruction echo
- Does it follow a structured field format without drifting?
- Plausible internal consistency (dates ordered, one person's details not contradicting)

Report the comparison with examples. Pick on evidence.

---

## 4. Document genres to produce

Everything except the two existing templates. Target Norwegian public-sector and
adjacent-institution documents, since that is the deployment domain. A reasonable spread:

| Domain | Genres |
|---|---|
| Health | GP referral, hospital discharge summary, occupational-health assessment, psychologist's note |
| Justice | police report, prosecution decision, court judgment summary, restraining-order decision |
| Welfare | NAV benefit decision, sickness-benefit follow-up, debt-counselling record |
| Tax & finance | tax assessment letter, `inkasso` notice, bank AML enquiry |
| Education | PPT assessment, school incident report, admission decision |
| Child welfare | `barnevern` concern report, care-plan review |
| Employment | employment contract, dismissal letter, whistleblowing report, HR grievance |
| Housing | municipal housing application, tenancy dispute, planning objection |
| Immigration | UDI correspondence, residence-permit decision |
| Veterinary | clinical record, inspection order (bridges to the existing domain) |

Vary the *structure*, not just the words: field-header forms, running prose, numbered legal
findings, letters with salutations, tabular summaries, bulleted meeting minutes. Vary length
from ~400 to ~4,000 characters — the existing corpus is bunched around 2,455 median.

Mix Bokmål and Nynorsk deliberately; both appear in real Norwegian government text and the
current corpus is Bokmål-heavy.

---

## 5. What must be in each document

Exercise all 16 types from `docs/ANNOTATION_SPEC.md`. Read that file in full — it defines
each type and 23 boundary rules, and it is the authority for what counts as a span.

Identifier realism, Norwegian-specific:
- `fødselsnummer` — 11 digits, DDMMYY + individual number + two check digits. Generate with
  a valid mod-11 checksum *or* deliberately invalid, but pick one policy and record it. A
  detector trained only on checksum-valid numbers may fail on typo'd real ones.
- `D-nummer` — as above with the day field offset by 40.
- `organisasjonsnummer` — 9 digits, mod-11 check.
- Postal codes — 4 digits, and use real place pairings; `0580 Oslo` is fine, `0580 Bergen`
  teaches a wrong association.
- Phone — 8 digits, `+47` prefix optional, realistic prefixes.
- Vehicle registration — two letters plus five digits (`DK 45778`). These are GOV_ID per
  B20 and must be tagged as their own span.
- Email, addresses with house numbers and letter suffixes (`Fjellveien 12B`).

**Never a real person.** Compose names from a name-frequency list; then check generated
full names against a list of Norwegian public figures and reject collisions. The documents
allege crimes, illness and sexual orientation — attaching that to a real name is the one
failure here with consequences outside the project. Do not skip this check.

Force the rare types in deliberately. In the existing corpus SEXUAL_ORIENTATION,
POLITICAL_CASE, ECONOMIC_STATUS and BEHAVIORAL_PATTERN are all sparse, and a generator left
to itself will reproduce that sparsity.

---

## 6. The decision that determines whether this works

**Do not generate free text and then annotate it.** That reproduces exactly the failure
this project is recovering from: a model writes prose, another model guesses the spans, and
the labels are wrong in the same judgement-heavy types that are already broken.

Generate so that **the labels are known by construction**:

1. A structured record is sampled first — the people, identifiers, conditions, offences,
   employment, relationships — as typed data.
2. The LLM is asked to write a document *realising* that record in a given genre, with an
   instruction to use the supplied values verbatim.
3. The labels come from the record, and are located in the output by exact string search.
4. **Any value that does not appear verbatim in the generated text causes the document to
   be discarded or regenerated.** This is the gate that makes the approach sound. If the
   model paraphrased `Fjellveien 12B` into `Fjellveien 12 B`, the label is wrong and the
   document is worthless.

The narrative types (HEALTH_INFO, CRIMINAL_RECORD, BEHAVIORAL_PATTERN, ECONOMIC_STATUS,
EMPLOYMENT_INFO) are harder, because their spans are clauses rather than values. Two
workable options — evaluate both and report which you chose:
- **Seeded clause**: supply the clause itself (`lider av type 2 diabetes`) and require it
  verbatim, then label it by search. Exact, but risks stilted text and low span diversity.
- **Marked generation**: ask the model to emit lightweight inline markers around the
  clause, then strip the markers and record the resulting offsets. Higher diversity, but
  you must verify the marker discipline holds and discard documents where it doesn't.

Whichever you pick, the verbatim invariant is non-negotiable — `tools/validate_labels.py`
enforces it and must exit 0 on every file you produce.

---

## 7. Validation gates

No document enters `data/synthetic/` until it passes all of these. Build them as a script,
not as a checklist you run by eye.

1. `python3 tools/validate_labels.py <file>` exits 0 — every span verbatim, types in
   schema, no empty records.
2. Every planned value from the source record is present and located. No silent drops.
3. No real-person name collision.
4. Identifier format checks pass (checksums where you chose to make them valid).
5. Genre and length distribution match the plan, not a collapsed mode.
6. **Diversity**: skeleton-hash the output the way `tools/sample_gold.py` does — digits to
   `#`, capitalised tokens to `N` — and confirm you are not producing the same document
   repeatedly. The existing corpus has 29,836 distinct skeletons across 32,439 documents;
   fall far short of that ratio and you have built a third template rather than fixing the
   problem.
7. Norwegian quality spot-check on a sample, by reading them.

---

## 8. Proving the documents are any good

Generation quality is not self-evident, so measure it two ways.

**Detection round-trip.** Run a detector over the generated documents and score its output
against the known labels using `tools/score_agreement.py` (relaxed F1 is the project's
primary metric; `--keys` lets you compare two label sets). Interpretation:
- High relaxed F1 means the documents are natural enough that a detector finds what is
  there. Good.
- Low F1 means one of two things, and you must determine which: the documents are
  unnatural, or your labels are wrong. Read failures rather than tuning the number.
- Suspiciously perfect F1 is also a warning — it usually means the PII is sitting in
  predictable slots and the documents are template-shaped.

**Distribution comparison against gold.** The 400-document gold set in `data/gold/` is the
project's reference for what correct annotation looks like. Compare your synthetic output's
per-type spans-per-document against it, split by genre. You should not match it exactly —
new genres have different profiles, that is the point — but a type that is 10× the gold
rate or absent entirely is a signal to inspect.

One caution learned the hard way in the annotation effort: **a keyword or regex count over
documents is not evidence about spans.** Three separate rules in this project were derived
from such counts and all three were wrong. Read the matches before concluding anything.

---

## 9. Deliverables

- `docs/MODEL_SELECTION.md` — candidates screened, licences, measurements, sample outputs,
  the choice and why. Include what you rejected.
- `tools/generate_documents.py` — the generator, with the record sampling, the prompt
  construction and the validation gates. Repo style: module docstring explaining *why*,
  Google-style arg docs, no decorative comments.
- `data/synthetic/` — the documents, in the same `{id, text_input, output}` JSONL shape as
  `data/gold/batch_*_gold.jsonl`, batched at a few hundred per file.
- A short report on the detection round-trip with numbers.

Start small. Produce 50 documents across 5 genres, run every gate, and report before
scaling. A generator that runs overnight and produces 10,000 unusable documents is the
expensive failure mode here.

---

## 10. Ground rules

- `myenv/bin/python` for anything touching torch; `python3` otherwise.
- The Write/Read/Edit tools time out constantly in this workspace. Work through Bash —
  `cat`, `sed -n`, heredocs, short scripts.
- Do not modify `docs/ANNOTATION_SPEC.md`, `data/gold/`, or `data/slice/`. If you find a
  contradiction in the spec — and there are some — write it in your report; another session
  is resolving them.
- Commit your own work; do not commit anything under those paths.
- Report measurements rather than impressions, and say plainly when something did not work.
