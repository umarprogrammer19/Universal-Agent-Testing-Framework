import os
import asyncio
from typing import Any

from google import genai
from google.genai import types
from dotenv import load_dotenv

from .base import BaseAgentAdapter

load_dotenv()


class GeminiAdapter(BaseAgentAdapter):
    """Adapter that wraps Google Gemini 2.0 Flash via the google-genai SDK."""

    _MODEL_NAME = "gemini-2.0-flash"
    _DISPLAY_NAME = "Gemini 2.0 Flash"

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set in the environment / .env file.")
        self._client = genai.Client(api_key=api_key)

    async def get_model_name(self) -> str:
        return self._DISPLAY_NAME

    async def run_with_trace(self, prompt: str, tools: list) -> dict:
        """
        Drive a Gemini agentic loop and return a normalised trace dict.

        tools: each item may carry an 'expected_tool' annotation for divergence
        detection. The underlying tool declaration is passed to the model.
        """
        # Separate expected_tool annotations from actual Gemini tool declarations
        expected_tools: list[str] = []
        gemini_tools: list[Any] = []
        for t in tools:
            if hasattr(t, "expected_tool"):
                expected_tools.append(t.expected_tool)
                gemini_tools.append(t.tool_declaration)
            elif isinstance(t, dict) and "expected_tool" in t:
                expected_tools.append(t["expected_tool"])
                gemini_tools.append(t.get("tool_declaration", t))
            else:
                expected_tools.append("")
                gemini_tools.append(t)

        config = types.GenerateContentConfig(
            tools=gemini_tools if gemini_tools else None,
        )

        execution_trace: list[dict] = []
        step_counter = 0
        total_tokens = 0

        # Build conversation history manually (new SDK uses stateless calls)
        contents: list[types.ContentUnion] = [
            types.Content(role="user", parts=[types.Part(text=prompt)])
        ]

        while True:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._MODEL_NAME,
                contents=contents,
                config=config,
            )

            # Token accounting
            usage = getattr(response, "usage_metadata", None)
            total_tokens = getattr(usage, "total_token_count", total_tokens) if usage else total_tokens

            # Append model turn to history
            contents.append(response.candidates[0].content)

            # Check for function calls in this response
            function_calls_found = False
            tool_response_parts: list[types.Part] = []

            for part in response.candidates[0].content.parts:
                fc = getattr(part, "function_call", None)
                if fc is None:
                    continue

                function_calls_found = True
                tool_name: str = fc.name
                tool_params: dict = dict(fc.args) if fc.args else {}

                expected = expected_tools[step_counter] if step_counter < len(expected_tools) else ""
                mock_result = {"result": f"mock response for {tool_name}"}

                trace_step = self._build_step(
                    step=step_counter,
                    tool=tool_name,
                    params=tool_params,
                    response=mock_result,
                    tokens_this_step=0,   # updated after full response round
                    expected_tool=expected,
                )
                execution_trace.append(trace_step)
                step_counter += 1

                # Build mock function response part
                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"output": mock_result},
                        )
                    )
                )

            if not function_calls_found:
                break

            # Append all tool responses as a single user turn
            contents.append(
                types.Content(role="user", parts=tool_response_parts)
            )

        # Extract final text
        final_response = ""
        try:
            final_response = response.text or ""
        except Exception:
            pass

        return self._build_result(
            final_response=final_response,
            execution_trace=execution_trace,
            token_usage=total_tokens,
        )
