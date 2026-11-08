"""The real-route runner: a gold set's documents through the detection service's text route, in process.

Runs with a detection_service checkout on the path (DS_ROOT holds the `detection_service` package) and only the
standard library besides. Each document is one page; its words (split on whitespace) are laid out left to right,
the text the engines see is the words joined by one space, and every offset is mapped back to the document's own
text. The route is the service's own `TextDetectService.detect_file` with `categories=["ALL"]` and the engine set
given, so each engine is asked through its routes at its floor, the rules run, and the merge is the service's.

    DS_ROOT=<dir> DOCS=<jsonl[.gz] with id, text_input> python run_route.py ENGINES OUT.jsonl
        ENGINES   fast | standard | advanced | fast+standard | ... | rules (the rule pass alone, no engine)
        OUT       one JSON line per document, then a summary line; "-" writes to stdout
    TABLE=<routing_table.json>   route with this table instead of the service's own (checked the same way)
    LIMIT=<n>                    the first n documents only

The output holds offsets, categories, scores and engines, never document text. Findings an engine scored under
its floor are recorded beside the route's answer (`under_floor`), so other floors can be scored offline without
another run. With Advanced on, every model request goes through a cost guard (see `install_cost_guard`).
"""
from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import sys
import time

DS_ROOT = os.environ.get("DS_ROOT", "/app")
sys.path.insert(0, DS_ROOT)

ENGINES, OUT = sys.argv[1], sys.argv[2]
LIMIT = int(os.environ["LIMIT"]) if os.environ.get("LIMIT") else None
# Cost guard (Advanced only). NOK per 1K tokens; cached prompt tokens are counted at full price (an upper bound).
PRICE_IN = float(os.environ.get("PRICE_IN", "0"))
PRICE_OUT = float(os.environ.get("PRICE_OUT", "0"))
SPENT_BEFORE = float(os.environ.get("SPENT_BEFORE_NOK", "0"))
STOP_NOK = float(os.environ.get("STOP_NOK", "0"))
TPM_BUDGET = int(os.environ.get("TPM_BUDGET", "18000"))
MAX_COMPLETION = 2048
TRANSIENT = {"engine_failed", "timed_out", "deadline", "rate_limited", "model_unavailable"}
MAX_DOC_ATTEMPTS = 3


def emit(fh, obj):
    fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
    fh.flush()


def build_page(text):
    """One page of the document's words, and the map from the joined text back to the document's offsets."""
    words, segs, x, joined = [], [], 0.0, 0
    for m in re.finditer(r"\S+", text):
        w = m.group(0)
        wd = 6.0 * len(w)
        words.append({"text": w, "x0": x, "y0": 2.0, "x1": x + wd, "y1": 10.0})
        segs.append((joined, m.start(), len(w)))
        x += wd + 6.0
        joined += len(w) + 1
    data = {"pages": [{"page_number": 1, "words": words, "error": None}], "total_document_pages": 1,
            "empty_pages": [], "operation_id": "gold", "metadata": None, "error": None}
    return data, segs


def to_orig(segs, start, end):
    """Joined-text offsets to the document's own: start at the word it falls in, end after its last character."""
    def start_map(p):
        for r, o, n in segs:
            if p < r + n:
                return o + max(0, p - r)
        return (segs[-1][1] + segs[-1][2]) if segs else p

    def end_map(p):
        last, prev = p - 1, None
        for r, o, n in segs:
            if last < r:
                return prev if prev is not None else o
            if last < r + n:
                return o + (last - r) + 1
            prev = o + n
        return prev if prev is not None else p

    s, e = start_map(start), end_map(end)
    return s, max(e, s)


class Spend:
    nok = SPENT_BEFORE
    requests = 0
    failed = 0
    prompt = 0
    completion = 0
    finish: dict = {}
    window: list = []
    stopped = False


class BudgetStop(Exception):
    pass


