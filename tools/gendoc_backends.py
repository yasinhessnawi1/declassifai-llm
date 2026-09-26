"""Pluggable generation backends: a deterministic mock and a transformers-based one.

The model to use for real generation has not been chosen yet (that is a
separate, parallel workstream -- see `docs/MODEL_SELECTION.md`, not yet
written). This module defines the backend contract both a screening result and
this generator's own tests can rely on, and implements it twice:

* `MockBackend` -- a deterministic template filler with no ML dependency at
  all. It exists so every gate in this pipeline (verbatim presence, name
  collision, checksum consistency, diversity, unplanned-PII sweep) can be
  exercised and proven to catch injected failures without a GPU or a chosen
  model. This is the backend used for the 50-document pilot run.
* `HFBackend` -- the real backend, written to the same contract, for whichever
  instruct model model-selection settles on. It is implemented in full
  (fp16, sdpa attention, chat template, batched generation, a hook to disable
  Qwen3-style "thinking" via `enable_thinking=False`) but is not exercised in
  this workstream: the machine's GPU is in use by a concurrent model-screening
  job, and no model has been chosen yet. `torch`/`transformers` are imported
  lazily inside `HFBackend.__init__` so importing this module, or running with
  `--backend mock`, never requires them.

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


_MANIFEST_LINE_RE = re.compile(r"^(VALUE|CLAUSE_SEEDED|CLAUSE_MARKED|SEED|META|REPAIR|MISSING)\|(.*)$")

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


class MockBackend(GenerationBackend):
    """Deterministic template filler used to exercise the pipeline without a model.

    Parses the machine-readable manifest block the prompt builder embeds in
    every prompt (`VALUE|type|value`, `CLAUSE_SEEDED|type|text`,
    `CLAUSE_MARKED|type`, `SEED|n`) and assembles a document that places every
    value verbatim, some in a field-header block and some inline in generated
    boilerplate sentences, seeded for reproducibility.
    """

    def generate(
        self, prompts: List[str], *, max_new_tokens: int = 900,
        temperature: float = 0.9, seed: Optional[int] = None,
    ) -> List[str]:
        self.last_finished = [True] * len(prompts)
        return [self._repair(p) if "\nREPAIR|" in p else self._fill(p) for p in prompts]

    def _repair(self, prompt: str) -> str:
        """Mock a minimal-edit repair: append each missing value in a sentence."""
        draft = prompt.split(DRAFT_OPEN + "\n", 1)[1].split("\n" + DRAFT_CLOSE, 1)[0]
        manifest = prompt.split(MANIFEST_SENTINEL, 1)[1]
        missing = [line.split("|", 1)[1] for line in manifest.splitlines() if line.startswith("MISSING|")]
        return draft + "".join(f" Det er også registrert at dette gjelder {m}." for m in missing)

    def _parse_manifest(self, prompt: str):
        values, seeded_clauses, marked_types, seed, form = [], [], [], 0, "nb"
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
            elif kind == "SEED":
                seed = int(rest)
            elif kind == "META":
                if rest.startswith("form="):
                    form = rest.split("=", 1)[1]
        return values, seeded_clauses, marked_types, seed, form

    def _fill(self, prompt: str) -> str:
        values, seeded_clauses, marked_types, seed, form = self._parse_manifest(prompt)
        rng = random.Random(seed)
        boilerplate = _BOILERPLATE_NB if form == "nb" else _BOILERPLATE_NN

        header_items, prose_items = [], []
        for etype, value in values:
            (header_items if rng.random() < 0.55 else prose_items).append((etype, value))

        lines = []
        for etype, value in header_items:
            lines.append(f"{etype}: {value}")

        body_sentences = []
        for etype, value in prose_items:
            body_sentences.append(f"Opplysning ({etype}) i saken er {value}.")
        for etype, text in seeded_clauses:
            body_sentences.append(f"Videre er det opplyst at vedkommende {text}.")
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
        with torch.no_grad():
            output_ids = self.model.generate(
                **encoded, max_new_tokens=max_new_tokens, do_sample=True,
                temperature=temperature, top_p=0.9, pad_token_id=self.tokenizer.pad_token_id,
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
