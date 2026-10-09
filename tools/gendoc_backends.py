"""Pluggable generation backends: a deterministic mock and a transformers-based one.

The model to use for real generation has not been chosen yet (that is a
separate, parallel workstream -- see `docs/MODEL_SELECTION.md`, not yet
written). This module defines the backend contract both a screening result and
this generator's own tests can rely on, and implements it twice:

* `MockBackend` -- a deterministic template filler with no ML dependency at
  all. It exists so every gate in this pipeline (verbatim presence, name
  collision, checksum consistency, diversity, unplanned-PII sweep) can be
  exercised and proven to catch injected failures without a GPU or a chosen
  model -- see `tools/check_generator_gates.py`, which drives every gate through
  it. Its G11 audit reports the two cue phrases `MOCK_ELABORATION_CUE` and
  `MOCK_FRAMING_CUE`, and applies a small lexical version of the two judgements the
  real auditor makes about meaning: a special-category word in the same sentence as a
  relevance cue is a framing finding, and a denial of a planted clause's topic (or an
  explain-away after the clause itself) is a contradiction finding. It is a stand-in
  that exercises the plumbing, not a measurement of what the model will find.
* `HFBackend` -- the real backend, used for every pilot and smoke run with the
  model `docs/MODEL_SELECTION.md` settles on (`Qwen/Qwen3.5-9B`): fp16, sdpa
  attention, chat template, batched generation, and a hook to disable
  Qwen3-style "thinking" via `enable_thinking=False`, probed once at
  construction rather than assumed. `temperature=0` switches it to greedy
  decoding, which is what the G11 content audit needs -- the same document must
  audit the same way every time, and passing a zero temperature to a sampling
  `generate()` divides by zero in the logits warper. `torch`/`transformers` are
  imported lazily inside `HFBackend.__init__` so importing this module, or
  running with `--backend mock`, never requires them.

A sectioned document's prompt (`generate_documents.build_section_prompt`) carries
`SECTION|k|n|kind`, `HEADING|...` and only that section's items in its manifest.
The mock answers one section per call: the heading, then the section's items and
a couple of neutral sentences no other section of the same document uses, so a
joined mock document passes the cross-section repetition gate unless a test
injects a repeat.

Both backends implement the same method:

    generate(self, prompts: List[str], *, max_new_tokens: int = 900,
             temperature: float = 0.9, seed: Optional[int] = None) -> List[str]

one output string per input prompt, in order, and set `last_finished` to one
bool per prompt saying whether generation ended on end-of-sequence rather than
on the token budget (a budget stop is a truncated document).

Prompts carry a machine-readable manifest after `MANIFEST_SENTINEL`. The mock
backend reads only the manifest; `HFBackend` cuts it off before the chat
template is applied. In the first pilot the manifest was part of what the
model read, and its `CLAUSE_SEEDED|HEALTH|...` lines taught the model to label
clauses with their category.
"""

from __future__ import annotations

import abc
import random
import re
from typing import List, Optional

import gendoc_genres as genres_mod


MANIFEST_SENTINEL = "<<<MANIFEST>>>"
DRAFT_OPEN = "<<<UTKAST>>>"
DRAFT_CLOSE = "<<<SLUTT PÅ UTKAST>>>"


def model_visible(prompt: str) -> str:
    """Return the part of a prompt the model sees (everything before the manifest)."""
    return prompt.split("\n" + MANIFEST_SENTINEL, 1)[0]


class GenerationBackend(abc.ABC):
    """Contract every generation backend implements."""

    last_finished: List[bool] = []

    @abc.abstractmethod
    def generate(
        self, prompts: List[str], *, max_new_tokens: int = 900,
        temperature: float = 0.9, seed: Optional[int] = None,
    ) -> List[str]:
        """Generate one document per prompt.

        Args:
            prompts: Fully-built prompts, one per document to generate.
            max_new_tokens: Generation length cap.
            temperature: Sampling temperature.
            seed: Seed for this call's sampling, for reproducibility.

        Returns:
            List of generated document strings, same length and order as `prompts`.
        """
        raise NotImplementedError