def install_cost_guard(fh):
    """Wrap the Azure OpenAI client's `create`: count tokens, stop at STOP_NOK, forward the call unchanged.
    It refuses to run without prices and a stop, and checks it sits in the path of every request."""
    if PRICE_IN <= 0 or PRICE_OUT <= 0 or STOP_NOK <= 0:
        raise SystemExit("Advanced needs PRICE_IN, PRICE_OUT and STOP_NOK")
    from detection_service.utils.helpers import ai_provider_adapters as adapters

    orig = adapters.AzureOpenAIProviderAdapter._client_for_running_loop

    def guarded(create):
        async def call(*args, **kwargs):
            if Spend.nok >= STOP_NOK:
                Spend.stopped = True
                raise BudgetStop()
            t0 = time.perf_counter()
            try:
                resp = await create(*args, **kwargs)
            except Exception as exc:
                Spend.failed += 1
                emit(fh, {"type": "req", "ok": False, "error": type(exc).__name__,
                          "status": getattr(exc, "status_code", None), "seconds": round(time.perf_counter() - t0, 2)})
                raise
            usage = getattr(resp, "usage", None)
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            fr = getattr(resp.choices[0], "finish_reason", None) if getattr(resp, "choices", None) else None
            Spend.requests += 1
            Spend.prompt += pt
            Spend.completion += ct
            Spend.finish[fr] = Spend.finish.get(fr, 0) + 1
            Spend.nok += pt / 1000 * PRICE_IN + ct / 1000 * PRICE_OUT
            Spend.window.append((time.monotonic(), pt + MAX_COMPLETION))
            emit(fh, {"type": "req", "ok": True, "prompt_tokens": pt, "completion_tokens": ct, "finish_reason": fr,
                      "temperature": kwargs.get("temperature"), "model": getattr(resp, "model", None),
                      "seconds": round(time.perf_counter() - t0, 2), "spent_nok": round(Spend.nok, 4)})
            return resp
        return call

    def patched(self):
        client = orig(self)
        comp = client.chat.completions
        if not getattr(comp, "_t15_guarded", False):
            wrapped = guarded(comp.create)
            comp.create = wrapped
            if client.chat.completions.create is not wrapped:
                raise RuntimeError("cost guard not in the request path")
            comp._t15_guarded = True
        return client

    adapters.AzureOpenAIProviderAdapter._client_for_running_loop = patched


async def pace(fh):
    """Keep the next document inside the deployment's tokens per minute (prompt + the answer cap, at arrival)."""
    need = max([c for _, c in Spend.window] or [4000])
    while True:
        now = time.monotonic()
        Spend.window[:] = [(t, c) for t, c in Spend.window if now - t <= 60]
        if not Spend.window or sum(c for _, c in Spend.window) + need <= TPM_BUDGET:
            return
        wait = 60 - (now - Spend.window[0][0]) + 0.5
        emit(fh, {"type": "wait", "seconds": round(wait, 1)})
        await asyncio.sleep(wait)


UNDER_FLOOR: list = []


def install_floor_tap():
    """Record what each engine's floor removes, beside the answer. The route itself is unchanged."""
    from detection_service.configs.engine_floors import floor_of, model_of
    from detection_service.domain.provenance import field_of
    from detection_service.entity_detection import engine_edge

    orig = engine_edge.apply_floors

    def tapped(result):
        kept = orig(result)
        if kept is result or result is None:
            return kept
        for page, k in zip(result.redaction_mapping.pages or [], kept.redaction_mapping.pages or []):
            kept_ids = {id(i) for i in k.sensitive}
            for item in page.sensitive:
                if id(item) not in kept_ids:
                    engines = list(field_of(item, "engines") or ())
                    model = model_of(engines[0]) if engines else None
                    UNDER_FLOOR.append({"start": field_of(item, "start"), "end": field_of(item, "end"),
                                        "score": field_of(item, "score"), "category": field_of(item, "category"),
                                        "engines": engines, "model": model, "floor": floor_of(model)})
        return kept

    engine_edge.apply_floors = tapped


def rules_only(text):
    from detection_service.entity_detection.tagger_rules import find_rule_matches
    from detection_service.text_pipeline.rule_pass import rule_types

    return [{"category": m.entity_type, "start": m.start, "end": m.end, "score": 1.0, "engines": ["rules"]}
            for m in find_rule_matches(text, frozenset(rule_types()))]


