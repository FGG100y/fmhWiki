from __future__ import annotations

import base64
import io
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image as PILImage

from painterAgent.config import config
from painterAgent.errors import to_user_error
from painterAgent.models import (
    CreateTurnRequest,
    CreateTurnResponse,
    JobStatus,
    ReplayTurnRequest,
    SessionResponse,
    SwitchTurnRequest,
    TurnDetailResponse,
    UploadResponse,
)
from painterAgent.storage import store
from painterAgent.workflow import run_workflow

logger = logging.getLogger(__name__)


app = FastAPI(title="多轮修图 Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Session ----


@app.post("/projects/{project_id}/sessions")
async def create_session(project_id: str, user_id: str = "default") -> dict:
    session = store.create_session(project_id=project_id, user_id=user_id)
    return session


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionResponse:
    result = store.get_session_with_turns(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="session not found")
    return result


# ---- Turn / Edit ----


@app.post("/sessions/{session_id}/turns", response_model=CreateTurnResponse)
async def create_turn(session_id: str, req: CreateTurnRequest) -> CreateTurnResponse:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    turn = store.create_turn(
        session_id=session_id,
        user_instruction=req.instruction,
        parent_turn_id=req.current_turn_id,
        status=JobStatus.queued.value,
    )
    job_id = store.create_job(session_id=session_id, turn_id=turn.turn_id)

    return CreateTurnResponse(
        job_id=job_id,
        turn_id=turn.turn_id,
        status=JobStatus.queued.value,
    )


@app.get("/turns/{turn_id}")
async def get_turn(turn_id: str) -> TurnDetailResponse:
    detail = store.get_turn_detail(turn_id)
    if not detail:
        raise HTTPException(status_code=404, detail="turn not found")
    return detail


# ---- Undo / Redo ----


@app.post("/sessions/{session_id}/undo")
async def undo_turn(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    parent_id = store.undo(session_id)
    return {"current_turn_id": parent_id}


@app.post("/sessions/{session_id}/redo")
async def redo_turn(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"current_turn_id": store.redo(session_id)}


@app.post("/sessions/{session_id}/switch-current-turn")
async def switch_current_turn(session_id: str, req: SwitchTurnRequest) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    turn = store.get_turn(req.turn_id)
    if not turn or turn.session_id != session_id:
        raise HTTPException(status_code=404, detail="turn not found in session")
    store.switch_current_turn(session_id, req.turn_id)
    return {"current_turn_id": req.turn_id}


@app.delete("/sessions/{session_id}/turns/{turn_id}")
async def delete_turn(session_id: str, turn_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    turn = store.get_turn(turn_id)
    if not turn or turn.session_id != session_id:
        raise HTTPException(status_code=404, detail="turn not found in session")
    store.delete_turn(turn_id)
    return {"deleted": True}


# ---- Job ----


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    """取消一个正在运行或排队的Job。"""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    
    # 只能取消 queued 或 running 状态的 job
    if job.status not in [JobStatus.queued.value, JobStatus.running.value]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status}"
        )
    
    # 更新 job 状态为 cancelled
    store.update_job(job_id, status=JobStatus.cancelled.value)
    
    # 同时更新对应的 turn 状态
    turn = store.get_turn(job.turn_id)
    if turn:
        store.update_turn(job.turn_id, status=JobStatus.cancelled.value)
    
    logger.info("cancel_job: job=%s turn=%s", job_id, job.turn_id)
    return {"job_id": job_id, "status": JobStatus.cancelled.value}


@app.get("/sessions/{session_id}/model-calls")
async def list_session_model_calls(session_id: str) -> list[dict]:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    rows = store.list_model_calls(session_id=session_id)
    return [r.model_dump() for r in rows]


@app.get("/turns/{turn_id}/model-calls")
async def list_turn_model_calls(turn_id: str) -> list[dict]:
    turn = store.get_turn(turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="turn not found")
    rows = store.list_model_calls(turn_id=turn_id)
    return [r.model_dump() for r in rows]


# ---- Upload ----

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
UPLOAD_MAX_SIZE = 1 * 1024 * 1024  # 1MB
UPLOAD_MAX_DIMENSION = 2048


def _compress_image(content: bytes, ext: str) -> tuple[bytes, str, str, int, int]:
    """按需压缩图片，返回 (final_bytes, mime_type, final_ext, width, height)"""
    img = PILImage.open(io.BytesIO(content))
    width, height = img.size

    # 小图片（< 1MB）→ 不压缩，保持原格式
    if len(content) < UPLOAD_MAX_SIZE:
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "image/png")
        return content, mime, ext, width, height

    logger.info("compressing large image: original_size=%dKB", len(content) // 1024)

    # 大图片 → 压缩
    if width > UPLOAD_MAX_DIMENSION or height > UPLOAD_MAX_DIMENSION:
        ratio = min(UPLOAD_MAX_DIMENSION / width, UPLOAD_MAX_DIMENSION / height)
        new_w, new_h = int(width * ratio), int(height * ratio)
        img = img.resize((new_w, new_h), PILImage.LANCZOS)
        width, height = new_w, new_h

    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85)
    compressed = buf.getvalue()

    logger.info(
        "compressed: %dx%d, final_size=%dKB",
        width,
        height,
        len(compressed) // 1024,
    )
    return compressed, "image/jpeg", ".jpg", width, height


