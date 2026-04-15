from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from multimodal_doc_intake_kit.config import Settings
from multimodal_doc_intake_kit.models import (
    DocumentIntakeRequest,
    FieldDecision,
    Profile,
    ReviewAction,
    ReviewDecision,
    ReviewReasonCode,
    SourceDocument,
)
from multimodal_doc_intake_kit.service import DocumentService
from multimodal_doc_intake_kit.store import InMemoryDocumentStore


ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "demo" / "input"
OUTPUT_DIR = ROOT / "demo" / "output"


def main() -> None:
    os.environ.setdefault("DOC_INTAKE_PROVIDER", "azure")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    settings = Settings.from_env()
    service = DocumentService(InMemoryDocumentStore(), settings=settings)

    inputs = [
        {
            "document_id": "contract-live-2026-04-15",
            "profile": Profile.CONTRACT,
            "path": INPUT_DIR / "enterprise-renewal-contract.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "review_truth": {
                "counterparty_name": "Northwind Analytics LLC",
                "effective_date": "2026-04-01",
                "termination_notice_days": 45,
            },
        },
        {
            "document_id": "invoice-live-2026-04-15",
            "profile": Profile.INVOICE,
            "path": INPUT_DIR / "field-operations-invoice.pdf",
            "mime_type": "application/pdf",
            "review_truth": {
                "invoice_number": "INV-2048-APR",
                "currency": "USD",
                "total_due_cents": 1284450,
                "vendor_name": "Cascade Field Services",
            },
        },
        {
            "document_id": "manual-live-2026-04-15",
            "profile": Profile.MANUAL,
            "path": INPUT_DIR / "warehouse-reset-scan.png",
            "mime_type": "image/png",
            "review_truth": {
                "document_title": "Warehouse Safety Reset Procedure",
                "revision": "r7",
                "requires_review_cycle": True,
            },
        },
    ]

    summary = []
    for item in inputs:
        request = _build_request(
            document_id=item["document_id"],
            profile=item["profile"],
            path=item["path"],
            mime_type=item["mime_type"],
        )
        ingested = service.ingest(request)
        artifacts = service.get_artifacts(item["document_id"])

        _write_json(OUTPUT_DIR / f"{item['document_id']}.ingest.json", ingested.model_dump(mode="json"))
        _write_json(
            OUTPUT_DIR / f"{item['document_id']}.artifacts.json",
            artifacts.model_dump(mode="json"),
        )

        exported = ingested
        if ingested.status == "review_pending":
            review = _build_review_decision(ingested.document_id, ingested.extracted_fields, item["review_truth"])
            reviewed = service.review_document(ingested.document_id, review)
            exported = service.export_document(ingested.document_id)
            _write_json(OUTPUT_DIR / f"{item['document_id']}.review.json", review.model_dump(mode="json"))
            _write_json(OUTPUT_DIR / f"{item['document_id']}.reviewed.json", reviewed.model_dump(mode="json"))
        else:
            exported = service.export_document(ingested.document_id)

        _write_json(OUTPUT_DIR / f"{item['document_id']}.export.json", exported.model_dump(mode="json"))
        summary.append(
            {
                "document_id": item["document_id"],
                "profile": item["profile"].value,
                "status": exported.status,
                "trace": [step.model for step in exported.processing_trace],
                "fields": {field.name: field.value for field in exported.extracted_fields},
                "chunks": len(exported.chunks),
            }
        )

    _write_json(OUTPUT_DIR / "demo-summary.json", summary)


def _build_request(document_id: str, profile: Profile, path: Path, mime_type: str) -> DocumentIntakeRequest:
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    return DocumentIntakeRequest(
        document_id=document_id,
        source=SourceDocument(uri=str(path), mime_type=mime_type, checksum_sha256=checksum),
        profile=profile,
        locale="en-US",
        submitted_at=datetime.now(timezone.utc),
        metadata={"demo": True, "source_path": str(path.name)},
    )


def _build_review_decision(document_id: str, fields, truth: Dict[str, object]) -> ReviewDecision:
    decisions = []
    for field in fields:
        if field.confidence >= 0.92:
            continue
        truth_value = truth.get(field.name, field.value)
        action = ReviewAction.ACCEPT if truth_value == field.value else ReviewAction.CORRECT
        decisions.append(
            FieldDecision(
                field_name=field.name,
                action=action,
                corrected_value=truth_value if action == ReviewAction.CORRECT else None,
                reason_code=ReviewReasonCode.DOMAIN_OVERRIDE if action == ReviewAction.CORRECT else ReviewReasonCode.PARSER_MISS,
                note="Automated demo review pass using expected field truth set.",
            )
        )

    if not decisions:
        raise RuntimeError("No reviewable fields were returned for a review-pending document.")

    return ReviewDecision(
        document_id=document_id,
        reviewer_id="demo.review.bot",
        field_decisions=decisions,
        submitted_at=datetime.now(timezone.utc),
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
