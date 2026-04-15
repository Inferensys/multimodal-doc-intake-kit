# Architecture: Multimodal Document Intake

## Design Goals

- Preserve layout semantics from non-linear documents.
- Make extraction outputs machine-verifiable via JSON Schema.
- Isolate uncertain fields for review without blocking the full document.
- Support deterministic replay for parsing regressions.

## Component Breakdown

- `ingest-api`: accepts upload metadata and extraction profile selection.
- `source-loader`: resolves local file paths or remote URLs.
- `layout-parser`: OCR + layout parsing + Markdown reconstruction.
- `normalizer`: converts layout output into canonical domain schema.
- `chunk-builder`: emits retrieval segments with provenance metadata.
- `embedding-stage`: turns chunks into retrieval vectors.
- `review-queue`: stores unresolved fields and assignment metadata.
- `export-api`: serves canonical normalized payloads and chunks.

## Data Flow

1. Client posts ingest request with profile and source URI.
2. Source loader resolves the URI into either a local byte stream or a remote URL payload.
3. Layout parser emits Markdown plus page-aware paragraph structure.
4. Normalizer maps layout output into typed fields and confidence scores.
5. Low-confidence fields generate review tasks.
6. Chunk builder emits retrieval entries with section/page anchors.
7. Embedding stage generates retrieval vectors for each chunk.
8. Export API serves normalized output once checks pass.

## Current Repository Modes

- `deterministic`
  - fully local
  - no provider dependencies
  - used by tests and contract fixtures
- `azure`
  - Azure Document Intelligence `prebuilt-layout`
  - Azure OpenAI `gpt-5-mini` for normalization
  - Azure OpenAI `text-embedding-3-small` for chunk vectors

The live mode is provider-backed but still preserves the same response contracts as the deterministic mode.

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
