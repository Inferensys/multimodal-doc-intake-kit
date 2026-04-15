from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import unquote, urlparse

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
from azure.core.credentials import AzureKeyCredential
from openai import AzureOpenAI

from .config import Settings
from .models import (
    Chunk,
    DocumentIntakeRequest,
    DocumentStatus,
    ExtractedField,
    FieldProvenance,
    NormalizedDocument,
    ProcessingMode,
    ProcessingStep,
    Profile,
)


AUTO_ACCEPT_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.60


class LivePipelineError(RuntimeError):
    pass


@dataclass
class DocumentProcessingResult:
    normalized: NormalizedDocument
    layout_markdown: str
    chunk_embeddings: Dict[str, List[float]]


class AzureDocumentPipeline:
    def __init__(self, settings: Settings) -> None:
        settings.validate_for_live_mode()
        self._settings = settings
        self._doc_client = DocumentIntelligenceClient(
            endpoint=settings.azure_docintelligence_endpoint,
            credential=AzureKeyCredential(settings.azure_docintelligence_api_key),
        )
        self._openai_client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )

    def ingest(self, request: DocumentIntakeRequest) -> DocumentProcessingResult:
        layout_result = self._analyze_layout(request)
        fields = self._normalize_fields(request, layout_result)
        chunks = self._build_chunks(request, layout_result)
        embeddings = self._embed_chunks(chunks)

        for chunk in chunks:
            vector = embeddings.get(chunk.chunk_id)
            if vector:
                chunk.embedding_model = self._settings.azure_openai_embedding_deployment
                chunk.embedding_dimensions = len(vector)

        status = (
            DocumentStatus.REVIEW_PENDING
            if any(REVIEW_THRESHOLD <= field.confidence < AUTO_ACCEPT_THRESHOLD for field in fields)
            else DocumentStatus.NORMALIZED
        )

        normalized = NormalizedDocument(
            document_id=request.document_id,
            profile=request.profile,
            status=status,
            source_checksum_sha256=request.source.checksum_sha256,
            source_mime_type=request.source.mime_type,
            processing_mode=ProcessingMode.AZURE_FOUNDATION,
            processing_trace=[
                ProcessingStep(
                    stage="layout",
                    provider="azure-document-intelligence",
                    model="prebuilt-layout",
                    status="completed",
                    notes="Markdown layout extraction with page-aware structure.",
                ),
                ProcessingStep(
                    stage="normalize",
                    provider="azure-openai",
                    model=self._settings.azure_openai_chat_deployment,
                    status="completed",
                    notes="Schema normalization by profile with evidence snippets.",
                ),
                ProcessingStep(
                    stage="embed",
                    provider="azure-openai",
                    model=self._settings.azure_openai_embedding_deployment or "disabled",
                    status="completed" if embeddings else "skipped",
                    notes="Chunk vectors generated for retrieval." if embeddings else "Embedding deployment disabled.",
                ),
            ],
            layout_excerpt_markdown=layout_result["markdown"][:1400],
            extracted_fields=fields,
            chunks=chunks,
        )
        return DocumentProcessingResult(
            normalized=normalized,
            layout_markdown=layout_result["markdown"],
            chunk_embeddings=embeddings,
        )

    def _analyze_layout(self, request: DocumentIntakeRequest) -> Dict[str, Any]:
        source_mode, payload = _resolve_source_payload(request.source.uri)
        try:
            if source_mode == "url":
                poller = self._doc_client.begin_analyze_document(
                    "prebuilt-layout",
                    AnalyzeDocumentRequest(url_source=payload),
                    output_content_format=DocumentContentFormat.MARKDOWN,
                )
            else:
                with open(payload, "rb") as handle:
                    poller = self._doc_client.begin_analyze_document(
                        "prebuilt-layout",
                        body=handle,
                        output_content_format=DocumentContentFormat.MARKDOWN,
                    )
            result = poller.result()
        except Exception as exc:  # pragma: no cover - exercised in live demo only
            raise LivePipelineError(f"Document Intelligence layout analysis failed: {exc}") from exc

        markdown = getattr(result, "content", "") or ""
        paragraphs = []
        for paragraph in getattr(result, "paragraphs", []) or []:
            content = (getattr(paragraph, "content", None) or "").strip()
            if not content:
                continue
            bounding_regions = getattr(paragraph, "bounding_regions", None) or []
            page = 1
            polygon = None
            if bounding_regions:
                first_region = bounding_regions[0]
                page = getattr(first_region, "page_number", 1) or 1
                polygon = getattr(first_region, "polygon", None)
            paragraphs.append(
                {
                    "page": page,
                    "role": getattr(paragraph, "role", None) or "body",
                    "content": content,
                    "bbox": _polygon_to_bbox(polygon),
                }
            )

        if not paragraphs and markdown:
            for idx, block in enumerate([item.strip() for item in markdown.split("\n\n") if item.strip()], start=1):
                paragraphs.append({"page": 1, "role": "body", "content": block, "bbox": None})

        return {"markdown": markdown, "paragraphs": paragraphs}

    def _normalize_fields(
        self,
        request: DocumentIntakeRequest,
        layout_result: Dict[str, Any],
    ) -> List[ExtractedField]:
        tool_schema = _field_extraction_tool_schema(request.profile)
        prompt_payload = {
            "document_id": request.document_id,
            "profile": request.profile.value,
            "locale": request.locale,
            "source_mime_type": request.source.mime_type,
            "extraction_instructions": _profile_instructions(request.profile),
            "layout_markdown": layout_result["markdown"][:24000],
            "page_paragraph_index": [
                {
                    "page": paragraph["page"],
                    "role": paragraph["role"],
                    "content": paragraph["content"][:500],
                }
                for paragraph in layout_result["paragraphs"][:80]
            ],
        }
        try:
            response = self._openai_client.chat.completions.create(
                model=self._settings.azure_openai_chat_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You normalize documents into typed fields. "
                            "Only return a tool call. Use evidence snippets directly from the source."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=True)},
                ],
                tools=[tool_schema],
                tool_choice={"type": "function", "function": {"name": "emit_document_fields"}},
            )
        except Exception as exc:  # pragma: no cover - exercised in live demo only
            raise LivePipelineError(f"Azure OpenAI normalization failed: {exc}") from exc

        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise LivePipelineError("Azure OpenAI returned no tool calls for normalization.")

        arguments = json.loads(tool_calls[0].function.arguments)
        fields: List[ExtractedField] = []
        for field_payload in arguments["fields"]:
            paragraph_match = _find_paragraph_match(layout_result["paragraphs"], field_payload["evidence_snippet"])
            fields.append(
                ExtractedField(
                    name=field_payload["name"],
                    value=field_payload.get("value"),
                    confidence=max(0.0, min(float(field_payload["confidence"]), 1.0)),
                    provenance=FieldProvenance(
                        page=field_payload.get("page") or paragraph_match.get("page", 1),
                        bbox=paragraph_match.get("bbox"),
                        snippet=field_payload.get("evidence_snippet"),
                    ),
                )
            )
        return fields

    def _build_chunks(self, request: DocumentIntakeRequest, layout_result: Dict[str, Any]) -> List[Chunk]:
        chunks: List[Chunk] = []
        bucket: List[str] = []
        current_page = 1
        current_section = "Document/Body"

        def flush_bucket() -> None:
            nonlocal bucket
            if not bucket:
                return
            text = "\n\n".join(bucket).strip()
            if not text:
                bucket = []
                return
            digest = hashlib.sha256(
                f"{request.document_id}:{current_page}:{current_section}:{text}".encode("utf-8")
            ).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=digest,
                    text=text,
                    section_path=current_section,
                    page=current_page,
                    char_start=0,
                    char_end=len(text),
                )
            )
            bucket = []

        for paragraph in layout_result["paragraphs"]:
            page = paragraph["page"]
            role = paragraph["role"]
            content = paragraph["content"]
            if page != current_page:
                flush_bucket()
                current_page = page
                current_section = f"Page {page}/Body"
            elif role in {"title", "sectionHeading"}:
                flush_bucket()
                current_section = f"Page {page}/{content[:60]}"

            bucket.append(content)
            if len("\n\n".join(bucket)) >= 900:
                flush_bucket()

        flush_bucket()
        return chunks

    def _embed_chunks(self, chunks: List[Chunk]) -> Dict[str, List[float]]:
        deployment = self._settings.azure_openai_embedding_deployment
        if not deployment or not chunks:
            return {}
        try:
            response = self._openai_client.embeddings.create(
                model=deployment,
                input=[chunk.text for chunk in chunks],
            )
        except Exception as exc:  # pragma: no cover - exercised in live demo only
            raise LivePipelineError(f"Azure OpenAI embeddings failed: {exc}") from exc

        output: Dict[str, List[float]] = {}
        for chunk, item in zip(chunks, response.data):
            output[chunk.chunk_id] = list(item.embedding)
        return output