@app.post("/upload", response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...), request: Request = None):
    ext = Path(file.filename or "image.png").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type: {ext}, allowed: {ALLOWED_EXTENSIONS}",
        )

    raw_content = await file.read()

    try:
        final_content, mime, final_ext, width, height = _compress_image(
            raw_content, ext
        )
    except Exception:
        raise HTTPException(status_code=400, detail="invalid image file")

    image_id = f"img_{uuid.uuid4().hex[:12]}"
    local_filename = f"{image_id}{final_ext}"
    local_path = _upload_dir / local_filename
    local_path.write_bytes(final_content)

    encoded = base64.b64encode(final_content).decode("ascii")
    image_url = f"data:{mime};base64,{encoded}"

    store.save_image(
        image_id,
        image_url,
        metadata={
            "asset_type": "upload",
            "filename": file.filename,
            "width": width,
            "height": height,
            "local_url": f"/uploads/{local_filename}",
        },
    )

    logger.info(
        "upload_image: id=%s filename=%s size=%dx%d mime=%s",
        image_id,
        file.filename,
        width,
        height,
        mime,
    )
    return UploadResponse(
        image_id=image_id,
        image_url=image_url,
        filename=file.filename or "",
        width=width,
        height=height,
    )


# ---- Execute (Async -- Job Queue) ----


@app.post("/sessions/{session_id}/execute")
async def execute_turn(session_id: str, req: CreateTurnRequest) -> dict:
    """异步执行工作流 — 创建 job 入队，立即返回 job_id/turn_id。"""
    logger.info(
        "execute_turn: session=%s instruction=%s has_mask=%s mask_image_id=%s",
        session_id, req.instruction[:80], bool(req.mask_image_id), req.mask_image_id,
    )
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    # 上传图片时创建根 turn 代表原始图，使其出现在编辑历史中
    if req.uploaded_image_id:
        uploaded_img = store.get_image(req.uploaded_image_id)
        if not uploaded_img:
            raise HTTPException(status_code=404, detail="uploaded image not found")
        root_turn = store.create_turn(
            session_id=session_id,
            user_instruction="[原图]",
            parent_turn_id=None,
            status=JobStatus.succeeded.value,
        )
        store.update_turn(
            root_turn.turn_id,
            input_image_id=req.uploaded_image_id,
            output_image_id=req.uploaded_image_id,
        )
        store.switch_current_turn(session_id, root_turn.turn_id)
        parent_turn_id = root_turn.turn_id
    else:
        parent_turn_id = req.current_turn_id or session.get("current_turn_id")

    turn = store.create_turn(
        session_id=session_id,
        user_instruction=req.instruction,
        parent_turn_id=parent_turn_id,
        status=JobStatus.queued.value,
    )
    if req.mask_image_id:
        store.update_turn(turn.turn_id, mask_image_id=req.mask_image_id)
    job_id = store.create_job(session_id=session_id, turn_id=turn.turn_id)

    # 确定当前图片：上传图片优先，否则用上一轮的输出
    if req.uploaded_image_id:
        uploaded_img = store.get_image(req.uploaded_image_id)
        if not uploaded_img:
            raise HTTPException(status_code=404, detail="uploaded image not found")
        current_image_id = req.uploaded_image_id
        current_image_url = uploaded_img.get("url", "")
    else:
        current_turn = None
        if req.current_turn_id:
            current_turn = store.get_turn(req.current_turn_id)
        elif session.get("current_turn_id"):
            current_turn = store.get_turn(session["current_turn_id"])
        current_image_id = current_turn.output_image_id if current_turn else None
        current_image_url = (
            store.get_image(current_turn.output_image_id or "").get("url")
            if current_turn and current_turn.output_image_id
            else None
        )

    # 解析 mask_image_id → mask_image_url
    mask_image_url = None
    if req.mask_image_id:
        mask_img = store.get_image(req.mask_image_id)
        if mask_img:
            mask_image_url = mask_img.get("url", "")

    # 入队异步任务
    from painterAgent.worker import execute_workflow

    execution_mode = req.options.get("mode", "auto") if req.options else "auto"

    execute_workflow.send(
        session_id=session_id,
        turn_id=turn.turn_id,
        job_id=job_id,
        user_id=session.get("user_id", "default"),
        project_id=session["project_id"],
        instruction=req.instruction,
        current_turn_id=turn.parent_turn_id,
        current_image_id=current_image_id,
        current_image_url=current_image_url,
        reference_image_ids=req.reference_image_ids,
        mask_image_id=req.mask_image_id,
        mask_image_url=mask_image_url,
        execution_mode=execution_mode,
    )

    logger.info("execute_turn: queued job=%s turn=%s", job_id, turn.turn_id)
    return {
        "job_id": job_id,
        "turn_id": turn.turn_id,
        "status": JobStatus.queued.value,
    }