_MANIFEST_LINE_RE = re.compile(
    r"^(VALUE|CLAUSE_SEEDED|CLAUSE_MARKED|NEGATIVE|SEED|META|REPAIR|MISSING|AUDIT|AUDIT_REPAIR|REMOVE|KEEP"
    r"|SECTION|HEADING|LAST|CLAUSE)\|(.*)$"
)

# Sentinels the audit prompt wraps the document in; duplicated from
# `gendoc_audit` so this module keeps no import of it and stays the leaf
# both the generator and the audit module depend on.
AUDIT_OPEN = "<<<DOKUMENT>>>"
AUDIT_CLOSE = "<<<SLUTT PÅ DOKUMENT>>>"

# What `MockBackend` treats as a sensitive elaboration and as a framing
# violation. The mock has no language model, so G11 needs a deterministic
# trigger the injected-failure harness can plant: a sentence carrying
# `MOCK_ELABORATION_CUE` is reported as unlabelled sensitive content and one
# carrying `MOCK_FRAMING_CUE` as sensitive framing. No generated Norwegian
# contains either, so a clean mock document audits clean.
MOCK_ELABORATION_CUE = "og har difor eit vedvarande rusproblem"
MOCK_FRAMING_CUE = "relevant for etterforskningen"

# The mock's stand-in for the auditor's Task B: a sentence is a framing finding when it
# names a special category and says it bears on suspicion, risk, credibility or an
# assessment. A health fact that justifies treatment or support is not one.
_MOCK_SPECIAL_RE = re.compile(
    r"\b(?:senterpartiet|fremskrittspartiet|arbeiderpartiet|høyre|partiet|politisk\w*|innvandring\w*|"
    r"religi\w*|menighet\w*|kirke\w*|moské\w*|muslim\w*|kristendom\w*|fagforening\w*|fagorganis\w*|"
    r"tillitsvalgt|homofil\w*|lesbisk\w*|seksuell\w*|etnisk\w*|romani|samisk|asyl\w*|oppholdsstatus|"
    r"diagnos\w*|depresjon\w*|angst\w*|antidepressiva|medisin\w*|sykdom\w*|sjukdom\w*|"
    r"funksjonsnedsett\w*|helseproblem\w*)\b", re.IGNORECASE)
_MOCK_RELEVANCE_RE = re.compile(
    r"relevant for|av betydning for|tyder på|øker (?:risikoen|faren)|gir grunn til|taler for|"
    r"styrker mistanken|svekker troverdigheten|betydning for vurderingen|"
    r"vurdering av (?:risiko|troverdighet|sikkerhet)|helhetsvurderingen|kan presses",
    re.IGNORECASE)
_MOCK_NEGATED_RE = re.compile(r"\b(?:ikke|ikkje|ingen|uten|utan)\b", re.IGNORECASE)
_MOCK_SUPPORT_RE = re.compile(r"behandling|tilrettelegg|arbeidsevne|ytelse|støtte|oppfølging", re.IGNORECASE)

# Task C: a denial about the topic of a planted clause, or an explain-away after the clause.
# "ingen direkte samband med ..." and "ingen tvil om ..." are not denials of a fact.
_MOCK_DENIAL_RE = re.compile(
    r"\b(?:foreligger|finst|finnes|er|har|ligg|ligger)\s+(?:det\s+)?(?:ingen|inga)\b"
    r"(?!\s+(?:direkte\s+)?(?:samband|forbindelse|tilknyt\w*|tvil|nye|ytterlegare|ytterligere))|"
    r"\bingen\s+(?:registrerte|kjente|tidlegare|tidligere)\b|"
    r"\b(?:ikke|ikkje)\s+(?:registrert|kjent|dømt|dømd|straffet|diagnostisert)\b", re.IGNORECASE)
