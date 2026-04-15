from __future__ import annotations

import hashlib
from typing import List, Tuple

from .models import (
    Chunk,
    DocumentIntakeRequest,
    DocumentStatus,
    ExtractedField,
    FieldProvenance,
    NormalizedDocument,
    Profile,
)


AUTO_ACCEPT_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.60


def normalize_document(request: DocumentIntakeRequest) -> NormalizedDocument:
    fields = _build_fields(request)
    chunks = _build_chunks(request)
    status = (
        DocumentStatus.REVIEW_PENDING
        if any(_requires_review(field.confidence) for field in fields)
        else DocumentStatus.NORMALIZED
    )
    return NormalizedDocument(
        document_id=request.document_id,
        profile=request.profile,
        status=status,
        source_checksum_sha256=request.source.checksum_sha256,
        extracted_fields=fields,
        chunks=chunks,
    )


def _requires_review(confidence: float) -> bool:
    return REVIEW_THRESHOLD <= confidence < AUTO_ACCEPT_THRESHOLD


def _seed(request: DocumentIntakeRequest, suffix: str) -> int:
    material = f"{request.document_id}:{request.profile.value}:{request.source.checksum_sha256 or 'no-checksum'}:{suffix}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _build_fields(request: DocumentIntakeRequest) -> List[ExtractedField]:
    if request.profile == Profile.CONTRACT:
        return [
            _field("counterparty_name", "Northwind Analytics LLC", 0.98, page=1, bbox=[104.0, 168.0, 421.0, 197.0]),
            _field("effective_date", "2026-04-01", 0.96, page=1, bbox=[102.0, 204.0, 244.0, 226.0]),
            _field("termination_notice_days", 30 + (_seed(request, "termination") % 3) * 15, 0.71, page=14, bbox=[92.0, 582.0, 301.0, 612.0]),
        ]
    if request.profile == Profile.INVOICE:
        base_amount = 42_500 + (_seed(request, "invoice_total") % 8_000)
        return [
            _field("invoice_number", f"INV-{request.document_id[-6:].upper()}", 0.99, page=1, bbox=[88.0, 112.0, 224.0, 136.0]),
            _field("currency", "USD", 0.97, page=1, bbox=[402.0, 142.0, 446.0, 166.0]),
            _field("total_due_cents", base_amount, 0.89, page=1, bbox=[396.0, 212.0, 522.0, 236.0]),
        ]
    if request.profile == Profile.MANUAL:
        return [
            _field("document_title", "Service Operations Manual", 0.97, page=1, bbox=[84.0, 96.0, 402.0, 122.0]),
            _field("revision", f"r{1 + (_seed(request, 'revision') % 4)}", 0.95, page=1, bbox=[84.0, 132.0, 132.0, 154.0]),
            _field("requires_review_cycle", True, 0.75, page=6, bbox=[120.0, 442.0, 184.0, 466.0]),
        ]
    return [
        _field("document_label", request.document_id, 0.99, page=1, bbox=[64.0, 64.0, 240.0, 88.0]),
        _field("source_uri", str(request.source.uri), 0.94, page=1, bbox=[64.0, 100.0, 520.0, 126.0]),
    ]


def _build_chunks(request: DocumentIntakeRequest) -> List[Chunk]:
    specs = _chunk_specs(request.profile)
    chunks: List[Chunk] = []
    for page, section_path, text in specs:
        window = text[:120]
        digest = hashlib.sha256(
            f"{request.document_id}:{section_path}:{page}:{window}".encode("utf-8")
        ).hexdigest()
        chunks.append(
            Chunk(
                chunk_id=digest,
                text=text,
                section_path=section_path,
                page=page,
                char_start=0,
                char_end=len(text),
            )
        )
    return chunks


def _chunk_specs(profile: Profile) -> List[Tuple[int, str, str]]:
    if profile == Profile.CONTRACT:
        return [
            (
                14,
                "13.Term and Termination/13.2 Notice",
                "Either party may terminate this Agreement by providing thirty (30) days written notice, subject to any superseding amendment references in the annex.",
            )
        ]
    if profile == Profile.INVOICE:
        return [
            (
                1,
                "Summary/Totals",
                "Total balance due in USD. Payment terms are net 30 and late fees apply after the due date unless waived in writing.",
            )
        ]
    if profile == Profile.MANUAL:
        return [
            (
                6,
                "Operations/Review Cycle",
                "All operational procedures require quarterly review and sign-off by the owning service team and compliance lead.",
            )
        ]
    return [
        (
            1,
            "General/Body",
            "Generic normalized document content used for contract testing of downstream retrieval and export interfaces.",
        )
    ]


def _field(name: str, value, confidence: float, *, page: int, bbox: List[float]) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=value,
        confidence=confidence,
        provenance=FieldProvenance(page=page, bbox=bbox),
    )

