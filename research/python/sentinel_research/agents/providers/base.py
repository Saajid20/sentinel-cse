from __future__ import annotations

import abc


class BaseLLMProvider(abc.ABC):
    """Abstract base for LLM providers that supply context/risk analysis.

    This class defines the interface for sending a document and a prompt
    to an LLM and receiving raw text output. It does NOT:
    - Parse or validate JSON output.
    - Interact with brokers or order placement.
    - Generate trading signals or recommendations.

    JSON parsing and schema validation MUST be performed by the caller
    (e.g., the R10 orchestrator) after the provider returns raw output.
    """

    @abc.abstractmethod
    def analyze_context(self, document: str, prompt: str) -> str:
        """Send *document* and *prompt* to the LLM and return raw text.

        Parameters
        ----------
        document : str
            The source text to analyze (e.g., a news article).
        prompt : str
            System-level instructions describing the analysis task.

        Returns
        -------
        str
            Raw provider output (typically JSON text). The caller is
            responsible for parsing and schema validation.
        """
        ...