_MOCK_EXPLAIN_AWAY_RE = re.compile(
    r"\bmen\s+(?:denne|dette|det|dei|de)\s+(?:finst|finnes|er|har|ligg|ligger|vart|ble)?\s*(?:ikke|ikkje)\b|"
    r"\buten\s+at\s+(?:dette|det)\s+er\s+(?:dokumentert|bekreftet)|"
    r"\bkan\s+(?:ikke|ikkje)\s+(?:bekreftes|stadfestast|stadfestes)|\bstemmer\s+(?:ikke|ikkje)\b|"
    r"\ber\s+uklart\s+om\b|\b(?:ikke|ikkje)\s+(?:i|frå|fra)\s+(?:oppgjeve|oppgitt)\s+register",
    re.IGNORECASE)
_MOCK_TOPIC_STEMS = {
    "CRIMINAL": re.compile(r"\b(?:straff\w*|dømt|dømd|siktel\w*|sikta|anmeld\w*|kriminell\w*|lovbrudd|politisak\w*)", re.I),
    "HEALTH": re.compile(r"\b(?:diagnos\w*|sjukdom\w*|sykdom\w*|helseproblem\w*|lidelse\w*|liding\w*)", re.I),
    "MEDICATION": re.compile(r"\b(?:medisin\w*|medikament\w*|legemiddel\w*)", re.I),
    "DISABILITY": re.compile(r"\b(?:funksjonsned\w*|uføre\w*|hemming|hemma)", re.I),
    "FINANCIAL": re.compile(r"\b(?:gjeld(?:en|a)?|lån\w*|betalingsanmerk\w*|betalingsmerk\w*|inkasso\w*)\b", re.I),
    "ECONOMIC_STATUS": re.compile(r"\bøkonomi\w*", re.I),
    "BEHAVIORAL_PATTERN": re.compile(r"\b(?:atferd|åtferd|adferd|oppførsel|framferd)\w*", re.I),
    "FAMILY_RELATION": re.compile(r"\b(?:ektefelle\w*|samboer\w*|sambuar\w*)", re.I),
    "POLITICAL": re.compile(r"\b(?:politisk\w*|parti\w*)", re.I),
    "RELIGIOUS_BELIEF": re.compile(r"\b(?:religi\w*|livssyn)", re.I),
    "TRADE_UNION": re.compile(r"\b(?:fagforen\w*|fagorganis\w*|tillitsvald|tillitsvalgt)", re.I),
}

MOCK_HEADER_FIELDS = 4

_BOILERPLATE_NB = [
    "Saken er behandlet i samsvar med gjeldende regelverk.",
    "Vedtaket bygger på opplysninger innhentet i forbindelse med saksbehandlingen.",
    "Dokumentasjonen er gjennomgått og vurdert av saksbehandler.",
    "Partene er varslet om saksgangen på vanlig måte.",
    "Ytterligere opplysninger kan innhentes ved behov.",
    "Saksbehandlingen følger forvaltningslovens bestemmelser.",
    "Det er lagt vekt på en helhetlig vurdering av forholdene i saken.",
    "Klageadgang følger av forvaltningsloven kapittel VI.",
]

_BOILERPLATE_NN = [
    "Saka er handsama i samsvar med gjeldande regelverk.",
    "Vedtaket byggjer på opplysningar innhenta i samband med sakshandsaminga.",
    "Dokumentasjonen er gjennomgått og vurdert av sakshandsamar.",
    "Partane er varsla om saksgangen på vanleg måte.",
    "Ytterlegare opplysningar kan innhentast ved behov.",
    "Sakshandsaminga følgjer forvaltningslova sine føresegner.",
    "Det er lagt vekt på ei heilskapleg vurdering av forholda i saka.",
    "Klagerett følgjer av forvaltningslova kapittel VI.",
]


