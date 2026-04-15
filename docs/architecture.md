# Architecture: Multimodal Document Intake

## Design Goals

- Preserve layout semantics from non-linear documents.
- Make extraction outputs machine-verifiable via JSON Schema.
- Isolate uncertain fields for review without blocking the full document.
- Support deterministic replay for parsing regressions.

## Component Breakdown

- `ingest-api`: accepts upload metadata and extraction profile selection.
- `blob-store`: immutable source document storage.
- `parser-worker`: OCR + layout parsing + table/form region detection.
- `normalizer`: converts parser output into canonical domain schema.
- `chunk-builder`: emits retrieval segments with provenance metadata.
- `review-queue`: stores unresolved fields and assignment metadata.
- `export-api`: serves canonical normalized payloads and chunks.

## Data Flow

1. Client posts ingest request with profile and source URI.
2. Ingest API writes a `queued` record and dispatches parser job.
3. Parser emits raw regions (text blocks, tables, key-value groups).
4. Normalizer maps raw regions into typed fields and confidence scores.
5. Low-confidence fields generate review tasks.
6. Chunk builder emits retrieval entries with section/page anchors.
7. Export API serves normalized output once checks pass.

## Failure Modes and Handling

- parser timeout:
  - stage set to `parsing_failed`
  - retry with backoff up to configured max attempts
- schema validation failure:
  - stage set to `normalization_failed`
  - attach schema error vector for triage
- review SLA breach:
  - stage set to `review_overdue`
  - emit alert event to operations channel

## Replay Strategy

Store parser raw output snapshots keyed by:

- parser version
- extraction profile
- source document checksum

This allows deterministic diffing when parser models or prompts are updated.

## Suggested Metrics

- `ingest_latency_ms` by profile
- `parse_failure_rate` by mime type
- `%_fields_requiring_review`
- `review_turnaround_minutes`
- `schema_validation_failures_total`
