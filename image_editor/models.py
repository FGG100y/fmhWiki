from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    generate_image = "generate_image"
    edit_image = "edit_image"
    local_edit = "local_edit"
    style_transfer = "style_transfer"
    background_replace = "background_replace"
    object_add = "object_add"
    object_remove = "object_remove"
    text_edit = "text_edit"
    variation = "variation"
    upscale = "upscale"
    undo = "undo"
    redo = "redo"
    compare = "compare"
    export = "export"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    qa_checking = "qa_checking"
    retrying = "retrying"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class EditScope(str, Enum):
    global_ = "global"
    background = "background"
    foreground = "foreground"
    object = "object"
    region = "region"


class IntentResult(BaseModel):
    intent: Intent
    operation: str = ""
    edit_scope: Optional[EditScope] = None
    requires_mask: bool = False
    preserve: list[str] = Field(default_factory=list)
    risk: str = ""


class PromptResult(BaseModel):
    positive_prompt: str
    negative_prompt: str = ""
    preservation_constraints: list[str] = Field(default_factory=list)
    edit_strength: float = 0.45


class ToolSelection(BaseModel):
    tool: str
    reason: str = ""
    fallback_tool: str = ""
    params: dict = Field(default_factory=dict)


class QAResult(BaseModel):
    passed: bool = False
    score: float = 0.0
    issues: list[str] = Field(default_factory=list)
    retry_suggestion: str = ""


class TurnRecord(BaseModel):
    turn_id: str = ""
    session_id: str = ""
    parent_turn_id: Optional[str] = None
    user_instruction: str = ""
    intent: Optional[str] = None
    edit_scope: Optional[str] = None
    rewritten_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    preservation_constraints: list[str] = Field(default_factory=list)
    input_image_id: Optional[str] = None
    output_image_id: Optional[str] = None
    mask_image_id: Optional[str] = None
    reference_image_ids: list[str] = Field(default_factory=list)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    selected_tool: Optional[str] = None
    model_params: dict = Field(default_factory=dict)
    status: str = "queued"
    qa_score: Optional[float] = None
    qa_passed: Optional[bool] = None
    qa_result: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "1:1"
    seed: Optional[int] = None
    quality: str = "standard"
    metadata: dict = Field(default_factory=dict)


class EditRequest(BaseModel):
    input_image_url: str
    prompt: str
    negative_prompt: str = ""
    mask_image_url: Optional[str] = None
    reference_image_urls: list[str] = Field(default_factory=list)
    aspect_ratio: Optional[str] = None
    seed: Optional[int] = None
    strength: Optional[float] = None
    metadata: dict = Field(default_factory=dict)


class GenerateResult(BaseModel):
    image_id: str
    image_url: str
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    seed: Optional[int] = None
    metadata: dict = Field(default_factory=dict)


class EditResult(BaseModel):
    image_id: str
    image_url: str
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    seed: Optional[int] = None
    metadata: dict = Field(default_factory=dict)


class CreateTurnRequest(BaseModel):
    instruction: str
    current_turn_id: Optional[str] = None
    reference_image_ids: list[str] = Field(default_factory=list)
    mask_image_id: Optional[str] = None
    options: dict = Field(default_factory=dict)


class CreateTurnResponse(BaseModel):
    job_id: str
    turn_id: str
    status: str = "queued"


class TurnDetailResponse(BaseModel):
    turn_id: str
    parent_turn_id: Optional[str] = None
    user_instruction: str
    intent: Optional[str] = None
    edit_scope: Optional[str] = None
    rewritten_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    input_image_id: Optional[str] = None
    input_image_url: Optional[str] = None
    output_image_id: Optional[str] = None
    output_image_url: Optional[str] = None
    mask_image_id: Optional[str] = None
    mask_image_url: Optional[str] = None
    reference_image_ids: list[str] = Field(default_factory=list)
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    selected_tool: Optional[str] = None
    model_params: dict = Field(default_factory=dict)
    status: str
    qa_score: Optional[float] = None
    qa_passed: Optional[bool] = None
    qa_result: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: str


class SessionResponse(BaseModel):
    session_id: str
    project_id: str
    current_turn_id: Optional[str] = None
    turns: list[TurnDetailResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str


class SwitchTurnRequest(BaseModel):
    turn_id: str


class ReplayTurnRequest(BaseModel):
    from_turn_id: str


class ModelCallRecord(BaseModel):
    call_id: str
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    provider: str
    model_name: str
    endpoint: str
    purpose: str
    latency_ms: int
    status: str
    error_message: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
