from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from image_editor.models import (
    CreateTurnRequest,
    CreateTurnResponse,
    JobStatus,
    ReplayTurnRequest,
    SessionResponse,
    SwitchTurnRequest,
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


# ---- Job ----

@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


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
        status=JobStatus.running.value,
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
            turn_id=turn.turn_id,
        )
        store.update_job(job_id, status=JobStatus.succeeded.value)
        store.update_turn(turn.turn_id, status=JobStatus.succeeded.value)
        return {"job_id": job_id, "turn_id": turn.turn_id, **result}
    except Exception as e:
        store.update_job(job_id, status=JobStatus.failed.value, error_message=str(e))
        store.update_turn(turn.turn_id, status="failed", error_message=str(e))
        return {"job_id": job_id, "turn_id": turn.turn_id, "error": str(e)}


@app.post("/sessions/{session_id}/replay")
async def replay_turn(session_id: str, req: ReplayTurnRequest) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    source_turn = store.get_turn(req.from_turn_id)
    if not source_turn or source_turn.session_id != session_id:
        raise HTTPException(status_code=404, detail="source turn not found")

    parent_turn = store.get_turn(source_turn.parent_turn_id) if source_turn.parent_turn_id else None
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

    turn = store.create_turn(
        session_id=session_id,
        user_instruction=replay_req.instruction,
        parent_turn_id=replay_req.current_turn_id,
        status=JobStatus.running.value,
    )
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
            turn_id=turn.turn_id,
        )
        store.update_job(job_id, status=JobStatus.succeeded.value)
        return {"job_id": job_id, "turn_id": turn.turn_id, **result}
    except Exception as e:
        store.update_job(job_id, status=JobStatus.failed.value, error_message=str(e))
        store.update_turn(turn.turn_id, status="failed", error_message=str(e))
        return {"job_id": job_id, "turn_id": turn.turn_id, "error": str(e)}
