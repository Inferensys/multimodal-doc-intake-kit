from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from .models import DocumentRecord


class InMemoryDocumentStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: Dict[str, DocumentRecord] = {}

    def save(self, record: DocumentRecord) -> None:
        with self._lock:
            self._items[record.intake.document_id] = record

    def get(self, document_id: str) -> Optional[DocumentRecord]:
        with self._lock:
            return self._items.get(document_id)

