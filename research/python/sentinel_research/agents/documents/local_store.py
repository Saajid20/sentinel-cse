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
