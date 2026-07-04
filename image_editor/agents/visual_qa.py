from __future__ import annotations

from image_editor.models import QAResult
from image_editor.state import ImageEditState


async def visual_qa(state: ImageEditState) -> dict:
    qa = QAResult(passed=True, score=1.0, issues=[], retry_suggestion="")
    return {"qa_result": qa.model_dump()}


def route_by_qa(state: ImageEditState) -> str:
    qa_data = state.get("qa_result")
    if not qa_data:
        return "pass"
    qa = QAResult(**qa_data)
    if qa.passed:
        return "pass"
    retry_count = state.get("retry_count", 0)
    if retry_count < 2:
        return "retry"
    return "fail"
