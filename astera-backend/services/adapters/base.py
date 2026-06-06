from abc import ABC, abstractmethod
from typing import Optional


class BaseAgentAdapter(ABC):
    """
    Abstract base for all LLM adapters.

    Every concrete adapter (Gemini, OpenAI, Claude) must return the exact
    same dict shape from run_with_trace so the framework can compare results
    across models without special-casing anything.
    """

    @abstractmethod
    async def run_with_trace(self, prompt: str, tools: list) -> dict:
        """
        Execute the prompt with the given tools and return a standardised trace.

        Returns
        -------
        {
            'final_response': str,
            'execution_trace': [
                {
                    'step': int,
                    'tool': str,
                    'params': dict,
                    'response': dict,
                    'tokens_this_step': int,
                    'expected_tool': str,       # from test-case expected_tools
                    'is_divergence': bool,
                    'divergence_reason': str | None
                },
                ...
            ],
            'token_usage': int
        }
        """

    @abstractmethod
    async def get_model_name(self) -> str:
        """Return a human-readable model name, e.g. 'Gemini 2.0 Flash'."""

    # ------------------------------------------------------------------
    # Helpers shared by all adapters
    # ------------------------------------------------------------------

    @staticmethod
    def _build_step(
        step: int,
        tool: str,
        params: dict,
        response: dict,
        tokens_this_step: int,
        expected_tool: str = "",
    ) -> dict:
        """Build a single normalised trace step."""
        is_divergence = bool(expected_tool) and tool != expected_tool
        divergence_reason: Optional[str] = (
            f"Expected '{expected_tool}' but model called '{tool}'"
            if is_divergence
            else None
        )
        return {
            "step": step,
            "tool": tool,
            "params": params,
            "response": response,
            "tokens_this_step": tokens_this_step,
            "expected_tool": expected_tool,
            "is_divergence": is_divergence,
            "divergence_reason": divergence_reason,
        }

    @staticmethod
    def _build_result(
        final_response: str,
        execution_trace: list,
        token_usage: int,
    ) -> dict:
        """Assemble the top-level result dict."""
        return {
            "final_response": final_response,
            "execution_trace": execution_trace,
            "token_usage": token_usage,
        }