def load_docs(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def main():
    docs = load_docs(os.environ["DOCS"])[:LIMIT]
    fh = sys.stdout if OUT == "-" else open(OUT, "w", encoding="utf-8")
    from detection_service.api.routes.detect_routes import _parse_extracted_data
    from detection_service.configs.engine_floors import ENGINE_FLOORS
    from detection_service.services.text_detect_service import TextDetectService
    from detection_service.text_pipeline.pipeline import deadline_seconds
    from detection_service.text_pipeline.request import parse_text_request
    from detection_service.text_pipeline.routing_table import get_routing_table, load_routing_table

    rules = ENGINES == "rules"
    request = None if rules else parse_text_request(["ALL"], ENGINES.split("+"))
    table = load_routing_table(os.environ["TABLE"]) if os.environ.get("TABLE") else get_routing_table()
    if not rules and "advanced" in request.engines:
        install_cost_guard(fh)
    install_floor_tap()
    emit(fh, {"type": "start", "engines": ENGINES, "docs": len(docs), "table": table.version,
              "floors": {k: v for k, v in ENGINE_FLOORS.items()}, "stop_nok": STOP_NOK or None,
              "spent_before_nok": SPENT_BEFORE, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    t_run, stop_reason, done = time.perf_counter(), None, 0
    for d in docs:
        text = d["text_input"]
        if rules:
            emit(fh, {"type": "doc", "id": d["id"], "items": rules_only(text), "under_floor": [], "status": []})
            done += 1
            continue
        data, segs = build_page(text)
        attempts = 0
        while True:
            attempts += 1
            if Spend.nok >= (STOP_NOK or float("inf")):
                stop_reason = f"budget: {Spend.nok:.2f} NOK"
                break
            if "advanced" in request.engines:
                await pace(fh)
            UNDER_FLOOR.clear()
            t0 = time.perf_counter()
            ans = await TextDetectService.detect_file(_parse_extracted_data(data), request, "", True, 0, table,
                                                      time.monotonic() + deadline_seconds())
            res = ans.get("results") or {}
            status = (res.get("coverage") or {}).get("status", [])
            transient = [s for s in status if s.get("reason") in TRANSIENT]
            if Spend.stopped or not transient or attempts >= MAX_DOC_ATTEMPTS:
                break
            emit(fh, {"type": "wait", "why": "transient", "doc": d["id"], "seconds": 65})
            await asyncio.sleep(65)
        if stop_reason or Spend.stopped:
            stop_reason = stop_reason or f"budget: {Spend.nok:.2f} NOK (document {d['id']} not recorded)"
            break
        items = []
        for page in (res.get("redaction_mapping") or {}).get("pages", []):
            for s in page.get("sensitive", []):
                a, b = to_orig(segs, s["start"], s["end"])
                items.append({"category": s.get("category"), "entity_type": s.get("entity_type"), "start": a, "end": b,
                              "score": s.get("score"), "engines": s.get("engines"),
                              "engine_scores": s.get("engine_scores")})
        under = []
        for u in UNDER_FLOOR:
            a, b = to_orig(segs, u["start"], u["end"])
            under.append({**u, "start": a, "end": b})
        emit(fh, {"type": "doc", "id": d["id"], "file_status": ans.get("status"), "items": items, "under_floor": under,
                  "status": status, "attempts": attempts, "seconds": round(time.perf_counter() - t0, 2),
                  "spent_nok": round(Spend.nok, 4)})
        done += 1
    emit(fh, {"type": "summary", "engines": ENGINES, "docs_done": done, "docs": len(docs), "stop_reason": stop_reason,
              "requests_ok": Spend.requests, "requests_failed": Spend.failed, "prompt_tokens": Spend.prompt,
              "completion_tokens": Spend.completion, "finish_reasons": Spend.finish,
              "spent_nok_this_run": round(Spend.nok - SPENT_BEFORE, 4), "spent_nok_total": round(Spend.nok, 4),
              "wall_s": round(time.perf_counter() - t_run, 1)})
    if fh is not sys.stdout:
        fh.close()


if __name__ == "__main__":
    asyncio.run(main())