# Neutral sentences for the mock's sections. A document draws its own permutation,
# and each section takes two, so no sentence occurs twice in a joined document of
# up to eight sections and two documents rarely share a pair.
_SECTION_FILLER_NB = [
    "Opplysningene er gjennomgått av saksbehandler.",
    "Det vises til tidligere korrespondanse i saken.",
    "Partene har fått anledning til å uttale seg.",
    "Fristen for å komme med merknader er varslet skriftlig.",
    "Saken er vurdert opp mot gjeldende retningslinjer.",
    "Møtet ble holdt i henhold til innkallingen.",
    "Det er ikke fremmet innsigelser mot saksgangen.",
    "Dokumentasjonen følger vedlagt under behandlingen.",
    "Forholdene er forelagt de berørte i rimelig tid.",
    "Videre behandling skjer etter vanlige rutiner.",
    "Det er innhentet de uttalelsene som er nødvendige.",
    "Beslutningen er truffet etter en samlet gjennomgang.",
    "Alle sider av saken er tatt med i betraktning.",
    "Behandlingen har foregått innenfor de fastsatte fristene.",
    "Nødvendige varsler er sendt ut i god tid.",
    "Saksfremstillingen bygger på det som er kjent per i dag.",
]
_SECTION_FILLER_NN = [
    "Opplysningane er gjennomgåtte av sakshandsamar.",
    "Det blir synt til tidlegare korrespondanse i saka.",
    "Partane har fått høve til å uttale seg.",
    "Fristen for å kome med merknader er varsla skriftleg.",
    "Saka er vurdert opp mot gjeldande retningslinjer.",
    "Møtet vart halde i samsvar med innkallinga.",
    "Det er ikkje fremja innvendingar mot saksgangen.",
    "Dokumentasjonen følgjer vedlagd under handsaminga.",
    "Forholda er førelagde dei råka i rimeleg tid.",
    "Vidare handsaming skjer etter vanlege rutinar.",
    "Det er innhenta dei fråsegnene som er nødvendige.",
    "Avgjerda er teken etter ei samla gjennomgang.",
    "Alle sider av saka er tekne med i vurderinga.",
    "Handsaminga har gått føre seg innanfor dei fastsette fristane.",
    "Nødvendige varsel er sende ut i god tid.",
    "Saksframstillinga byggjer på det som er kjent per i dag.",
]


