"""内存存储实现 — 用于演示和开发

生产环境应替换为 Postgres + S3 / OSS"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from image_editor.models import (
    SessionResponse,
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

    # ---- Session ----

    def create_session(self, project_id: str, user_id: str) -> dict:
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        self._sessions[session_id] = {
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "current_turn_id": None,
            "created_at": now,
            "updated_at": now,
        }
        return self._sessions[session_id]

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
    ) -> TurnRecord:
        turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        turn = TurnRecord(
            turn_id=turn_id,
            session_id=session_id,
            parent_turn_id=parent_turn_id,
            user_instruction=user_instruction,
        )
        self._turns[turn_id] = turn

        session = self._sessions.get(session_id)
        if session:
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
        record = {
            "image_id": image_id,
            "url": url,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        self._images[image_id] = record
        return record

    def get_image(self, image_id: str) -> Optional[dict]:
        return self._images.get(image_id)

    # ---- Helpers ----

    def _to_turn_detail(self, turn: TurnRecord) -> TurnDetailResponse:
        return TurnDetailResponse(
            turn_id=turn.turn_id,
            parent_turn_id=turn.parent_turn_id,
            user_instruction=turn.user_instruction,
            intent=turn.intent,
            rewritten_prompt=turn.rewritten_prompt,
            status=turn.status,
            qa_score=turn.qa_score,
            qa_passed=turn.qa_passed,
            error_message=turn.error_message,
            created_at=turn.created_at,
        )


store = MemoryStore()
