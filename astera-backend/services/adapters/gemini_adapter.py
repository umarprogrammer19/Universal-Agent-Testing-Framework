import os
import asyncio
from typing import Any

import google.generativeai as genai
from dotenv import load_dotenv

from .base import BaseAgentAdapter

load_dotenv()


class GeminiAdapter(BaseAgentAdapter):
    """Adapter that wraps Google Gemini 2.0 Flash via the generativeai SDK."""

    _MODEL_NAME = "gemini-2.0-flash"
    _DISPLAY_NAME = "Gemini 2.0 Flash"

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set in the environment / .env file.")
        genai.configure(api_key=api_key)

    async def get_model_name(self) -> str:
        return self._DISPLAY_NAME

    async def run_with_trace(self, prompt: str, tools: list) -> dict:
        """
        Drive a Gemini agentic loop and return a normalised trace dict.

        Parameters
        ----------
        prompt : str
            The user message / task description.
        tools : list
            Each item may be a raw Gemini tool declaration (dict / FunctionDeclaration)
            or a framework test-case object that carries an ``expected_tool`` field.
            Objects that expose ``.expected_tool`` are used for divergence detection;
            the underlying tool declaration is passed to the model.
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

        model = genai.GenerativeModel(
            model_name=self._MODEL_NAME,
            tools=gemini_tools if gemini_tools else None,
        )

        # SDK calls are synchronous; run them in a thread pool so we stay async-safe
        chat = await asyncio.to_thread(model.start_chat)

        execution_trace: list[dict] = []
        step_counter = 0
        total_tokens = 0

        response = await asyncio.to_thread(chat.send_message, prompt)

        while True:
            # Accumulate tokens reported so far
            usage = getattr(response, "usage_metadata", None)
            current_total = getattr(usage, "total_token_count", 0) if usage else 0

            # Collect every function_call part in this response
            function_calls_found = False

            for part in response.parts:
                fc = getattr(part, "function_call", None)
                if fc is None:
                    continue

                function_calls_found = True
                tool_name: str = fc.name
                tool_params: dict = dict(fc.args) if fc.args else {}

                # Tokens consumed up to and including this step
                tokens_delta = current_total - total_tokens

                # Divergence check against the ordered expected_tools list
                expected = expected_tools[step_counter] if step_counter < len(expected_tools) else ""

                trace_step = self._build_step(
                    step=step_counter,
                    tool=tool_name,
                    params=tool_params,
                    response={},          # filled in below after mock call
                    tokens_this_step=tokens_delta,
                    expected_tool=expected,
                )

                # Send a mock function response so the agent loop can continue
                mock_result = {"result": f"mock response for {tool_name}"}
                function_response_part = genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"output": mock_result},
                    )
                )

                response = await asyncio.to_thread(
                    chat.send_message,
                    genai.protos.Content(
                        role="user",
                        parts=[function_response_part],
                    ),
                )

                # Update token delta now that we have the next response
                new_usage = getattr(response, "usage_metadata", None)
                new_total = getattr(new_usage, "total_token_count", 0) if new_usage else 0
                trace_step["response"] = mock_result
                trace_step["tokens_this_step"] = new_total - total_tokens
                total_tokens = new_total

                execution_trace.append(trace_step)
                step_counter += 1

            # No function calls in this response → the agent is done
            if not function_calls_found:
                # Capture any remaining tokens
                final_usage = getattr(response, "usage_metadata", None)
                total_tokens = (
                    getattr(final_usage, "total_token_count", total_tokens)
                    if final_usage
                    else total_tokens
                )
                break

        # Extract the final text answer
        final_response = response.text if hasattr(response, "text") else ""

        return self._build_result(
            final_response=final_response,
            execution_trace=execution_trace,
            token_usage=total_tokens,
        )
