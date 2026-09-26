# Model selection — synthetic Norwegian PII document generator

**Owner of this document:** the model-selection workstream (see `docs/PROJECT_SPEC_V2.md`,
`docs/SYNTHETIC_DATA_SPEC.md` §2/§3). Screened 2026-09-26 on the project's single Tesla
V100-SXM3-32GB (sm70, CUDA 12.9, driver 570.172.08), `myenv/bin/python` (torch 2.5.1+cu121,
transformers 5.3.0, bitsandbytes 0.49.2). All screening artifacts live under
`data/synthetic/screening/` (`prompts.py`, `run_screening.py`, `score_outputs.py`, raw
outputs in `raw/<slug>/`, metrics in `logs/`).

**Choice: `Qwen/Qwen3.5-9B`**, fp16, `attn_implementation="sdpa"`, thinking mode disabled.
Runner-up and fallback: `NbAiLab/nb-notram-llama-3.1-8b-instruct`.

---

## 1. Method

Ranked by the order `SYNTHETIC_DATA_SPEC.md` §3 specifies — Norwegian fluency →
instruction adherence → licence → speed — but licence was checked early since it is a hard
gate and disqualifies a candidate regardless of quality.

**11 prompts** (`data/synthetic/screening/prompts.py`), each a structured record (names,
`fødselsnummer`, address with house-letter suffix, postal code + real place, phone, dates,
org number) plus 2 judgement clauses (health, criminal, economic, employment, immigration,
child-welfare, veterinary), with an instruction to reproduce every value and clause
**verbatim**. Genres: GP referral, police report, NAV benefit decision, dismissal
letter/HR grievance, UDI residence-permit decision, `barnevern` concern report, tax/inkasso
letter, veterinary inspection order — 8 in "seeded clause" form (P01–P08) and 3 in "marked
generation" form (P09–P11, model wraps its own self-written clause in `⟦TYPE: ...⟦`
markers). 7 prompts are Bokmål, 4 are Nynorsk (≥2 required).

Sampling: temperature 0.75, top_p 0.9, max_new_tokens 650, each model's own chat template
via `tokenizer.apply_chat_template()`. **Measured automatically**: exact-substring
verbatim-inclusion rate for values and clauses, marker discipline, crude English/placeholder/
echo regexes, tokens/sec, peak VRAM. **Measured by reading**: register, Bokmål/Nynorsk
consistency, anglicisms/Danish-isms, whether markers were genuinely attempted.

The crude regex checks under-count real behaviour in at least one documented way (§5) — per
`SYNTHETIC_DATA_SPEC.md` §8's rule that "a keyword or regex count is not evidence about
spans," every clause/marker miss below was read before being counted as a real failure.

## 2. Candidates and licences

| Candidate | Params | Licence | Output-use-for-training clause |
|---|--:|---|---|
| `Qwen/Qwen2.5-7B-Instruct` | 7.6B | Apache-2.0 | No restriction. |
| `Qwen/Qwen3.5-9B` | 9.7B | Apache-2.0 | No restriction. |
| `ltg/normistral-7b-warm-instruct` | 7.2B | Apache-2.0 | No restriction. |
| `NbAiLab/nb-notram-llama-3.1-8b-instruct` | 8.0B | Llama 3.1 Community License (inherited from base `meta-llama/Llama-3.1-8B-Instruct`) | Permitted since Llama 3.1 (unlike Llama 2/3.0). Condition: if outputs are used to "create, train, fine-tune, or otherwise improve" an AI model that is itself distributed, that model's name must start with "Llama". Also carries Meta's >700M-MAU commercial-license trigger (irrelevant here) and the AUP. A naming obligation on anything we publish, not a training prohibition. |
| `NbAiLab/borealis-open-12b` | 12.2B | Gemma Terms of Use (inherited from `google/gemma-3-12b-it`) | Gemma "Outputs" are explicitly **not** deemed "Model Derivatives"; a downstream model only inherits Gemma's licence if it is trained to reproduce Gemma's own capabilities (distillation), which a PII-detector/NER model does not do. Licence itself is workable. **Disqualified on a technical, not licence, ground — see §4.** |

