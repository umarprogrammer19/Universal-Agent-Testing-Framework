import os
from typing import Any

import httpx
from dotenv import load_dotenv

from .base import BaseAgentAdapter

load_dotenv()

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenAIAdapter(BaseAgentAdapter):
    """Adapter that routes GPT-4-Turbo requests through OpenRouter via httpx."""

    _DISPLAY_NAME = "GPT-4 Turbo"

    def __init__(self, model: str = "gpt-4-turbo") -> None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY is not set in the environment / .env file.")
        self._api_key = api_key
        self._model = model
        self._base_url = _OPENROUTER_BASE_URL

    async def get_model_name(self) -> str:
        return self._DISPLAY_NAME

    async def run_with_trace(self, prompt: str, tools: list) -> dict:
        """
        Drive a GPT-4-Turbo agentic loop via OpenRouter and return a normalised trace dict.

        Parameters
        ----------
        prompt : str
            The user message / task description.
        tools : list
            Each item may be a plain OpenAI function-schema dict, or a framework
            test-case object / dict that carries an ``expected_tool`` annotation.
        """
        # Separate expected_tool annotations from actual OpenAI tool declarations
        expected_tools: list[str] = []
        openai_tools: list[dict[str, Any]] = []

        for t in tools:
            if hasattr(t, "expected_tool"):
                expected_tools.append(t.expected_tool)
                raw = t.tool_declaration
            elif isinstance(t, dict) and "expected_tool" in t:
                expected_tools.append(t["expected_tool"])
                raw = t.get("tool_declaration", t)
            else:
                expected_tools.append("")
                raw = t

            # Wrap bare function schemas in the OpenAI tool envelope
            if isinstance(raw, dict) and raw.get("type") == "function":
                openai_tools.append(raw)
            else:
                openai_tools.append({"type": "function", "function": raw})

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        execution_trace: list[dict] = []
        step_counter = 0
        total_tokens = 0

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            while True:
                payload: dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                }
                if openai_tools:
                    payload["tools"] = openai_tools

                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                # Token accounting — cumulative running total
                usage = data.get("usage", {})
                total_tokens = usage.get("total_tokens", total_tokens)

                choice = data["choices"][0]
                finish_reason: str = choice.get("finish_reason", "stop")
                assistant_message: dict[str, Any] = choice["message"]

                if finish_reason == "tool_calls":
                    tool_calls: list[dict] = assistant_message.get("tool_calls", [])

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        tool_name: str = fn.get("name", "")

                        # Arguments come back as a JSON string from the API
                        import json as _json
                        raw_args = fn.get("arguments", "{}")
                        try:
                            tool_params: dict = _json.loads(raw_args)
                        except _json.JSONDecodeError:
                            tool_params = {"raw": raw_args}

                        expected = (
                            expected_tools[step_counter]
                            if step_counter < len(expected_tools)
                            else ""
                        )

                        mock_result = {"result": f"mock response for {tool_name}"}

                        trace_step = self._build_step(
                            step=step_counter,
                            tool=tool_name,
                            params=tool_params,
                            response=mock_result,
                            tokens_this_step=usage.get("completion_tokens", 0),
                            expected_tool=expected,
                        )
                        execution_trace.append(trace_step)
                        step_counter += 1

                    # Append the assistant turn that triggered the tool calls
                    messages.append(assistant_message)

                    # Append mock tool results for every call so the model can continue
                    for tc in tool_calls:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": "mock tool result",
                            }
                        )

                else:
                    # finish_reason == 'stop' (or any non-tool-call terminal state)
                    final_response: str = assistant_message.get("content") or ""
                    break

        return self._build_result(
            final_response=final_response,
            execution_trace=execution_trace,
            token_usage=total_tokens,
        )
