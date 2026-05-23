from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_ROOT))

from sentinel_research.agents import ContextAgent, DeepSeekProvider, R10AnalysisError  # noqa: E402


def main() -> int:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("R10 smoke test requires DEEPSEEK_API_KEY to be set in the environment.")
        return 1

    provider = DeepSeekProvider(api_key=api_key)
    agent = ContextAgent(provider)

    mock_document = (
        "COLOMBO (News 1st) - The Central Bank of Sri Lanka (CBSL) has announced "
        "an unexpected reduction in the SDFR and SLFR by 50 basis points, citing "
        "lowering inflation. Banking sector stocks are expected to see margin "
        "compression, but overall market liquidity will increase."
    )
    sources = [
        {
            "source_type": "CBSL",
            "title": "Mock CBSL policy rate reduction article",
            "url": None,
            "published_at": None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    try:
        analysis = agent.process_document(document=mock_document, sources=sources)
    except R10AnalysisError as error:
        print(f"R10 smoke test failed validation: {error}")
        return 2
    except Exception as error:
        print(f"R10 smoke test failed unexpectedly: {error}")
        return 3

    print(analysis.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
