"""内存存储实现 — 用于演示和开发

生产环境应替换为 Postgres + S3 / OSS"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from image_editor.models import (
    SessionResponse,
    ModelCallRecord,
    TurnDetailResponse,
    TurnRecord,
)


class MemoryStore:
    """内存存储（开发/演示用）"""

    def __init__(self) -> None:
        self._turns: dict[str, TurnRecord] = {}
        self._sessions: dict[str, dict] = {}
        self._jobs: dict[str, dict] = {}
        self._images: dict[str, dict] = {}
        self._model_calls: list[ModelCallRecord] = []

    # ---- Session ----

    def create_session(self, project_id: str, user_id: str) -> dict:
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        self._sessions[session_id] = {
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "current_turn_id": None,
            "redo_stack": [],
            "created_at": now,
            "updated_at": now,
        }
        return self._sessions[session_id]

    def switch_current_turn(self, session_id: str, turn_id: Optional[str]) -> dict:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError("session not found")
        if turn_id is not None and turn_id not in self._turns:
            raise ValueError("turn not found")
        session["current_turn_id"] = turn_id
        session["redo_stack"] = []
        session["updated_at"] = datetime.utcnow().isoformat()
        return session

    def undo(self, session_id: str) -> Optional[str]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        current = session.get("current_turn_id")
        if not current:
            return None
        current_turn = self._turns.get(current)
        parent = current_turn.parent_turn_id if current_turn else None
        if current:
            session["redo_stack"].append(current)
        session["current_turn_id"] = parent
        session["updated_at"] = datetime.utcnow().isoformat()
        return parent

    def redo(self, session_id: str) -> Optional[str]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        redo_stack = session.get("redo_stack", [])
        if not redo_stack:
            return session.get("current_turn_id")
        new_current = redo_stack.pop()
        session["current_turn_id"] = new_current
        session["updated_at"] = datetime.utcnow().isoformat()
        return new_current

    def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def get_session_with_turns(self, session_id: str) -> Optional[SessionResponse]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        turns = [
            self._to_turn_detail(t)
            for t in self._turns.values()
            if t.session_id == session_id
        ]
        turns.sort(key=lambda t: t.created_at)
        return SessionResponse(
            session_id=session["session_id"],
            project_id=session["project_id"],
            current_turn_id=session["current_turn_id"],
            turns=turns,
            created_at=session["created_at"],
            updated_at=session["updated_at"],
        )

    # ---- Turn ----

    def create_turn(
        self,
        session_id: str,
        user_instruction: str,
        parent_turn_id: Optional[str] = None,
        status: str = "queued",
        set_current: bool = False,
    ) -> TurnRecord:
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        turn = TurnRecord(
            turn_id=turn_id,
            session_id=session_id,
            parent_turn_id=parent_turn_id,
            user_instruction=user_instruction,
            status=status,
        )
        self._turns[turn_id] = turn

        session = self._sessions.get(session_id)
        if session and set_current:
            session["current_turn_id"] = turn_id
            session["updated_at"] = datetime.utcnow().isoformat()

        return turn

    def update_turn(self, turn_id: str, **fields) -> Optional[TurnRecord]:
        turn = self._turns.get(turn_id)
        if not turn:
            return None
        for k, v in fields.items():
            if hasattr(turn, k):
                setattr(turn, k, v)
        session = self._sessions.get(turn.session_id)
        if session:
            session["updated_at"] = datetime.utcnow().isoformat()
        return turn

    def get_turn(self, turn_id: str) -> Optional[TurnRecord]:
        return self._turns.get(turn_id)

    def get_turn_detail(self, turn_id: str) -> Optional[TurnDetailResponse]:
        turn = self._turns.get(turn_id)
        if not turn:
            return None
        return self._to_turn_detail(turn)

    # ---- Job ----

    def create_job(self, session_id: str, turn_id: str) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self._jobs[job_id] = {
            "job_id": job_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "queued",
            "created_at": datetime.utcnow().isoformat(),
        }
        return job_id

    def update_job(self, job_id: str, **fields) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.update(fields)

    def get_job(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    # ---- Image ----

    def save_image(self, image_id: str, url: str, metadata: Optional[dict] = None) -> dict:
        meta = metadata or {}
        record = {
            "image_id": image_id,
            "url": url,
            "width": meta.get("width"),
            "height": meta.get("height"),
            "thumbnail_url": meta.get("thumbnail_url"),
            "metadata": meta,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._images[image_id] = record
        return record

    def get_image(self, image_id: str) -> Optional[dict]:
        return self._images.get(image_id)

    def record_model_call(self, record: ModelCallRecord) -> None:
        self._model_calls.append(record)

    def list_model_calls(
        self,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> list[ModelCallRecord]:
        rows = self._model_calls
        if session_id:
            rows = [r for r in rows if r.session_id == session_id]
        if turn_id:
            rows = [r for r in rows if r.turn_id == turn_id]
        return rows

    def clear_redo_stack(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session["redo_stack"] = []
            session["updated_at"] = datetime.utcnow().isoformat()

    # ---- Helpers ----

    def _to_turn_detail(self, turn: TurnRecord) -> TurnDetailResponse:
        input_image = self._images.get(turn.input_image_id or "") if turn.input_image_id else None
        output_image = self._images.get(turn.output_image_id or "") if turn.output_image_id else None
        mask_image = self._images.get(turn.mask_image_id or "") if turn.mask_image_id else None
        return TurnDetailResponse(
            turn_id=turn.turn_id,
            parent_turn_id=turn.parent_turn_id,
            user_instruction=turn.user_instruction,
            intent=turn.intent,
            edit_scope=turn.edit_scope,
            rewritten_prompt=turn.rewritten_prompt,
            negative_prompt=turn.negative_prompt,
            input_image_id=turn.input_image_id,
            input_image_url=input_image["url"] if input_image else None,
            output_image_id=turn.output_image_id,
            output_image_url=output_image["url"] if output_image else None,
            mask_image_id=turn.mask_image_id,
            mask_image_url=mask_image["url"] if mask_image else None,
            reference_image_ids=turn.reference_image_ids,
            model_provider=turn.model_provider,
            model_name=turn.model_name,
            selected_tool=turn.selected_tool,
            model_params=turn.model_params,
            status=turn.status,
            qa_score=turn.qa_score,
            qa_passed=turn.qa_passed,
            qa_result=turn.qa_result,
            error_message=turn.error_message,
            created_at=turn.created_at,
        )


store = MemoryStore()
