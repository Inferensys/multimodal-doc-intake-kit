# multimodal-doc-intake-kit

Reference repository for turning heterogeneous documents (PDF, scans, forms, manuals) into:

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

## Working Set

Start with the reference contracts and example payloads:

1. Inspect the ingest contract in [`schemas/document-intake-request.schema.json`](./schemas/document-intake-request.schema.json).
2. Compare it with [`examples/ingest-request.json`](./examples/ingest-request.json).
3. Trace the normalized output in [`examples/normalized-document.json`](./examples/normalized-document.json).
4. Review the operator correction payload in [`examples/review-decision.json`](./examples/review-decision.json).

## Data Contracts

- ingest request schema: [`schemas/document-intake-request.schema.json`](./schemas/document-intake-request.schema.json)
- normalized output schema: [`schemas/normalized-document.schema.json`](./schemas/normalized-document.schema.json)
- review decision schema: [`schemas/review-decision.schema.json`](./schemas/review-decision.schema.json)

Sample payloads:

- [`examples/ingest-request.json`](./examples/ingest-request.json)
- [`examples/normalized-document.json`](./examples/normalized-document.json)
- [`examples/review-decision.json`](./examples/review-decision.json)

## API Sketch

- `POST /api/ingest` submit document metadata + extraction profile
- `GET /api/documents/{id}` fetch normalized record + extraction confidence
- `POST /api/review/{id}` submit field-level corrections
- `POST /api/search` query normalized chunks by lexical/semantic filters
- `GET /api/exports/{id}` export canonical JSON for downstream workflows

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

Detailed architecture notes: [`docs/architecture.md`](./docs/architecture.md).
Stage semantics and field-confidence rules: [`docs/pipeline-notes.md`](./docs/pipeline-notes.md).

## Demo Artifacts

Image placeholders and capture instructions are in [`assets/README.md`](./assets/README.md).

## Repository Layout

```text
docs/       architecture and pipeline notes
examples/   request/response payloads for local testing
schemas/    JSON schemas for ingest, normalize, and review contracts
assets/     screenshot placeholders and demo capture instructions
```