`ltg/normistral-11b-warm` (Mistral-Nemo based, apache-2.0) was considered but **not
screened**: its own model card states it "is not finetuned to follow instructions" — it is
a base LM, not an instruct model, and this whole protocol depends on chat-template
instruction-following. Screening a base model here would have meant designing a separate
few-shot harness for one candidate, which was not worth the time given four working instruct
candidates already covered the Norwegian-native + multilingual spread. `Viking`/`Poro`
(Finnish-centric, weak Norwegian per their own cards) and `NorwAI-Mistral/Llama` (superseded
by the same LTG group's NorMistral line) were not screened for the same reason: time-boxed
to 4-6 realistic candidates per the brief, and these were the least promising of the
plausible set found by searching the Hub.

## 3. Measurements

Automated (exact substring / regex; `n=11` prompts, 8 seeded-clause + 3 marked, per
candidate):

| Model | Value verbatim % | Clause verbatim % (seeded, n=8×2) | Marker discipline % (marked, n=3×2) | Eng./Danish tells | Placeholders | tok/s (fp16, sdpa) | Peak VRAM |
|---|--:|--:|--:|--:|--:|--:|--:|
| Qwen2.5-7B-Instruct | 92% | 56% | 33%† | 0 auto-flag, Danish-isms on read | 0 | 32.7 | 15.4 GB |
| NorMistral-7b-warm-instruct | 61% | 12% | 0% | 0 | 3 files | 30.1 | 14.7 GB |
| nb-notram-llama-3.1-8b-instruct | 90% | 44% | 67% | 0 | 0 | 30.6 | 16.3 GB |
| **Qwen3.5-9B** | **93%** | **94%** | 33% | 0 | 1 file (design flaw, see §5) | 20.5 | 18.1 GB |
| Borealis-open-12b | — | — | — | — | — | — | **rejected before measurement, §4** |

† Qwen2.5's raw marker score understates it — see §5.1: it attempted marking on 5 of 6
clauses but closed 4 of them with `⟧` instead of the (deliberately unusual) `⟦` I asked it
to repeat, so the strict regex only credited 2/6.

## 4. Rejected: `NbAiLab/borealis-open-12b` (Gemma 3, fp16 numerical failure)

This is the most important negative result. Borealis-open-12b (Gemma-3-12b-it fine-tuned
for Norwegian, the most current NB-specific release found, May 2026) produced a
`device-side assert triggered ... probability tensor contains ... nan` CUDA error on the
**first** generation call, in every attempted configuration:

```
../aten/src/ATen/native/cuda/TensorCompare.cu:110: _assert_async_cuda_kernel: ...
Assertion `probability tensor contains either inf, nan or element < 0` failed
```

Isolated with a direct forward pass (no sampling, no `generate()`): `attn_implementation="sdpa"`
and `"eager"` both give `logits.isnan().any() == True` in fp16 on this GPU, on a plain
one-sentence prompt. This is Gemma 3's known fp16 overflow behaviour — its residual-stream/
logit magnitudes exceed fp16's range and it needs bf16. But `SYNTHETIC_DATA_SPEC.md` §2 is
explicit that bf16 is emulated on this Volta card and measured ~9x slower than fp16
(12.88ms vs 1.46ms per 4096³ matmul) — running Borealis at a usable precision would mean
giving up almost an order of magnitude of throughput for the one model that also carries the
most complex licence chain (Gemma ToU) of the set. **Rejected on a hardware/dtype
incompatibility, not on quality** — its Norwegian is very likely excellent (it is the
national library's own Norwegian-tuned release) but that could not be measured within the
fp16-only constraint this project is bound to.

## 5. What the reading pass changed or confirmed

### 5.1 Marker glyph substitution (methodology finding, applies to future marked-generation work)

I asked models to wrap self-written clauses in `⟦TYPE: ...⟦` — the **same** glyph on both
sides, deliberately, to make the marker easy to `grep` for uniquely. Qwen2.5-7B ignored this
and closed with the conventional-looking `⟧` (U+27E7) instead, e.g.:

```
⟦ECONOMIC_STATUS: Personens økonomiske situasjon er tidsvis gammel, da han har vært uten
arbeid siden desember 2025. ... har brukt opptjente pensjonseinkomster som
hovedfinansiering. ...⟧
```

This is a generalizable lesson for `tools/generate_documents.py`: **use a conventional
matching open/close delimiter pair (`⟦`/`⟧`), not a repeated single glyph** — models
default to symmetric-bracket habits from training data and will "fix" an unusual scheme
silently, which breaks a naive single-glyph regex. Qwen3.5-9B, by contrast, either used the
exact symmetric glyph I asked for or used no marker at all (binary, not partial) — it never
substituted a different closing character.

### 5.2 Verbatim clause reproduction is genuinely hard for every model, including the winner

Even the best model (Qwen3.5-9B, 94% clause rate) missed clauses by paraphrase, not
omission — e.g. Qwen2.5-7B turned `"har diagnosen bipolar lidelse type II"` into `"har ...
symptomer til bipolar lidelse type II"`, and NorMistral turned `"er registrert med aktiv
arbeidskontrakt hos Nord-Norsk Fiskeindustri AS"` into `"er registrert med ein aktiv
arbeidskontrakt hos Nord-Norsk Fiskeindustri AS"` (inserted "ein"). This is exactly the
failure mode `SYNTHETIC_DATA_SPEC.md` §6 warns the seeded-clause approach risks, and it
confirms the generator's regenerate-on-verbatim-failure gate (`tools/validate_labels.py`)
is not optional even for the best-scoring model — budget for retries.

### 5.3 One placeholder hit on the winner was a prompt design flaw, not a model flaw

Qwen3.5-9B left `[Adresse for mottaker]` / `[Postnummer og sted]` in the dismissal-letter
prompt (P04). Reading it: the prompt supplied one ambiguous `address`/`postal` pair and the
model correctly used it for the **employer's** letterhead, then honestly placeholdered the
**employee's** home address, which the prompt never supplied. This is a screening-prompt
ambiguity (fixed for the real generator by giving every party in a genre its own explicit
address field), not evidence the model fabricates or drops given values.

### 5.4 Register and Bokmål/Nynorsk consistency (read, not automated)

- **Qwen2.5-7B-Instruct defaults to Bokmål even when explicitly told to write Nynorsk and
  told not to.** P05 (UDI decision, instructed Nynorsk) came back in Bokmål throughout
  ("Til:", "Dette betyr at hun er anstilt", "arbeidsoppholdsløyveprogrammet") with visible
  Danish-isms elsewhere in the set (`medicinsk`, `haft`, `mellem` for `medisinsk`/`hatt`/
  `mellom` — real Danish spellings, not Norwegian). This is a hard fail against the spec's
  binding constraint ("the binding constraint is Norwegian").
- **NorMistral-7b-warm-instruct** writes the most idiomatic, native-sounding Nynorsk of the
  set when it stays on task ("Vi vonar denne meldinga finn deg vel... gler oss til å sjå kva
  du kjem til å oppnå") — but see §5.5, it frequently doesn't stay on task.
- **nb-notram-llama-3.1-8b-instruct** produced correct, idiomatic Nynorsk grammar
  (`eg`, `blei`, `ikkje`, `dømd`, `førarrett`, `meiner`) with no Bokmål leakage in the
  Nynorsk prompts tested.
- **Qwen3.5-9B** also produced correct Nynorsk register and morphology (`påleggjer`,
  `forsvarleg`, `sidan`, `veker`) and — unlike Qwen2.5-7B — did not collapse to Bokmål on
  any of its 4 Nynorsk prompts. This is a real generational improvement between Qwen2.5 and
  Qwen3.5 on Norwegian, not just a benchmark artifact.

### 5.5 NorMistral-7b-warm-instruct: fluent but structurally unreliable

Its low value/clause rates are not a language-quality problem — they are an
instruction-following/reliability problem. Two concrete failures:
- **P08 (veterinary inspection order)** never filled in a single supplied value. It wrote
  the entire document with bracket placeholders (`[Eigar]`, `[Organisasjonsnummer]`,
  `[Dato]`, ...) despite an explicit "no placeholders" instruction, and then **repeated the
  same near-identical letter three times** until it hit the 650-token budget.
- **P07 (inkasso letter)** dropped the `fødselsnummer`, address, postal code and case
  number entirely, writing a generic personal letter instead of the requested field-header
  format, and shortened `INK-2026-771402` to `2026-771402`.

This is a genuine reliability gap that would make NorMistral expensive to use in production
even though its language is often the most native-sounding of the set: every document would
need the regeneration gate to catch collapse-into-template, and the retry rate would likely
be high.

### 5.6 nb-notram-llama-3.1-8b-instruct: best marker discipline, but invents unplanned detail

Marker discipline (67%, 2 of 3 marked prompts fully compliant) was the best of any
candidate, and the markers it wrote were substantive, not filler:

```
⟦HEALTH: Hun bruker daglig vitamin D-tilskudd og har nylig startet med Omega-3-kapsler
etter en rutinemessig blodprøve viste lett forhøyede triglyserider⟦
```

But on the one marked prompt it failed (P10, police report), it didn't just skip the
markers — it invented an entire unplanned criminal history in plain prose (specific years,
specific convictions, a fabricated officer name "Lars Hansen" never in the record). This is
exactly the "unplanned PII" failure mode `SYNTHETIC_DATA_SPEC.md` §3 warns generation must be
swept for — a live illustration of why the mechanical unplanned-PII sweep is not optional.

## 6. Sample excerpts

**Qwen3.5-9B**, P03 (NAV decision, Bokmål, seeded clause) — both clauses reproduced
character-for-character:

> Du **har en samlet gjeld på over 480 000 kroner**, noe som indikerer betydelig økonomisk
> belastning. Videre er det dokumentert at du **mottar for tiden supplerende sosialhjelp fra
> kommunen**.

**Qwen3.5-9B**, P08 (veterinary inspection order, Nynorsk, seeded clause) — correct Nynorsk
register, both clauses verbatim:

> Grunngjevinga for vedtaket er at du **har gjentekne avvik på forsvarleg husdyrhald sidan
> 2023**. ... Vidare vart det konstatert at du **fekk pålegg om utbetring innan fire veker
> etter forrige tilsyn**.

**nb-notram-llama-3.1-8b-instruct**, P09 (GP referral, marked generation) — correct marker
usage with a substantive, non-generic clause:

> ⟦HEALTH: Hun er en engstelig person som ofte bekymrer seg for helsen sin⟦ ... ⟦HEALTH: Hun
> bruker daglig vitamin D-tilskudd og har nylig startet med Omega-3-kapsler etter en
> rutinemessig blodprøve viste lett forhøyede triglyserider⟦

**nb-notram-llama-3.1-8b-instruct**, P10 (police report, Nynorsk) — idiomatic Nynorsk, but
illustrates the unplanned-detail risk (§5.6):

> Mistenkt: Vetle Skogen Aas, født 01.01.1990, har tidlegare vore involvert i kriminelle
> handlingar. I 2015 blei han dømd for ran og i 2018 for skadeverk.

## 7. Decision

**`Qwen/Qwen3.5-9B`**, fp16, `attn_implementation="sdpa"`, thinking disabled.

Reasons, in the spec's stated priority order:
1. **Norwegian fluency**: correct Nynorsk grammar and register on all 4 Nynorsk prompts,
   no Bokmål leakage, no Danish-isms observed on reading — a clear step up from Qwen2.5-7B
   on the same axis.
2. **Instruction adherence**: highest measured value-verbatim (93%) and by far the highest
   clause-verbatim rate (94%, next best is 67% for llama3.1-nb's marker rate on a different
   metric) of any working candidate. No template-collapse or repetition failures like
   NorMistral's.
3. **Licence**: Apache-2.0, no restriction on using outputs to train another model, no
   naming or distribution obligation. Cleanest of the set.
4. **Speed**: slowest of the four working candidates (20.5 tok/s vs 30-33 tok/s for the
   7-8B models) and highest VRAM (18.1 GB peak) because it is a larger, hybrid
   linear-attention/full-attention architecture — but still comfortably fp16 on a 32 GB
   V100 with no quantization needed, and speed was explicitly the lowest-priority criterion.

**Runner-up / fallback: `NbAiLab/nb-notram-llama-3.1-8b-instruct`.** If Qwen3.5-9B's
throughput becomes a real bottleneck at scale, this is the fallback: 90% value-verbatim,
best marker discipline (67%), genuinely good Nynorsk, ~50% faster generation, smaller VRAM
footprint. Its only real cost is the Llama 3.1 licence's "Llama"-prefix naming condition on
any distributed model trained using its outputs, and a stronger tendency to add unplanned
narrative detail (§5.6), which raises the importance of the mechanical unplanned-PII sweep.

**Rejected**: `NbAiLab/borealis-open-12b` (fp16 NaN on this hardware, §4);
`Qwen/Qwen2.5-7B-Instruct` (Bokmål/Nynorsk collapse, Danish-isms, weak clause fidelity);
`ltg/normistral-7b-warm-instruct` (best raw Nynorsk fluency in the set, but unreliable —
template collapse and value drops make it expensive to use under the verbatim gate);
`ltg/normistral-11b-warm` (base model, not instruction-tuned, not screened).

## 8. Recommended generation configuration

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "Qwen/Qwen3.5-9B"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(
    model_id, dtype=torch.float16, attn_implementation="sdpa",
).to("cuda")
model.eval()

messages = [{"role": "user", "content": "<genre + record + verbatim instruction>"}]
input_ids = tok.apply_chat_template(
    messages, add_generation_prompt=True, return_tensors="pt",
    return_dict=False, enable_thinking=False,   # REQUIRED, see below
).to("cuda")

with torch.no_grad():
    out = model.generate(
        input_ids, max_new_tokens=700, do_sample=True,
        temperature=0.75, top_p=0.9,
        pad_token_id=tok.pad_token_id or tok.eos_token_id,
    )
text = tok.decode(out[0, input_ids.shape[1]:], skip_special_tokens=True)
```

**Chat-template quirk — thinking mode must be disabled.** Qwen3.5-9B's
`chat_template.jinja` defaults to opening an unclosed `<think>\n` block unless
`enable_thinking=False` is passed to `apply_chat_template()` (confirmed by reading the
template: `{%- if enable_thinking is defined and enable_thinking is false -%}` emits a
pre-closed empty `<think>\n\n</think>\n\n`, the `else` branch emits a bare open `<think>\n`
and lets the model fill it in). Verified live: with the default (no `enable_thinking` kwarg,
400-token budget), the model spent the entire budget on an English "Thinking Process:"
preamble (numbered analysis of the prompt's constraints) and **never reached the Norwegian
document** — see `data/synthetic/screening/raw/qwen3.5-9b-thinking-on/P01_gp_referral_nb.txt`.
With `enable_thinking=False` the model goes straight to the Norwegian document.

Also note: `apply_chat_template(..., return_tensors="pt")` alone returns a `BatchEncoding`
in transformers 5.3.0, not a bare tensor — pass `return_dict=False` explicitly or index
`["input_ids"]`, otherwise `model.generate()` fails with `AttributeError` on `.shape`.

**Seeded-clause vs marked generation, for this model**: use **seeded clause**, not marked
generation, for production. Measured 94% clause-verbatim rate for seeded clauses against
33% marker-discipline rate for marked generation (2 of 3 marked prompts had zero marker
attempts at all, not partial compliance — see §5.4). Marked generation would need either a
stronger delimiter-compliance prompt (few-shot example of the marker in use, tried neither
here for time reasons) or a fallback to seeded-clause on marker-validation failure; seeded
clause plus the mandatory verbatim-regeneration gate is the simpler, already-measured path.

## 9. Measured throughput and memory (fp16, sdpa, this V100)

| Model | avg tok/s | peak VRAM | load time |
|---|--:|--:|--:|
| Qwen2.5-7B-Instruct | 32.7 | 15.4 GB | 121 s (cold cache) |
| NorMistral-7b-warm-instruct | 30.1 | 14.7 GB | 36 s |
| nb-notram-llama-3.1-8b-instruct | 30.6 | 16.3 GB | 19 s |
| **Qwen3.5-9B** | **20.5** | **18.1 GB** | 22 s |

No quantization was used or needed for any candidate (all ≤12B fp16 fit well under 32 GB
per `SYNTHETIC_DATA_SPEC.md` §2's "quantize only at ~13B+" guidance). GPU was released
(`nvidia-smi` confirmed 0 MiB used) after each run; this session was the only GPU user
throughout.
