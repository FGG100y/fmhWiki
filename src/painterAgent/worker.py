"""Dramatiq worker — 执行 LangGraph workflow"""

from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


class TruncatingFilter(logging.Filter):
    """截断过长日志消息（避免 base64 图片撑满日志）"""
    MAX_LEN = 500
    def filter(self, record: logging.LogRecord) -> bool:
        if len(record.msg) > self.MAX_LEN:
            record.msg = f"{record.msg[:self.MAX_LEN]}...<truncated {len(record.msg) - self.MAX_LEN} chars>"
        return True


# ── Worker 日志配置 ────────────────────────────────────────────────────────────
_logs_dir = Path(__file__).parent.parent / "logs"
_logs_dir.mkdir(parents=True, exist_ok=True)

_log_fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = RotatingFileHandler(
    _logs_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_log_fmt)
_file_handler.addFilter(TruncatingFilter())

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_fmt)
_console_handler.addFilter(TruncatingFilter())

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_console_handler)

logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("dramatiq").setLevel(logging.WARNING)
# ────────────────────────────────────────────────────────────────────────────────

import dramatiq

from painterAgent.tasks import _broker  # noqa: F401 — 触发 broker 配置
from painterAgent.errors import to_user_error
from painterAgent.models import JobStatus
from painterAgent.storage import store
from painterAgent.workflow import run_workflow

logger = logging.getLogger(__name__)


def _cleanup_gpu() -> None:
    """释放 GPU 显存（Moebius 等本地模型用完后清理）"""
    try:
        import gc
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            gc.collect()
            torch.cuda.empty_cache()
    except ImportError:
        pass


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
    mask_image_url: str | None = None,
) -> None:
    """执行 LangGraph workflow 并更新任务状态"""
    logger.info(
        "execute_workflow: job=%s turn=%s instruction=%s has_mask=%s mask_image_id=%s",
        job_id, turn_id, instruction[:80], bool(mask_image_url), mask_image_id,
    )

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
                    mask_image_url=mask_image_url,
                    turn_id=turn_id,
                )
            )
        finally:
            loop.close()
            # 释放 GPU 显存，避免多轮推理后 OOM
            _cleanup_gpu()

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

    sys.argv = ["dramatiq", "painterAgent.worker", "--processes", "1", "--threads", "2"]
    dramatiq.cli.main()
