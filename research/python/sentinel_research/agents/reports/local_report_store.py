from __future__ import annotations

from pathlib import Path

from sentinel_research.agents.reports.report_model import R10AnalysisReport


class LocalReportStore:
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def save(self, report: R10AnalysisReport) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{report.report_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        return path

    def load(self, path: str | Path) -> R10AnalysisReport:
        return R10AnalysisReport.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def list_reports(self, pattern: str = "*.json") -> list[Path]:
        if not self._directory.exists():
            return []
        return sorted(path for path in self._directory.glob(pattern) if path.is_file())

    def clear(self) -> None:
        if not self._directory.exists():
            return
        for path in self._directory.glob("*.json"):
            if path.is_file():
                path.unlink()
