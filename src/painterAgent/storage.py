"""存储实现 — 支持 Postgres 和内存存储

生产环境使用 Postgres，开发环境可使用内存存储"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from painterAgent.models import (
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
        session["updated_at"] = datetime.utcnow().isoformat()
        return session

    def get_session(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def list_sessions_by_project(self, project_id: str) -> list[dict]:
        """列出项目下所有会话（用于偏好聚合等跨会话查询）"""
        return [s for s in self._sessions.values() if s.get("project_id") == project_id]

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

    def delete_turn(self, turn_id: str) -> bool:
        turn = self._turns.get(turn_id)
        if not turn:
            return False
        session = self._sessions.get(turn.session_id)
        if session:
            if session.get("current_turn_id") == turn_id:
                session["current_turn_id"] = turn.parent_turn_id
            session["updated_at"] = datetime.utcnow().isoformat()
        del self._turns[turn_id]
        return True

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
            agent_steps=[s.model_dump() if hasattr(s, 'model_dump') else s for s in (turn.agent_steps or [])],
            execution_mode=turn.execution_mode or "",
            created_at=turn.created_at,
        )


class PostgresStore:
    """Postgres 存储（生产环境）"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self._database_url)
            self._conn.autocommit = False
        return self._conn

    def _execute(self, query: str, params=None, fetch: bool = False):
        conn = self._get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return None

    def _commit(self):
        self._get_conn().commit()

    # ---- Session ----

    def create_session(self, project_id: str, user_id: str) -> dict:
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        query = """
            INSERT INTO sessions (session_id, project_id, user_id, current_turn_id, created_at, updated_at)
            VALUES (%s, %s, %s, NULL, %s, %s)
            RETURNING *
        """
        result = self._execute(query, (session_id, project_id, user_id, now, now), fetch=True)
        self._commit()
        return dict(result[0]) if result else {}

    def switch_current_turn(self, session_id: str, turn_id: Optional[str]) -> dict:
        query = "SELECT * FROM sessions WHERE session_id = %s"
        result = self._execute(query, (session_id,), fetch=True)
        if not result:
            raise ValueError("session not found")
        if turn_id is not None:
            turn_query = "SELECT * FROM turns WHERE turn_id = %s"
            turn_result = self._execute(turn_query, (turn_id,), fetch=True)
            if not turn_result:
                raise ValueError("turn not found")
        now = datetime.utcnow().isoformat()
        update_query = """
            UPDATE sessions
            SET current_turn_id = %s, updated_at = %s
            WHERE session_id = %s
            RETURNING *
        """
        result = self._execute(update_query, (turn_id, now, session_id), fetch=True)
        self._commit()
        return dict(result[0]) if result else {}

    def get_session(self, session_id: str) -> Optional[dict]:
        query = "SELECT * FROM sessions WHERE session_id = %s"
        result = self._execute(query, (session_id,), fetch=True)
        return dict(result[0]) if result else None

    def list_sessions_by_project(self, project_id: str) -> list[dict]:
        """列出项目下所有会话"""
        query = "SELECT * FROM sessions WHERE project_id = %s"
        result = self._execute(query, (project_id,), fetch=True)
        return [dict(r) for r in result] if result else []

    def get_session_with_turns(self, session_id: str) -> Optional[SessionResponse]:
        session = self.get_session(session_id)
        if not session:
            return None
        query = "SELECT * FROM turns WHERE session_id = %s ORDER BY created_at"
        turns_result = self._execute(query, (session_id,), fetch=True)
        turns = [self._to_turn_detail(dict(t)) for t in turns_result] if turns_result else []
        return SessionResponse(
            session_id=session["session_id"],
            project_id=session["project_id"],
            current_turn_id=session.get("current_turn_id"),
            turns=turns,
            created_at=session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
            updated_at=session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else session["updated_at"],
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
        query = """
            INSERT INTO turns (turn_id, session_id, parent_turn_id, user_instruction, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        result = self._execute(query, (turn_id, session_id, parent_turn_id, user_instruction, status), fetch=True)
        self._commit()
        
        if set_current:
            now = datetime.utcnow().isoformat()
            update_session = """
                UPDATE sessions SET current_turn_id = %s, updated_at = %s WHERE session_id = %s
            """
            self._execute(update_session, (turn_id, now, session_id))
            self._commit()
        
        turn_data = dict(result[0]) if result else {}
        if "created_at" in turn_data and hasattr(turn_data["created_at"], "isoformat"):
            turn_data["created_at"] = turn_data["created_at"].isoformat()
        return TurnRecord(**turn_data)

    def update_turn(self, turn_id: str, **fields) -> Optional[TurnRecord]:
        set_clauses = []
        values = []
        for k, v in fields.items():
            if k in TurnRecord.model_fields:
                if isinstance(v, (dict, list)):
                    set_clauses.append(f"{k} = %s")
                    values.append(json.dumps(v))
                else:
                    set_clauses.append(f"{k} = %s")
                    values.append(v)
        if not set_clauses:
            return None
        values.append(turn_id)
        query = f"UPDATE turns SET {', '.join(set_clauses)} WHERE turn_id = %s RETURNING *"
        result = self._execute(query, values, fetch=True)
        self._commit()
        if result:
            turn_data = dict(result[0])
            if "created_at" in turn_data and hasattr(turn_data["created_at"], "isoformat"):
                turn_data["created_at"] = turn_data["created_at"].isoformat()
            return TurnRecord(**turn_data)
        return None

    def get_turn(self, turn_id: str) -> Optional[TurnRecord]:
        query = "SELECT * FROM turns WHERE turn_id = %s"
        result = self._execute(query, (turn_id,), fetch=True)
        if result:
            turn_data = dict(result[0])
            if "created_at" in turn_data and hasattr(turn_data["created_at"], "isoformat"):
                turn_data["created_at"] = turn_data["created_at"].isoformat()
            return TurnRecord(**turn_data)
        return None

    def get_turn_detail(self, turn_id: str) -> Optional[TurnDetailResponse]:
        turn = self.get_turn(turn_id)
        if not turn:
            return None
        return self._to_turn_detail(dict(turn))

    def delete_turn(self, turn_id: str) -> bool:
        turn = self.get_turn(turn_id)
        if not turn:
            return False
        session = self.get_session(turn.session_id)
        if session:
            if session.get("current_turn_id") == turn_id:
                self._execute("UPDATE sessions SET current_turn_id = %s WHERE session_id = %s", (turn.parent_turn_id, turn.session_id))
            self._commit()
        self._execute("DELETE FROM model_calls WHERE turn_id = %s", (turn_id,))
        self._execute("DELETE FROM jobs WHERE turn_id = %s", (turn_id,))
        self._execute("DELETE FROM turns WHERE turn_id = %s", (turn_id,))
        self._commit()
        return True

    # ---- Job ----

    def create_job(self, session_id: str, turn_id: str) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        query = """
            INSERT INTO jobs (job_id, session_id, turn_id, status)
            VALUES (%s, %s, %s, 'queued')
        """
        self._execute(query, (job_id, session_id, turn_id))
        self._commit()
        return job_id

    def update_job(self, job_id: str, **fields) -> None:
        set_clauses = []
        values = []
        for k, v in fields.items():
            set_clauses.append(f"{k} = %s")
            values.append(v)
        if set_clauses:
            values.append(job_id)
            query = f"UPDATE jobs SET {', '.join(set_clauses)}, updated_at = NOW() WHERE job_id = %s"
            self._execute(query, values)
            self._commit()

    def get_job(self, job_id: str) -> Optional[dict]:
        query = "SELECT * FROM jobs WHERE job_id = %s"
        result = self._execute(query, (job_id,), fetch=True)
        return dict(result[0]) if result else None

    # ---- Image ----

    def save_image(self, image_id: str, url: str, metadata: Optional[dict] = None) -> dict:
        meta = metadata or {}
        query = """
            INSERT INTO images (image_id, url, width, height, thumbnail_url, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
        """
        result = self._execute(query, (
            image_id, url, 
            meta.get("width"), meta.get("height"), 
            meta.get("thumbnail_url"), json.dumps(meta)
        ), fetch=True)
        self._commit()
        return dict(result[0]) if result else {}

    def get_image(self, image_id: str) -> Optional[dict]:
        query = "SELECT * FROM images WHERE image_id = %s"
        result = self._execute(query, (image_id,), fetch=True)
        return dict(result[0]) if result else None

    def record_model_call(self, record: ModelCallRecord) -> None:
        query = """
            INSERT INTO model_calls (call_id, session_id, turn_id, provider, model_name, endpoint, purpose, latency_ms, status, error_message, input_tokens, output_tokens, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        self._execute(query, (
            record.call_id, record.session_id, record.turn_id,
            record.provider, record.model_name, record.endpoint,
            record.purpose, record.latency_ms, record.status,
            record.error_message, record.input_tokens, record.output_tokens,
            json.dumps(record.metadata)
        ))
        self._commit()

    def list_model_calls(
        self,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
    ) -> list[ModelCallRecord]:
        query = "SELECT * FROM model_calls WHERE 1=1"
        params = []
        if session_id:
            query += " AND session_id = %s"
            params.append(session_id)
        if turn_id:
            query += " AND turn_id = %s"
            params.append(turn_id)
        query += " ORDER BY created_at"
        result = self._execute(query, params, fetch=True)
        return [ModelCallRecord(**dict(r)) for r in result] if result else []

    # ---- Helpers ----

    def _to_turn_detail(self, turn: dict) -> TurnDetailResponse:
        input_image = self._get_image_dict(turn.get("input_image_id"))
        output_image = self._get_image_dict(turn.get("output_image_id"))
        mask_image = self._get_image_dict(turn.get("mask_image_id"))
        return TurnDetailResponse(
            turn_id=turn["turn_id"],
            parent_turn_id=turn.get("parent_turn_id"),
            user_instruction=turn["user_instruction"],
            intent=turn.get("intent"),
            edit_scope=turn.get("edit_scope"),
            rewritten_prompt=turn.get("rewritten_prompt"),
            negative_prompt=turn.get("negative_prompt"),
            input_image_id=turn.get("input_image_id"),
            input_image_url=input_image["url"] if input_image else None,
            output_image_id=turn.get("output_image_id"),
            output_image_url=output_image["url"] if output_image else None,
            mask_image_id=turn.get("mask_image_id"),
            mask_image_url=mask_image["url"] if mask_image else None,
            reference_image_ids=turn.get("reference_image_ids") or [],
            model_provider=turn.get("model_provider"),
            model_name=turn.get("model_name"),
            selected_tool=turn.get("selected_tool"),
            model_params=turn.get("model_params") or {},
            status=turn["status"],
            qa_score=turn.get("qa_score"),
            qa_passed=turn.get("qa_passed"),
            qa_result=turn.get("qa_result") or {},
            error_message=turn.get("error_message"),
            agent_steps=_json_loads(turn.get("agent_steps"), default=[]),
            execution_mode=turn.get("execution_mode") or "",
            created_at=turn["created_at"].isoformat() if isinstance(turn["created_at"], datetime) else turn["created_at"],
        )

    def _get_image_dict(self, image_id: Optional[str]) -> Optional[dict]:
        if not image_id:
            return None
        return self.get_image(image_id)


def _json_loads(value, default=None):
    """安全 json.loads：处理已解析的 dict/list 或 None。"""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


# 根据环境变量选择存储实现
_database_url = os.getenv("DATABASE_URL")
if _database_url:
    store = PostgresStore(_database_url)
else:
    store = MemoryStore()
