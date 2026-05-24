from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from sentinel_research.agents.documents.document_model import SourceDocument


class LocalDocumentStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def append(self, document: SourceDocument) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(document.model_dump_json())
            handle.write("\n")

    def append_many(self, documents: list[SourceDocument]) -> None:
        if not documents:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            for document in documents:
                handle.write(document.model_dump_json())
                handle.write("\n")

    def exists(self, document_id: str) -> bool:
        normalized_document_id = self._normalize_document_id(document_id)
        return any(
            document.document_id == normalized_document_id
            for document in self.load_all()
        )

    def load_by_id(self, document_id: str) -> SourceDocument | None:
        normalized_document_id = self._normalize_document_id(document_id)
        for document in self.load_all():
            if document.document_id == normalized_document_id:
                return document
        return None

    def upsert(self, document: SourceDocument) -> None:
        self.upsert_many([document])

    def upsert_many(self, documents: list[SourceDocument]) -> None:
        if not documents:
            return

        stored_documents = self.load_all()
        stored_index = {
            document.document_id: index for index, document in enumerate(stored_documents)
        }
        new_document_order: list[str] = []
        new_documents_by_id: dict[str, SourceDocument] = {}

        for document in documents:
            existing_index = stored_index.get(document.document_id)
            if existing_index is not None:
                stored_documents[existing_index] = document
                continue
            if document.document_id not in new_documents_by_id:
                new_document_order.append(document.document_id)
            new_documents_by_id[document.document_id] = document

        stored_documents.extend(
            new_documents_by_id[document_id] for document_id in new_document_order
        )
        self._write_all(stored_documents)

    def load_all(self) -> list[SourceDocument]:
        if not self._path.exists():
            return []

        documents: list[SourceDocument] = []
        for line_number, raw_line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in document store at line {line_number}: {error}"
                ) from error
            try:
                documents.append(SourceDocument.model_validate(payload))
            except ValidationError as error:
                raise ValueError(
                    f"Invalid SourceDocument in document store at line {line_number}: {error}"
                ) from error

        return documents

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def _write_all(self, documents: list[SourceDocument]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8", newline="\n") as handle:
            for document in documents:
                handle.write(document.model_dump_json())
                handle.write("\n")

    @staticmethod
    def _normalize_document_id(document_id: str) -> str:
        normalized_document_id = document_id.strip()
        if not normalized_document_id:
            raise ValueError("document_id must not be empty")
        return normalized_document_id
