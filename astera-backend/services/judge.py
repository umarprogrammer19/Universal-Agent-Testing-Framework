"""
services/judge.py
Thin adapter so test_runner can call judge_response(prompt, golden=, actual=)
while the real implementation lives in llm_judge.py.
"""

from services.llm_judge import judge_response as _judge


async def judge_response(prompt: str, golden: str, actual: str) -> dict:
    """
    Wrapper that translates test_runner kwarg names → llm_judge param names
    and normalises the return key 'score' → 'semantic_score'.
    """
    result = await _judge(
        prompt=prompt,
        golden_response=golden,
        actual_response=actual,
    )
    return {
        "semantic_score": result["score"],
        "explanation": result["explanation"],
        "label": result["label"],
    }
