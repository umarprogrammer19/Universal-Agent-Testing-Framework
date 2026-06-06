"""
services/llm_judge.py
LLM-as-a-Judge for semantic scoring of agent responses using google-genai SDK.
"""

import json
import os

from google import genai
from dotenv import load_dotenv

load_dotenv()

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")
        _client = genai.Client(api_key=api_key)
    return _client


async def judge_response(
    prompt: str,
    golden_response: str,
    actual_response: str,
) -> dict:
    """
    Score actual response against golden response using Gemini as judge.
    Returns: {"score": float (0-100), "label": str, "explanation": str}
    """

    judge_prompt = f"""You are a strict evaluation judge for AI agent responses.
Your job is to compare an actual response against a golden (ideal) response.

USER PROMPT:
{prompt}

GOLDEN RESPONSE (ideal answer):
{golden_response}

ACTUAL RESPONSE (what the agent produced):
{actual_response}

Score the ACTUAL response on these criteria:
- Relevance (0-40): Does it answer the user's prompt?
- Factual Accuracy (0-40): Are the facts correct compared to the golden response?
- No Hallucination (0-20): Does it invent information not in the golden response?

Total score = Relevance + Accuracy + No-Hallucination (0-100)

Respond with ONLY valid JSON, no markdown, no preamble:
{{"score": <number>, "label": "<Excellent|Good|Poor>", "explanation": "<one sentence>"}}

Label rules:
- Excellent: 80-100
- Good: 50-79
- Poor: 0-49
"""

    try:
        import asyncio
        client = _get_client()
        model = os.getenv("GEMINI_JUDGE_MODEL", "gemini-3.1-flash-lite")

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=judge_prompt,
        )

        response_text = response.text.strip()
        # Strip markdown fences if model wraps JSON anyway
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        parsed = json.loads(response_text)
        return {
            "score": float(parsed.get("score", 0)),
            "label": parsed.get("label", "Poor"),
            "explanation": parsed.get("explanation", "Judge response parse error"),
        }

    except json.JSONDecodeError:
        print("[ERROR] Judge JSON parse failed")
        return {"score": 0.0, "label": "Poor", "explanation": "Judge failed to parse response"}
    except Exception as e:
        print(f"[ERROR] Judge service error: {e}")
        return {"score": 0.0, "label": "Poor", "explanation": f"Judge error: {e}"}
