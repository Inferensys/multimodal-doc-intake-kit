from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl


class Profile(str, Enum):
    INVOICE = "invoice_v1"
    CONTRACT = "contract_v1"
    MANUAL = "manual_v1"
    GENERIC = "generic_v1"


class DocumentStatus(str, Enum):
    NORMALIZED = "normalized"
    REVIEW_PENDING = "review_pending"
    REVIEWED = "reviewed"
    EXPORTED = "exported"


ScalarValue = Union[str, int, float, bool, None]


class SourceDocument(BaseModel):
    uri: HttpUrl | str
    mime_type: Literal["application/pdf", "image/png", "image/jpeg", "application/tiff"]
    checksum_sha256: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class DocumentIntakeRequest(BaseModel):
    document_id: str = Field(pattern=r"^[a-zA-Z0-9._:-]{6,128}$")
    source: SourceDocument
    profile: Profile
    locale: str = "en-US"
    submitted_at: datetime
    metadata: Dict[str, ScalarValue] = Field(default_factory=dict)


class FieldProvenance(BaseModel):
    page: int = Field(ge=1)
    bbox: List[float] = Field(min_length=4, max_length=4)


class ExtractedField(BaseModel):
    name: str
    value: ScalarValue
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: FieldProvenance
    reviewed: bool = False
    review_reason_code: Optional[str] = None
    review_note: Optional[str] = None


class Chunk(BaseModel):
    chunk_id: str
    text: str = Field(min_length=1)
    section_path: str
    page: int = Field(ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class NormalizedDocument(BaseModel):
    document_id: str
    profile: Profile
    status: DocumentStatus
    source_checksum_sha256: Optional[str] = None
    extracted_fields: List[ExtractedField]
    chunks: List[Chunk]


class ReviewAction(str, Enum):
    ACCEPT = "accept"
    CORRECT = "correct"
    DROP = "drop"


class ReviewReasonCode(str, Enum):
    OCR_ERROR = "ocr_error"
    LAYOUT_MISALIGNMENT = "layout_misalignment"
    PARSER_MISS = "parser_miss"
    DOMAIN_OVERRIDE = "domain_override"


class FieldDecision(BaseModel):
    field_name: str
    action: ReviewAction
    corrected_value: Optional[ScalarValue] = None
    reason_code: ReviewReasonCode
    note: Optional[str] = None


class ReviewDecision(BaseModel):
    document_id: str
    reviewer_id: str
    field_decisions: List[FieldDecision] = Field(min_length=1)
    submitted_at: datetime


class DocumentRecord(BaseModel):
    intake: DocumentIntakeRequest
    normalized: NormalizedDocument
    last_review: Optional[ReviewDecision] = None

