"""Dramatiq worker — 执行 LangGraph workflow"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import dramatiq

from image_editor.tasks import _broker  # noqa: F401 — 触发 broker 配置
from image_editor.errors import to_user_error
from image_editor.models import JobStatus
from image_editor.storage import store
from image_editor.workflow import run_workflow

logger = logging.getLogger(__name__)


@dramatiq.actor(queue_name="image_jobs", max_retries=3, min_backoff=10000, max_backoff=300000)
def execute_workflow(
    session_id: str,
    turn_id: str,
    job_id: str,
    user_id: str = "default",
    project_id: str = "default",
    instruction: str = "",
    current_turn_id: str | None = None,
    current_image_id: str | None = None,
    current_image_url: str | None = None,
    reference_image_ids: list[str] | None = None,
    mask_image_id: str | None = None,
) -> None:
    """执行 LangGraph workflow 并更新任务状态"""
    logger.info("execute_workflow: job=%s turn=%s instruction=%s", job_id, turn_id, instruction[:80])

    # 更新状态为 running
    store.update_job(job_id, status=JobStatus.running.value)
    store.update_turn(turn_id, status=JobStatus.running.value)

    try:
        # 运行异步 workflow
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                run_workflow(
                    user_id=user_id,
                    project_id=project_id,
                    session_id=session_id,
                    instruction=instruction,
                    current_turn_id=current_turn_id,
                    current_image_id=current_image_id,
                    current_image_url=current_image_url,
                    reference_image_ids=reference_image_ids,
                    mask_image_id=mask_image_id,
                    turn_id=turn_id,
                )
            )
        finally:
            loop.close()

        # 检查结果
        if result.get("error"):
            code, friendly = to_user_error(result["error"])
            logger.warning("execute_workflow: failed job=%s code=%s", job_id, code)
            store.update_job(job_id, status=JobStatus.failed.value, error_message=result["error"])
            store.update_turn(turn_id, status="failed", error_message=friendly)
        else:
            logger.info("execute_workflow: succeeded job=%s turn=%s", job_id, turn_id)
            store.update_job(job_id, status=JobStatus.succeeded.value)
            store.update_turn(turn_id, status=JobStatus.succeeded.value)

    except Exception as e:
        code, friendly = to_user_error(str(e))
        logger.error("execute_workflow: exception job=%s error=%s", job_id, e)
        store.update_job(job_id, status=JobStatus.failed.value, error_message=str(e))
        store.update_turn(turn_id, status="failed", error_message=friendly)
        raise  # 让 dramatiq 重试


if __name__ == "__main__":
    # 启动 worker
    import dramatiq.cli

    sys.argv = ["dramatiq", "image_editor.worker", "--processes", "1", "--threads", "4"]
    dramatiq.cli.main()
