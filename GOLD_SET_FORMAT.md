# Gold-set file format

For the labelling tool. A gold set is a folder. `eval/routing/validate_gold.py` checks it before every score:

```
python -m eval.routing.validate_gold path/to/gold_real
```

## Layout

```
gold_real/
  manifest.json
  documents/<doc_id>.txt     one UTF-8 text file per document
  labels.jsonl               one line per document, one JSON object per line
```

`doc_id` uses only `A-Z a-z 0-9 _ -`. Every line of `labels.jsonl` has a file `documents/<doc_id>.txt`.

## The text

- UTF-8, Unicode NFC, `\n` line ends (no `\r`).
- All offsets point into this exact text. Do not edit a document after labelling it: the hash would change.

## Offsets

- Counted in **Unicode code points** (Python `str` indexing), start inclusive, end exclusive.
- A JavaScript tool counts UTF-16 units, so convert before writing: use `Array.from(text)` indices. A character such as an emoji is one code point but two UTF-16 units.

## `manifest.json`

| field | value |
|---|---|
| `set_id` | name of the set, e.g. `gold_real` |
| `version` | set version, a string |
| `taxonomy_version` | must equal the taxonomy version in `eval/routing/text_taxonomy.yaml` (now `1.0.0`) |
| `labelling_rules` | which labelling rules were used (name and date) |
| `created` | date, `YYYY-MM-DD` |
| `documents` | number of lines in `labels.jsonl` |

## A line of `labels.jsonl`

| field | value |
|---|---|
| `doc_id` | see above |
| `text_sha256` | hex SHA-256 of the UTF-8 bytes of `documents/<doc_id>.txt` |
| `genre` | `case_file`, `letter_public_body`, `medical_welfare`, `hr_employment`, `table`, `form`, `scanned_ocr`, `email_thread`, `invoice`, `cv`, `news`, `other` |
| `language` | language code, e.g. `nb` |
| `source` | `handwritten`, `consent`, `public_layout`, `generated_planted` |
| `hard_negative` | `true` or `false`; a hard negative has **no spans** |
| `pages` | list of `{page, start, end}`; pages count from 1 and cover the whole text with no gaps or overlaps (one page: `start` 0, `end` = text length) |
| `spans` | list of `{start, end, type, planted}` and an optional `note` |
| `review` | `{prelabel_model, reviewed_by, reviewed_at, status}`; `status` is `prelabelled` or `reviewed`. Only `reviewed` documents are scored |

A span's `type` is one of the 59 taxonomy ids (the `id` values in `eval/routing/text_taxonomy.yaml`). `planted` is `true` when the value was written into the document for the test, `false` when it was already there.

## Rules the validator enforces

- `type` is one of the 59 ids.
- The text hash matches.
- `0 <= start < end <= length of the text`.
- A span does not start or end on whitespace.
- Spans of the same type do not overlap. Spans of different types may be nested (an ADDRESS around its POSTAL_CODE).
- `pages` cover the text without gaps.
- A hard negative has no spans.
- `genre` and `source` are from the lists above; the manifest's `documents` equals the number of lines.

Labelling rules: a lone surname or first name that refers to a person is PERSON. Include hard negatives.

## Synthetic example

`documents/g0001.txt` (86 code points; the text ends with `\n`):

```example-document
Saksbehandler Kari Nordmann ringte 99 99 99 99.
Nordmann bor i Storgata 5, 0182 Oslo.
```

`manifest.json`:

```example-manifest
{"set_id": "gold_real", "version": "1", "taxonomy_version": "1.0.0", "labelling_rules": "gold-set labelling rules, 07.11.2026", "created": "2026-11-20", "documents": 1}
```

The line in `labels.jsonl` (shown with line breaks here; in the file it is a single line):

```example-label
{
  "doc_id": "g0001",
  "text_sha256": "cdfe275304cd7ef4c1fb79686ff7b78ea931a231c6f1827334660644e04e2351",
  "genre": "letter_public_body",
  "language": "nb",
  "source": "handwritten",
  "hard_negative": false,
  "pages": [{"page": 1, "start": 0, "end": 86}],
  "spans": [
    {"start": 14, "end": 27, "type": "PERSON", "planted": false},
    {"start": 35, "end": 46, "type": "PHONE", "planted": false},
    {"start": 48, "end": 56, "type": "PERSON", "planted": false, "note": "lone surname"},
    {"start": 63, "end": 84, "type": "ADDRESS", "planted": false},
    {"start": 75, "end": 79, "type": "POSTAL_CODE", "planted": false}
  ],
  "review": {"prelabel_model": "<model id>", "reviewed_by": "yasin", "reviewed_at": "2026-11-20", "status": "reviewed"}
}
```