@app.post("/sessions/{session_id}/replay")
async def replay_turn(session_id: str, req: ReplayTurnRequest) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    source_turn = store.get_turn(req.from_turn_id)
    if not source_turn or source_turn.session_id != session_id:
        raise HTTPException(status_code=404, detail="source turn not found")

    parent_turn = (
        store.get_turn(source_turn.parent_turn_id)
        if source_turn.parent_turn_id
        else None
    )
    current_image_id = parent_turn.output_image_id if parent_turn else None
    current_image_url = (
        store.get_image(current_image_id).get("url")
        if current_image_id and store.get_image(current_image_id)
        else None
    )

    replay_req = CreateTurnRequest(
        instruction=source_turn.user_instruction,
        current_turn_id=source_turn.parent_turn_id,
        reference_image_ids=source_turn.reference_image_ids,
        mask_image_id=source_turn.mask_image_id,
        options={
            "replay_from_turn_id": source_turn.turn_id,
            "replay_reason": "manual_replay",
        },
    )

    # 解析 mask_image_id → mask_image_url
    mask_image_url = None
    if replay_req.mask_image_id:
        mask_img = store.get_image(replay_req.mask_image_id)
        if mask_img:
            mask_image_url = mask_img.get("url", "")

    turn = store.create_turn(
        session_id=session_id,
        user_instruction=replay_req.instruction,
        parent_turn_id=replay_req.current_turn_id,
        status=JobStatus.running.value,
    )
    if replay_req.mask_image_id:
        store.update_turn(turn.turn_id, mask_image_id=replay_req.mask_image_id)
    job_id = store.create_job(session_id=session_id, turn_id=turn.turn_id)

    try:
        result = await run_workflow(
            user_id=session.get("user_id", "default"),
            project_id=session["project_id"],
            session_id=session_id,
            instruction=replay_req.instruction,
            current_turn_id=replay_req.current_turn_id,
            current_image_id=current_image_id,
            current_image_url=current_image_url,
            reference_image_ids=replay_req.reference_image_ids,
            mask_image_id=replay_req.mask_image_id,
            mask_image_url=mask_image_url,
            turn_id=turn.turn_id,
        )
        if result.get("error"):
            code, friendly = to_user_error(result["error"])
            store.update_job(
                job_id, status=JobStatus.failed.value, error_message=result["error"]
            )
            store.update_turn(turn.turn_id, status="failed", error_message=friendly)
            return {
                "job_id": job_id,
                "turn_id": turn.turn_id,
                "error_code": code,
                "error": friendly,
            }
        store.update_job(job_id, status=JobStatus.succeeded.value)
        return {"job_id": job_id, "turn_id": turn.turn_id, **result}
    except Exception as e:
        code, friendly = to_user_error(str(e))
        store.update_job(job_id, status=JobStatus.failed.value, error_message=str(e))
        store.update_turn(turn.turn_id, status="failed", error_message=friendly)
        return {
            "job_id": job_id,
            "turn_id": turn.turn_id,
            "error_code": code,
            "error": friendly,
        }


_output_dir = Path(config.image_tool.output_dir)
_output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(_output_dir)), name="output")

_upload_dir = Path(config.image_tool.upload_dir)
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")

_frontend_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True))
