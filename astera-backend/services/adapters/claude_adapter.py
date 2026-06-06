from .openai_adapter import OpenAIAdapter


class ClaudeAdapter(OpenAIAdapter):
    """
    Adapter for Claude via OpenRouter.

    OpenRouter exposes a unified OpenAI-compatible REST interface, so the
    entire agentic loop (tool calls, token accounting, trace building) is
    inherited unchanged from OpenAIAdapter — only the model identifier and
    display name differ.
    """

    _DISPLAY_NAME = "Claude 3.5 Sonnet"

    def __init__(self, model: str = "anthropic/claude-3.5-sonnet") -> None:
        super().__init__(model=model)

    async def get_model_name(self) -> str:
        return self._DISPLAY_NAME
