from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from sentinel_research.agents.documents import SourceDocument
from sentinel_research.agents.ingestion.base import DocumentSource


def _load_json_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error


class JsonFileDocumentSource(DocumentSource):
    def __init__(self, path: str | Path, name: str | None = None) -> None:
        self._path = Path(path)
        self.name = name or self._path.stem

    def fetch(self) -> list[SourceDocument]:
        if not self._path.exists():
            raise FileNotFoundError(self._path)

        payload = _load_json_file(self._path)
        try:
            document = SourceDocument.model_validate(payload)
        except ValidationError as error:
            raise ValueError(
                f"Invalid SourceDocument in {self._path}: {error}"
            ) from error
        return [document]


class DirectoryJsonDocumentSource(DocumentSource):
    def __init__(
        self,
        directory: str | Path,
        pattern: str = "*.json",
        name: str | None = None,
    ) -> None:
        self._directory = Path(directory)
        self._pattern = pattern
        self.name = name or self._directory.name or "json-directory"

    def fetch(self) -> list[SourceDocument]:
        if not self._directory.exists():
            raise FileNotFoundError(self._directory)

        documents: list[SourceDocument] = []
        for path in sorted(self._directory.glob(self._pattern)):
            if not path.is_file():
                continue
            payload = _load_json_file(path)
            try:
                document = SourceDocument.model_validate(payload)
            except ValidationError as error:
                raise ValueError(
                    f"Invalid SourceDocument in {path}: {error}"
                ) from error
            documents.append(document)

        return documents
