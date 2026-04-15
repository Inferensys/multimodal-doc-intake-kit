# Implementation Plan

## Objective

Build a runnable contract-first document intake service that validates the existing schemas and exercises the review/export lifecycle.

## v1 Scope

- FastAPI service with in-memory state
- Pydantic models mirroring the existing ingest, normalized, and review contracts
- deterministic normalization and chunk generation with profile-specific templates
- field-level review application and export gating
- API tests for ingest, review, and export behavior

## Module split

- `models.py`: public API contracts and internal record types
- `pipeline.py`: profile-driven deterministic extraction and chunking
- `store.py`: in-memory document persistence
- `service.py`: lifecycle orchestration, review validation, export preconditions
- `main.py`: HTTP routing and exception mapping

## Design rules

- normalized records remain strongly typed end-to-end
- review state is tracked at field granularity
- export transitions are explicit and blocked while unresolved review fields remain
- chunk IDs are deterministic from document, section, page, and text window

