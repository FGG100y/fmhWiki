export interface CreateTurnRequest {
  instruction: string;
  current_turn_id?: string;
  reference_image_ids?: string[];
  mask_image_id?: string;
  uploaded_image_id?: string;
  options?: Record<string, unknown>;
}

export interface TurnDetail {
  turn_id: string;
  parent_turn_id: string | null;
  user_instruction: string;
  intent: string | null;
  edit_scope: string | null;
  rewritten_prompt: string | null;
  negative_prompt: string | null;
  input_image_id: string | null;
  input_image_url: string | null;
  output_image_id: string | null;
  output_image_url: string | null;
  mask_image_id: string | null;
  mask_image_url: string | null;
  reference_image_ids: string[];
  model_provider: string | null;
  model_name: string | null;
  selected_tool: string | null;
  model_params: Record<string, unknown>;
  status: string;
  qa_score: number | null;
  qa_passed: boolean | null;
  qa_result: Record<string, unknown>;
  error_message: string | null;
  agent_steps: Array<{
    index: number;
    tool: string;
    args: Record<string, unknown>;
    result: Record<string, unknown>;
    tool_impl: string;
    status: string;
    error: string;
    latency_ms: number;
    created_at: string;
  }>;
  execution_mode: string;
  created_at: string;
}

export interface SessionResponse {
  session_id: string;
  project_id: string;
  current_turn_id: string | null;
  can_undo: boolean;
  can_redo: boolean;
  turns: TurnDetail[];
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  image_id: string;
  image_url: string;
  filename: string;
  width: number;
  height: number;
}

export interface ExecuteResult {
  job_id: string;
  turn_id: string;
  output_image_url?: string;
  output_image_id?: string;
  error?: string;
}

export interface JobDetail {
  job_id: string;
  session_id: string;
  turn_id: string;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionRecord {
  session_id: string;
  project_id: string;
  user_id: string;
  current_turn_id: string | null;
  created_at: string;
  updated_at: string;
}

const BASE = "";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export async function uploadImage(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/upload", { method: "POST", body: formData });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export function createSession(projectId: string): Promise<SessionRecord> {
  return request<SessionRecord>(
    `/projects/${encodeURIComponent(projectId)}/sessions?user_id=default`,
    { method: "POST" }
  );
}

export function executeTurn(
  sessionId: string,
  body: CreateTurnRequest
): Promise<ExecuteResult> {
  return request<ExecuteResult>(
    `/sessions/${encodeURIComponent(sessionId)}/execute`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
}

export function getSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(
    `/sessions/${encodeURIComponent(sessionId)}`
  );
}

export function getTurn(turnId: string): Promise<TurnDetail> {
  return request<TurnDetail>(`/turns/${encodeURIComponent(turnId)}`);
}

export function undoTurn(sessionId: string): Promise<{ current_turn_id: string | null }> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/undo`, { method: "POST" });
}

export function redoTurn(sessionId: string): Promise<{ current_turn_id: string | null }> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/redo`, { method: "POST" });
}

export function replayTurn(
  sessionId: string,
  fromTurnId: string
): Promise<ExecuteResult> {
  return request<ExecuteResult>(
    `/sessions/${encodeURIComponent(sessionId)}/replay`,
    {
      method: "POST",
      body: JSON.stringify({ from_turn_id: fromTurnId }),
    }
  );
}

export function getJob(jobId: string): Promise<JobDetail> {
  return request<JobDetail>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function cancelJob(jobId: string): Promise<{ job_id: string; status: string }> {
  return request<{ job_id: string; status: string }>(
    `/jobs/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" }
  );
}

export function deleteTurn(
  sessionId: string,
  turnId: string
): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(
    `/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}`,
    { method: "DELETE" }
  );
}