class MockBackend(GenerationBackend):
    """Deterministic template filler used to exercise the pipeline without a model.

    Parses the machine-readable manifest block the prompt builder embeds in
    every prompt (`VALUE|type|value`, `CLAUSE_SEEDED|type|text`,
    `CLAUSE_MARKED|type`, `NEGATIVE|type|text`, `SEED|n`) and assembles a
    document that places every value verbatim, a few in a short field-header
    block and the rest inline in generated boilerplate sentences, seeded for
    reproducibility. The header is capped at `MOCK_HEADER_FIELDS` for the same
    reason the prompt caps it: a document that opens with a row per planted value
    is the table dump G13 rejects.
    """

    def generate(
        self, prompts: List[str], *, max_new_tokens: int = 900,
        temperature: float = 0.9, seed: Optional[int] = None,
    ) -> List[str]:
        self.last_finished = [True] * len(prompts)
        outputs = []
        for prompt in prompts:
            if "\nSECTION|" in prompt and "\nREPAIR|" not in prompt:
                outputs.append(self._fill_section(prompt))
            elif "\nAUDIT|1" in prompt:
                outputs.append(self._audit(prompt))
            elif "\nAUDIT_REPAIR|1" in prompt:
                outputs.append(self._audit_repair(prompt))
            elif "\nREPAIR|" in prompt:
                outputs.append(self._repair(prompt))
            else:
                outputs.append(self._fill(prompt))
        return outputs

    @staticmethod
    def _audited_document(prompt: str) -> str:
        return prompt.split(AUDIT_OPEN + "\n", 1)[1].split("\n" + AUDIT_CLOSE, 1)[0]

    def _audit(self, prompt: str) -> str:
        """Mock a G11 audit pass: the two cue phrases, plus lexical framing and contradiction tests.

        Args:
            prompt: A G11 audit prompt; its manifest may carry `CLAUSE|TYPE|text` lines
                for the planned clauses.

        Returns:
            `FUNN|<code>|<sentence>` lines, or `INGEN`.
        """
        document = self._audited_document(prompt)
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1] if MANIFEST_SENTINEL in prompt else ""
        clauses = [tuple(line.split("|", 2)[1:]) for line in manifest.splitlines() if line.startswith("CLAUSE|")]
        findings = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", document):
            stripped = sentence.strip().rstrip(".")
            if not stripped:
                continue
            lowered = stripped.lower()
            if MOCK_FRAMING_CUE in stripped:
                findings.append(f"FUNN|RAMME|{stripped}")
            elif MOCK_ELABORATION_CUE in stripped:
                findings.append(f"FUNN|SENSITIV|{stripped}")
            elif (_MOCK_SPECIAL_RE.search(stripped) and not _MOCK_SUPPORT_RE.search(stripped)
                  and any(not _MOCK_NEGATED_RE.search(stripped[max(0, m.start() - 25):m.start()])
                          for m in _MOCK_RELEVANCE_RE.finditer(stripped))):
                findings.append(f"FUNN|RAMME|{stripped}")
            elif self._contradicts(lowered, clauses):
                findings.append(f"FUNN|MOTSIGELSE|{stripped}")
        return "\n".join(findings) if findings else "INGEN"

    @staticmethod
    def _contradicts(sentence: str, clauses) -> bool:
        """Whether a (lower-cased) sentence denies a planted clause or explains it away.

        A sentence contradicts when it carries the clause's own words followed by an
        explain-away ("men denne finst ikkje i register"), or when it denies the topic of a
        clause the record planted ("ingen registrerte straffedomar" with a CRIMINAL clause).
        """
        for etype, clause in clauses:
            if clause.lower() in sentence and _MOCK_EXPLAIN_AWAY_RE.search(sentence):
                return True
            topic = _MOCK_TOPIC_STEMS.get(etype)
            if (topic is not None and _MOCK_DENIAL_RE.search(sentence) and topic.search(sentence)
                    and clause.lower() not in sentence):
                return True
        return False

    def _audit_repair(self, prompt: str) -> str:
        """Mock a targeted repair: delete the quoted material, keep the listed values.

        A real model is asked to delete or neutralise exactly the audited
        sentences while keeping every planned value and clause verbatim, so the
        mock does the same -- it replaces each quote with whatever `KEEP` values
        sat inside it, which is what makes the repaired draft able to pass G2
        again rather than failing on a value the deletion took with it.
        """
        document = self._audited_document(prompt)
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1]
        removes = [l.split("|", 1)[1] for l in manifest.splitlines() if l.startswith("REMOVE|")]
        keeps = [l.split("|", 1)[1] for l in manifest.splitlines() if l.startswith("KEEP|")]
        for quote in removes:
            kept = [k for k in keeps if k and k in quote]
            document = document.replace(quote, "; ".join(kept))
        document = re.sub(r"[ \t]{2,}", " ", document)
        document = re.sub(r" +([.,;:])", r"\1", document)
        document = re.sub(r"(?<=[.;:])\s*\.", "", document)
        return re.sub(r"\n{3,}", "\n\n", document).strip()

    def _repair(self, prompt: str) -> str:
        """Mock a minimal-edit repair: append each missing value in a sentence."""
        draft = prompt.split(DRAFT_OPEN + "\n", 1)[1].split("\n" + DRAFT_CLOSE, 1)[0]
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1]
        missing = [line.split("|", 1)[1] for line in manifest.splitlines() if line.startswith("MISSING|")]
        return draft + "".join(f" Det er også registrert at dette gjelder {m}." for m in missing)

    def _parse_manifest(self, prompt: str):
        values, seeded_clauses, marked_types, seed, form = [], [], [], 0, "nb"
        negatives: List[str] = []
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1] if MANIFEST_SENTINEL in prompt else prompt
        for line in manifest.splitlines():
            m = _MANIFEST_LINE_RE.match(line.strip())
            if not m:
                continue
            kind, rest = m.groups()
            if kind == "VALUE":
                etype, value = rest.split("|", 1)
                values.append((etype, value))
            elif kind == "CLAUSE_SEEDED":
                etype, value = rest.split("|", 1)
                seeded_clauses.append((etype, value))
            elif kind == "CLAUSE_MARKED":
                marked_types.append(rest)
            elif kind == "NEGATIVE":
                negatives.append(rest.split("|", 1)[1])
            elif kind == "SEED":
                seed = int(rest)
            elif kind == "META":
                if rest.startswith("form="):
                    form = rest.split("=", 1)[1]
        return values, seeded_clauses, marked_types, negatives, seed, form

    def _fill_section(self, prompt: str) -> str:
        """Mock one section: its heading, its own items and two neutral sentences.

        Reads only the manifest lines `SECTION|k|n|kind`, `HEADING|...`, `LAST|1`
        and the section's items, so a missing value in the output is exactly a
        value the section was asked for and did not get.
        """
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1]
        values, seeded_clauses, marked_types, negatives, seed, form = self._parse_manifest(prompt)
        k, n, heading = 0, 1, None
        for line in manifest.splitlines():
            if line.startswith("SECTION|"):
                k, n = (int(x) for x in line.split("|")[1:3])
            elif line.startswith("HEADING|"):
                heading = line.split("|", 1)[1]
        rng = random.Random(seed)
        pool = _SECTION_FILLER_NB if form == "nb" else _SECTION_FILLER_NN
        order = random.Random(seed ^ 0xF111).sample(range(len(pool)), len(pool))
        filler = [pool[order[(2 * k) % len(pool)]], pool[order[(2 * k + 1) % len(pool)]]]

        header_items, prose_items = [], []
        for etype, value in values:
            to_header = k == 0 and rng.random() < 0.55 and len(header_items) < MOCK_HEADER_FIELDS
            (header_items if to_header else prose_items).append((etype, value))
        header_label = lambda etype: genres_mod.field_label(etype, form)  # noqa: E731
        sentences = [f"Opplysning ({etype}) i saken er {value}." for etype, value in prose_items]
        sentences += [f"Videre er det opplyst at vedkommende {text}." for _etype, text in seeded_clauses]
        sentences += [f"Det er også notert at vedkommende {text}." for text in negatives]
        sentences += [f"⟦{etype}: vedkommende har forhold av denne typen som er nærmere beskrevet i saken⟧."
                      for etype in marked_types]
        rng.shuffle(sentences)
        sentences.insert(rng.randint(0, len(sentences)), filler[0])
        sentences.append(filler[1])
        parts = []
        if heading:
            parts.append(heading)
        if header_items:
            parts.append("\n".join(f"{header_label(etype)}: {value}" for etype, value in header_items))
        parts.append(" ".join(sentences))
        return "\n\n".join(parts)

    def _fill(self, prompt: str) -> str:
        values, seeded_clauses, marked_types, negatives, seed, form = self._parse_manifest(prompt)
        rng = random.Random(seed)
        boilerplate = _BOILERPLATE_NB if form == "nb" else _BOILERPLATE_NN

        header_items, prose_items = [], []
        for etype, value in values:
            to_header = rng.random() < 0.55 and len(header_items) < MOCK_HEADER_FIELDS
            (header_items if to_header else prose_items).append((etype, value))

        lines = []
        for etype, value in header_items:
            lines.append(f"{genres_mod.field_label(etype, form)}: {value}")

        body_sentences = []
        for etype, value in prose_items:
            body_sentences.append(f"Opplysning ({etype}) i saken er {value}.")
        for etype, text in seeded_clauses:
            body_sentences.append(f"Videre er det opplyst at vedkommende {text}.")
        for text in negatives:
            body_sentences.append(f"Det er også notert at vedkommende {text}.")
        for etype in marked_types:
            body_sentences.append(f"⟦{etype}: vedkommende har forhold av denne typen som er nærmere beskrevet i saken⟧.")

        rng.shuffle(body_sentences)
        filler = list(boilerplate)
        rng.shuffle(filler)

        text = "\n".join(lines) + "\n\n" + " ".join(body_sentences)
        i = 0
        while len(text) < 500 and i < len(filler):
            text += " " + filler[i]
            i += 1
        return text


