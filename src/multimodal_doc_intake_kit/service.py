from __future__ import annotations

from typing import Dict

from .models import (
    DocumentIntakeRequest,
    DocumentRecord,
    DocumentStatus,
    NormalizedDocument,
    ReviewAction,
    ReviewDecision,
)
from .pipeline import AUTO_ACCEPT_THRESHOLD, normalize_document
from .store import InMemoryDocumentStore


class DocumentNotFoundError(RuntimeError):
    pass


class ExportNotReadyError(RuntimeError):
    pass


class ReviewValidationError(RuntimeError):
    pass


class DocumentService:
    def __init__(self, store: InMemoryDocumentStore) -> None:
        self._store = store

    def ingest(self, request: DocumentIntakeRequest) -> NormalizedDocument:
        normalized = normalize_document(request)
        self._store.save(DocumentRecord(intake=request, normalized=normalized))
        return normalized

    def get_document(self, document_id: str) -> NormalizedDocument:
        return self._load(document_id).normalized

    def review_document(self, document_id: str, review: ReviewDecision) -> NormalizedDocument:
        record = self._load(document_id)
        if review.document_id != document_id:
            raise ReviewValidationError("Review payload document_id does not match route.")

        field_map: Dict[str, int] = {
            field.name: index for index, field in enumerate(record.normalized.extracted_fields)
        }
        unresolved_before = _unresolved_review_fields(record.normalized)
        if not unresolved_before:
            raise ReviewValidationError("Document has no review-pending fields.")

        for decision in review.field_decisions:
            if decision.field_name not in field_map:
                raise ReviewValidationError(f"Unknown field '{decision.field_name}'.")
            field = record.normalized.extracted_fields[field_map[decision.field_name]]
            if field.confidence >= AUTO_ACCEPT_THRESHOLD and not field.reviewed:
                raise ReviewValidationError(
                    f"Field '{decision.field_name}' does not require review."
                )
            if decision.action == ReviewAction.CORRECT and decision.corrected_value is None:
                raise ReviewValidationError(
                    f"Field '{decision.field_name}' requires corrected_value for action=correct."
                )

            if decision.action == ReviewAction.CORRECT:
                field.value = decision.corrected_value
            elif decision.action == ReviewAction.DROP:
                field.value = None

            field.confidence = 1.0
            field.reviewed = True
            field.review_reason_code = decision.reason_code.value
            field.review_note = decision.note

        record.last_review = review
        record.normalized.status = (
            DocumentStatus.REVIEWED
            if not _unresolved_review_fields(record.normalized)
            else DocumentStatus.REVIEW_PENDING
        )
        self._store.save(record)
        return record.normalized

    def export_document(self, document_id: str) -> NormalizedDocument:
        record = self._load(document_id)
        if _unresolved_review_fields(record.normalized):
            raise ExportNotReadyError("Document still has unresolved review-required fields.")
        if record.normalized.status == DocumentStatus.NORMALIZED:
            record.normalized.status = DocumentStatus.EXPORTED
        elif record.normalized.status == DocumentStatus.REVIEWED:
            record.normalized.status = DocumentStatus.EXPORTED
        self._store.save(record)
        return record.normalized

    def _load(self, document_id: str) -> DocumentRecord:
        record = self._store.get(document_id)
        if record is None:
            raise DocumentNotFoundError(document_id)
        return record


def _unresolved_review_fields(document: NormalizedDocument):
    return [
        field
        for field in document.extracted_fields
        if AUTO_ACCEPT_THRESHOLD > field.confidence >= 0.60 and not field.reviewed
    ]

