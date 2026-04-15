# Ingestion Pipeline Notes

This document defines implementation details for the document intake lifecycle used in this repository.

## Execution Stages

1. `queued`
2. `parsing`
3. `normalized`
4. `review_pending` (optional, confidence threshold breach)
5. `reviewed`
6. `exported`

Every stage transition should emit an immutable event with:

- `document_id`
- `stage`
- `timestamp`
- `worker_id`
- `attempt`

## Confidence Handling

Field-level confidence is required on all extracted entities.

Suggested defaults:

- auto-accept: `>= 0.92`
- review queue: `0.60 - 0.91`
- reject extraction: `< 0.60`

Confidence thresholds must be extraction-profile specific (invoice, contract, policy-manual, etc).

## Review Rules

- Reviews are field-scoped, not document-scoped.
- Corrections must retain original extraction value for audit.
- Reviewer writes should include reason codes:
  - `ocr_error`
  - `layout_misalignment`
  - `parser_miss`
  - `domain_override`

## Chunking Constraints

Chunk objects must carry provenance:

- source page index
- optional bounding boxes
- section path (`h1/h2/h3`)
- character offsets in normalized text body

Chunk IDs should be deterministic:

`sha256(document_id + section_path + page + text_window)`

## Export Guarantees

The export payload is considered canonical only when:

- required schema fields are present
- all required review fields are resolved
- checksum recorded for source file + normalized record

See schema definitions in `../schemas/`.
