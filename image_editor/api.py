from __future__ import annotations

import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from image_editor.models import (
    CreateTurnRequest,
    CreateTurnResponse,
    JobStatus,
    SessionResponse,
    TurnDetailResponse,
)
from image_editor.storage import store
from image_editor.workflow import run_workflow

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
    current = session.get("current_turn_id")
    if not current:
        return {"current_turn_id": None}
    turn = store.get_turn(current)
    parent_id = turn.parent_turn_id if turn else None
    if session:
        session["current_turn_id"] = parent_id
    return {"current_turn_id": parent_id}


@app.post("/sessions/{session_id}/redo")
async def redo_turn(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"current_turn_id": session.get("current_turn_id")}


# ---- Job ----

@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


# ---- Execute (Async -- 实际生产应通过 Job Queue) ----

@app.post("/sessions/{session_id}/execute")
async def execute_turn(session_id: str, req: CreateTurnRequest) -> dict:
    """同步执行工作流（开发/演示用）。生产环境应异步调用。"""
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    turn = store.create_turn(
        session_id=session_id,
        user_instruction=req.instruction,
        parent_turn_id=req.current_turn_id or session.get("current_turn_id"),
    )
    job_id = store.create_job(session_id=session_id, turn_id=turn.turn_id)

    # 获取当前图片信息
    current_turn = None
    if req.current_turn_id:
        current_turn = store.get_turn(req.current_turn_id)
    elif session.get("current_turn_id"):
        current_turn = store.get_turn(session["current_turn_id"])

    try:
        result = await run_workflow(
            user_id=session.get("user_id", "default"),
            project_id=session["project_id"],
            session_id=session_id,
            instruction=req.instruction,
            current_turn_id=turn.parent_turn_id,
            current_image_id=current_turn.output_image_id if current_turn else None,
            current_image_url=(
                store.get_image(current_turn.output_image_id or "").get("url")
                if current_turn and current_turn.output_image_id
                else None
            ),
            reference_image_ids=req.reference_image_ids,
            mask_image_id=req.mask_image_id,
        )
        store.update_job(job_id, status=JobStatus.succeeded.value)
        return {"job_id": job_id, "turn_id": turn.turn_id, **result}
    except Exception as e:
        store.update_job(job_id, status=JobStatus.failed.value, error_message=str(e))
        store.update_turn(turn.turn_id, status="failed", error_message=str(e))
        return {"job_id": job_id, "turn_id": turn.turn_id, "error": str(e)}
