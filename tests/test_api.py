from fastapi.testclient import TestClient

from multimodal_doc_intake_kit.main import create_app


def _ingest_payload():
    return {
        "document_id": "contract-2026-04-15-001",
        "source": {
            "uri": "https://example.com/contracts/master-services-agreement.pdf",
            "mime_type": "application/pdf",
            "checksum_sha256": "2c64d7f544f6176be0bdb7669a7f2da4cb4f7ea77a3f2d8ec16f4fb115630f7e",
        },
        "profile": "contract_v1",
        "locale": "en-US",
        "submitted_at": "2026-04-15T09:05:00Z",
        "metadata": {"tenant": "acme-sandbox"},
    }


def test_ingest_returns_review_pending_and_deterministic_chunk_id():
    client = TestClient(create_app())

    response = client.post("/api/ingest", json=_ingest_payload())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "review_pending"
    assert payload["document_id"] == "contract-2026-04-15-001"
    assert payload["chunks"][0]["chunk_id"] == payload["chunks"][0]["chunk_id"]
    assert any(field["name"] == "termination_notice_days" for field in payload["extracted_fields"])


def test_export_blocked_until_review_is_resolved():
    client = TestClient(create_app())
    client.post("/api/ingest", json=_ingest_payload())

    export = client.get("/api/exports/contract-2026-04-15-001")
    assert export.status_code == 409

    review = client.post(
        "/api/review/contract-2026-04-15-001",
        json={
            "document_id": "contract-2026-04-15-001",
            "reviewer_id": "ops.review.17",
            "field_decisions": [
                {
                    "field_name": "termination_notice_days",
                    "action": "correct",
                    "corrected_value": 45,
                    "reason_code": "domain_override",
                    "note": "Clause amendment supersedes the base termination section.",
                }
            ],
            "submitted_at": "2026-04-15T09:09:21Z",
        },
    )
    assert review.status_code == 200
    assert review.json()["status"] == "reviewed"

    export = client.get("/api/exports/contract-2026-04-15-001")
    assert export.status_code == 200
    assert export.json()["status"] == "exported"


def test_review_rejects_unknown_field():
    client = TestClient(create_app())
    client.post("/api/ingest", json=_ingest_payload())

    response = client.post(
        "/api/review/contract-2026-04-15-001",
        json={
            "document_id": "contract-2026-04-15-001",
            "reviewer_id": "ops.review.17",
            "field_decisions": [
                {
                    "field_name": "missing_field",
                    "action": "accept",
                    "reason_code": "parser_miss",
                }
            ],
            "submitted_at": "2026-04-15T09:09:21Z",
        },
    )
    assert response.status_code == 400
    assert "Unknown field" in response.json()["detail"]