class HFBackend(GenerationBackend):
    """Batched transformers backend for the chosen instruct model.

    Loads in fp16 with `attn_implementation="sdpa"` (this machine's Volta GPU
    has no FlashAttention-2 support, per `docs/SYNTHETIC_DATA_SPEC.md` Section
    2), applies the model's chat template, and, when the template accepts it,
    passes `enable_thinking=False` to suppress Qwen3-style reasoning traces in
    the output -- probed once at construction time rather than assumed, since
    not every chat template takes that argument.
    """

    def __init__(
        self, model_repo_id: str, device: str = "cuda", dtype: str = "float16",
        attn_implementation: str = "sdpa",
    ) -> None:
        """Load the tokenizer and model.

        Args:
            model_repo_id: Hugging Face repo id of the instruct model to use.
            device: Device to load onto ("cuda" or "cpu").
            dtype: torch dtype name; "float16" per the measured Volta guidance,
                never "bfloat16" on this hardware.
            attn_implementation: SDPA backend name passed to `from_pretrained`.
        """
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch_dtype = getattr(torch, dtype)
        self.tokenizer = AutoTokenizer.from_pretrained(model_repo_id)
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_repo_id, torch_dtype=torch_dtype, attn_implementation=attn_implementation,
        ).to(device)
        self.model.eval()
        self.device = device
        self._supports_enable_thinking = self._probe_enable_thinking()

    def _probe_enable_thinking(self) -> bool:
        try:
            self.tokenizer.apply_chat_template(
                [{"role": "user", "content": "test"}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False,
            )
            return True
        except TypeError:
            return False

    def generate(
        self, prompts: List[str], *, max_new_tokens: int = 900,
        temperature: float = 0.9, seed: Optional[int] = None,
    ) -> List[str]:
        import torch

        if seed is not None:
            torch.manual_seed(seed)
        chat_texts = []
        for prompt in map(model_visible, prompts):
            kwargs = {"enable_thinking": False} if self._supports_enable_thinking else {}
            chat_texts.append(
                self.tokenizer.apply_chat_template(
                    [{"role": "user", "content": prompt}],
                    tokenize=False, add_generation_prompt=True, **kwargs,
                )
            )
        encoded = self.tokenizer(
            chat_texts, return_tensors="pt", padding=True, truncation=True,
        ).to(self.device)
        # Temperature 0 means greedy, not "sample from a zero-temperature
        # distribution": the G11 audit pass needs the same answer every time it
        # sees the same document, and passing temperature=0.0 to a sampling
        # generate() is a divide-by-zero in transformers' logits warper.
        sampling = {"do_sample": True, "temperature": temperature, "top_p": 0.9}
        if temperature <= 0:
            sampling = {"do_sample": False}
        # Qwen3.5 ships no generation_config.json, so the model's own eos is
        # <|endoftext|> while a chat turn ends on the tokenizer's <|im_end|>;
        # stop on both rather than rely on the model emitting the second.
        gen_eos = self.model.generation_config.eos_token_id
        gen_eos = gen_eos if isinstance(gen_eos, list) else [gen_eos]
        stop_on = [i for i in dict.fromkeys([*gen_eos, self.tokenizer.eos_token_id]) if i is not None]
        with torch.no_grad():
            output_ids = self.model.generate(
                **encoded, max_new_tokens=max_new_tokens, eos_token_id=stop_on,
                pad_token_id=self.tokenizer.pad_token_id, **sampling,
            )
        generated = output_ids[:, encoded["input_ids"].shape[1]:]
        eos = self.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        stop_ids = {i for i in [*eos, self.tokenizer.eos_token_id, self.tokenizer.pad_token_id] if i is not None}
        # A row that ended on end-of-sequence is padded after it; a row that ran
        # out of budget has a non-stop token in its last position.
        self.last_finished = [int(row[-1]) in stop_ids for row in generated]
        return self.tokenizer.batch_decode(generated, skip_special_tokens=True)


def build_backend(name: str, model: Optional[str] = None) -> GenerationBackend:
    """Construct a backend by name.

    Args:
        name: "mock" or "hf".
        model: Required Hugging Face repo id when `name == "hf"`.

    Returns:
        A `GenerationBackend` instance.
    """
    if name == "mock":
        return MockBackend()
    if name == "hf":
        if not model:
            raise ValueError("--backend hf requires --model <repo_id>")
        return HFBackend(model)
    raise ValueError(f"unknown backend: {name}")
