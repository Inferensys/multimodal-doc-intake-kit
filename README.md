# multimodal-doc-intake-kit

FastAPI service for turning heterogeneous documents (PDF, scans, forms, manuals) into:

- validated structured records
- retrieval-ready chunks with provenance
- review tasks for low-confidence extractions

This project is intentionally schema-first: extraction output is treated as an API contract, not an untyped blob.

## Scope

In scope:

- document ingestion lifecycle (`queued -> parsing -> normalized -> reviewed -> exported`)
- layout-aware extraction normalization
- confidence-scored field outputs
- deterministic chunking with page and bbox provenance
- operator review handoff format

Out of scope:

- OCR model training
- vector database operations (indexing is integration-specific)
- production auth and tenancy hardening

## Current implementation

The first slice is intentionally single-process and in-memory:

- `POST /api/ingest` accepts a typed intake request and produces a normalized record.
- `GET /api/documents/{id}` returns the latest normalized document.
- `POST /api/review/{id}` applies field-level decisions and resolves review-required fields.
- `GET /api/exports/{id}` emits the canonical normalized document once review constraints are satisfied.
- deterministic normalization and chunk generation come from profile-specific templates seeded by the intake payload

## Data Contracts

- ingest request schema: [`schemas/document-intake-request.schema.json`](./schemas/document-intake-request.schema.json)
- normalized output schema: [`schemas/normalized-document.schema.json`](./schemas/normalized-document.schema.json)
- review decision schema: [`schemas/review-decision.schema.json`](./schemas/review-decision.schema.json)

Sample payloads:

- [`examples/ingest-request.json`](./examples/ingest-request.json)
- [`examples/normalized-document.json`](./examples/normalized-document.json)
- [`examples/review-decision.json`](./examples/review-decision.json)

## Project layout

```text
.
├── docs/
│   ├── architecture.md
│   ├── implementation-plan.md
│   └── pipeline-notes.md
├── src/multimodal_doc_intake_kit/
│   ├── main.py
│   ├── models.py
│   ├── pipeline.py
│   ├── service.py
│   └── store.py
├── tests/
│   └── test_api.py
├── schemas/
└── examples/
```

## Processing Topology

```text
[Blob Store] -> [Ingest API] -> [Parser Worker] -> [Normalizer]
                                           |            |
                                           |            v
                                           |       [Chunk Builder]
                                           v            |
                                    [Review Queue] <----+
                                           |
                                           v
                                      [Export API]
```

## Run locally

Prerequisites:

- Python 3.9
- `uv`

```bash
uv sync --extra dev
uv run uvicorn multimodal_doc_intake_kit.main:app --app-dir src --reload
```

## Test

```bash
uv run pytest -q
```

## Example flow

Ingest:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d @examples/ingest-request.json
```

Review:

```bash
curl -X POST http://127.0.0.1:8000/api/review/contract-2026-04-15-001 \
  -H "Content-Type: application/json" \
  -d @examples/review-decision.json
```

Export:

```bash
curl http://127.0.0.1:8000/api/exports/contract-2026-04-15-001
```

Detailed architecture notes: [`docs/architecture.md`](./docs/architecture.md).
Stage semantics and field-confidence rules: [`docs/pipeline-notes.md`](./docs/pipeline-notes.md).

## Notes

- Review is field-scoped and only required for confidence values in the review band.
- Export is blocked until all review-required fields are resolved.
- Storage is in-memory for this slice; restart clears state.
