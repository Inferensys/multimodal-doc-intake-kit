from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .azure_backend import LivePipelineError
from .models import DocumentArtifacts, DocumentIntakeRequest, NormalizedDocument, ReviewDecision
from .service import (
    DocumentNotFoundError,
    DocumentService,
    ExportNotReadyError,
    ReviewValidationError,
)
from .store import InMemoryDocumentStore


def create_app() -> FastAPI:
    app = FastAPI(title="multimodal-doc-intake-kit", version="0.1.0")
    service = DocumentService(InMemoryDocumentStore())
    app.state.document_service = service

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.post("/api/ingest", response_model=NormalizedDocument)
    def ingest(request: DocumentIntakeRequest) -> NormalizedDocument:
        try:
            return service.ingest(request)
        except LivePipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/documents/{document_id}", response_model=NormalizedDocument)
    def get_document(document_id: str) -> NormalizedDocument:
        try:
            return service.get_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/artifacts/{document_id}", response_model=DocumentArtifacts)
    def get_artifacts(document_id: str) -> DocumentArtifacts:
        try:
            return service.get_artifacts(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/review/{document_id}", response_model=NormalizedDocument)
    def review_document(document_id: str, review: ReviewDecision) -> NormalizedDocument:
        try:
            return service.review_document(document_id, review)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReviewValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/exports/{document_id}", response_model=NormalizedDocument)
    def export_document(document_id: str) -> NormalizedDocument:
        try:
            return service.export_document(document_id)
        except DocumentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ExportNotReadyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
