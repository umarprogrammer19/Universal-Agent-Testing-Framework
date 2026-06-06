from .base import BaseAgentAdapter


class AdapterFactory:
    """Instantiate the correct adapter from a model-type string."""

    @staticmethod
    async def create(model_type: str) -> BaseAgentAdapter:
        """
        Parameters
        ----------
        model_type : str
            One of ``'gemini'``, ``'gpt-4'``, or ``'claude'``.

        Returns
        -------
        BaseAgentAdapter
            A ready-to-use adapter instance.

        Raises
        ------
        ValueError
            If *model_type* is not recognised.
        """
        key = model_type.strip().lower()

        if key == "gemini":
            from .gemini_adapter import GeminiAdapter
            return GeminiAdapter()

        if key == "gpt-4":
            from .openai_adapter import OpenAIAdapter
            return OpenAIAdapter(model="gpt-4-turbo")

        if key == "claude":
            from .claude_adapter import ClaudeAdapter
            return ClaudeAdapter(model="claude-3.5-sonnet")

        raise ValueError(
            f"Unknown model_type '{model_type}'. "
            "Supported values: 'gemini', 'gpt-4', 'claude'."
        )