def _resolve_source_payload(uri: str) -> tuple[str, str]:
    raw_value = str(uri)
    parsed = urlparse(raw_value)
    if parsed.scheme in {"http", "https"}:
        return "url", raw_value
    if parsed.scheme == "file":
        candidate = Path(unquote(parsed.path)).expanduser()
    else:
        candidate = Path(raw_value).expanduser()
    if not candidate.exists():
        raise LivePipelineError(f"Source document not found: {candidate}")
    return "file", str(candidate)


def _polygon_to_bbox(polygon: Any) -> List[float] | None:
    if not polygon:
        return None
    values = [float(value) for value in polygon]
    xs = values[0::2]
    ys = values[1::2]
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _find_paragraph_match(paragraphs: Iterable[Dict[str, Any]], snippet: str | None) -> Dict[str, Any]:
    if not snippet:
        return {"page": 1, "bbox": None}
    snippet_folded = snippet.casefold()
    for paragraph in paragraphs:
        if snippet_folded in paragraph["content"].casefold():
            return paragraph
    return {"page": 1, "bbox": None}


def _profile_instructions(profile: Profile) -> List[Dict[str, str]]:
    if profile == Profile.CONTRACT:
        return [
            {"name": "counterparty_name", "type": "string"},
            {"name": "effective_date", "type": "date"},
            {"name": "termination_notice_days", "type": "integer"},
        ]
    if profile == Profile.INVOICE:
        return [
            {"name": "invoice_number", "type": "string"},
            {"name": "currency", "type": "string"},
            {"name": "total_due_cents", "type": "integer"},
            {"name": "vendor_name", "type": "string"},
        ]
    if profile == Profile.MANUAL:
        return [
            {"name": "document_title", "type": "string"},
            {"name": "revision", "type": "string"},
            {"name": "requires_review_cycle", "type": "boolean"},
        ]
    return [
        {"name": "document_label", "type": "string"},
        {"name": "source_uri", "type": "string"},
    ]


def _field_extraction_tool_schema(profile: Profile) -> Dict[str, Any]:
    allowed_names = [item["name"] for item in _profile_instructions(profile)]
    return {
        "type": "function",
        "function": {
            "name": "emit_document_fields",
            "description": "Emit normalized fields for a document profile with evidence snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "enum": allowed_names},
                                "value": {
                                    "type": ["string", "number", "integer", "boolean", "null"],
                                },
                                "confidence": {"type": "number"},
                                "page": {"type": "integer"},
                                "evidence_snippet": {"type": "string"},
                            },
                            "required": ["name", "value", "confidence", "page", "evidence_snippet"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["fields"],
                "additionalProperties": False,
            },
        },
    }
