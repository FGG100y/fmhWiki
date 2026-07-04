import { useEffect, useRef, useState, useCallback } from "react";
import {
  createSession,
  executeTurn,
  getSession,
  undoTurn as apiUndo,
  redoTurn as apiRedo,
  replayTurn as apiReplay,
  getJob,
  cancelJob,
  ExecuteResult,
  SessionResponse,
  TurnDetail,
} from "../api";

export interface SessionState {
  sessionId: string | null;
  currentTurnId: string | null;
  turns: TurnDetail[];
  loading: boolean;
  error: string | null;
  currentOutputUrl: string | null;
  currentInputUrl: string | null;
  currentInstruction: string | null;
  uploadedImageId: string | null;
  uploadedImageUrl: string | null;
  maskImageId: string | null;
  maskImageUrl: string | null;
  maskFilename: string | null;
  canUndo: boolean;
  canRedo: boolean;
}

const SESSION_ID_KEY = "image-editor:session-id";

export function useSession() {
  const [state, setState] = useState<SessionState>({
    sessionId: null,
    currentTurnId: null,
    turns: [],
    loading: false,
    error: null,
    currentOutputUrl: null,
    currentInputUrl: null,
    currentInstruction: null,
    uploadedImageId: null,
    uploadedImageUrl: null,
    maskImageId: null,
    maskImageUrl: null,
    maskFilename: null,
    canUndo: false,
    canRedo: false,
  });

  const sessionIdRef = useRef<string | null>(null);

  const refresh = useCallback(async (sid: string) => {
    try {
      const data: SessionResponse = await getSession(sid);
      const currentTurn = data.turns.find(
        (t) => t.turn_id === data.current_turn_id
      );
      setState((prev) => ({
        ...prev,
        sessionId: data.session_id,
        currentTurnId: data.current_turn_id,
        turns: data.turns,
        loading: false,
        error: null,
        currentOutputUrl: currentTurn?.output_image_url ?? prev.currentOutputUrl,
        currentInputUrl: currentTurn?.input_image_url ?? null,
        currentInstruction: currentTurn?.user_instruction ?? null,
        canUndo: data.can_undo,
        canRedo: data.can_redo,
      }));
    } catch (e: unknown) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : "Unknown error",
      }));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function init() {
      setState((prev) => ({ ...prev, loading: true }));
      const stored = localStorage.getItem(SESSION_ID_KEY);
      if (stored) {
        try {
          const existing = await getSession(stored);
          if (cancelled) return;
          sessionIdRef.current = existing.session_id;
          await refresh(existing.session_id);
          return;
        } catch {
          localStorage.removeItem(SESSION_ID_KEY);
        }
      }
      try {
        const session = await createSession("default-project");
        if (cancelled) return;
        sessionIdRef.current = session.session_id;
        localStorage.setItem(SESSION_ID_KEY, session.session_id);
        await refresh(session.session_id);
      } catch (e: unknown) {
        if (cancelled) return;
        setState((prev) => ({
          ...prev,
          loading: false,
          error: e instanceof Error ? e.message : "Unknown error",
        }));
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const sendInstruction = useCallback(
    async (instruction: string): Promise<ExecuteResult> => {
      const sid = sessionIdRef.current;
      if (!sid) throw new Error("No session");
      setState((prev) => ({ ...prev, loading: true, error: null }));
      const uploadedImageId = state.uploadedImageId;
      const maskImageId = state.maskImageId;
      try {
        const result = await executeTurn(sid, {
          instruction,
          current_turn_id: state.currentTurnId ?? undefined,
          uploaded_image_id: uploadedImageId ?? undefined,
          mask_image_id: maskImageId ?? undefined,
        });
        
        // 如果返回了job_id，开始轮询job状态
        if (result.job_id) {
          const pollJob = async () => {
            try {
              const job = await getJob(result.job_id);
              if (job.status === "succeeded" || job.status === "failed") {
                // job完成，刷新session数据
                setState((prev) => ({
                  ...prev,
                  uploadedImageId: null,
                  uploadedImageUrl: null,
                  maskImageId: null,
                  maskImageUrl: null,
                  maskFilename: null,
                }));
                await refresh(sid);
                return;
              }
              // 继续轮询
              setTimeout(pollJob, 1000);
            } catch {
              // 轮询出错，停止轮询并刷新
              setState((prev) => ({
                ...prev,
                uploadedImageId: null,
                uploadedImageUrl: null,
                maskImageId: null,
                maskImageUrl: null,
                maskFilename: null,
              }));
              await refresh(sid);
            }
          };
          // 开始轮询
          setTimeout(pollJob, 1000);
        } else {
          // 没有job_id（同步执行），直接刷新
          setState((prev) => ({
            ...prev,
            uploadedImageId: null,
            uploadedImageUrl: null,
            maskImageId: null,
            maskImageUrl: null,
            maskFilename: null,
          }));
          await refresh(sid);
        }
        
        return result;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Unknown error";
        setState((prev) => ({ ...prev, loading: false, error: msg }));
        return { job_id: "", turn_id: "", error: msg };
      }
    },
    [state.currentTurnId, state.uploadedImageId, state.maskImageId, refresh]
  );

  const handleImageUpload = useCallback((imageId: string, imageUrl: string) => {
    setState((prev) => ({
      ...prev,
      uploadedImageId: imageId,
      uploadedImageUrl: imageUrl,
      currentInputUrl: imageUrl,
    }));
  }, []);

  const handleMaskUpload = useCallback((imageId: string, _imageUrl: string) => {
    setState((prev) => ({
      ...prev,
      maskImageId: imageId,
      maskImageUrl: _imageUrl,
      maskFilename: "已上传",
    }));
  }, []);

  const clearMask = useCallback(() => {
    setState((prev) => ({
      ...prev,
      maskImageId: null,
      maskImageUrl: null,
      maskFilename: null,
    }));
  }, []);

  const undo = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    try {
      await apiUndo(sid);
      await refresh(sid);
    } catch (e: unknown) {
      setState((prev) => ({
        ...prev,
        error: e instanceof Error ? e.message : "Undo failed",
      }));
    }
  }, [refresh]);

  const redo = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    try {
      await apiRedo(sid);
      await refresh(sid);
    } catch (e: unknown) {
      setState((prev) => ({
        ...prev,
        error: e instanceof Error ? e.message : "Redo failed",
      }));
    }
  }, [refresh]);

  const retry = useCallback(
    async (turnId: string): Promise<ExecuteResult | undefined> => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const result = await apiReplay(sid, turnId);
        
        // 如果返回了job_id，开始轮询job状态
        if (result.job_id) {
          const pollJob = async () => {
            try {
              const job = await getJob(result.job_id);
              if (job.status === "succeeded" || job.status === "failed") {
                // job完成，刷新session数据
                await refresh(sid);
                if (result.error) {
                  setState((prev) => ({ ...prev, error: result.error ?? null }));
                }
                return;
              }
              // 继续轮询
              setTimeout(pollJob, 1000);
            } catch {
              // 轮询出错，停止轮询并刷新
              await refresh(sid);
            }
          };
          // 开始轮询
          setTimeout(pollJob, 1000);
        } else {
          // 没有job_id（同步执行），直接刷新
          await refresh(sid);
        }
        
        if (result.error) {
          setState((prev) => ({ ...prev, error: result.error ?? null }));
        }
        return result;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Retry failed";
        setState((prev) => ({ ...prev, loading: false, error: msg }));
        return { job_id: "", turn_id: "", error: msg };
      }
    },
    [refresh]
  );

  const selectTurn = useCallback(
    async (turnId: string) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      setState((prev) => ({ ...prev, loading: true }));
      try {
        await fetch(`/sessions/${encodeURIComponent(sid)}/switch-current-turn`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ turn_id: turnId }),
        });
        await refresh(sid);
      } catch (e: unknown) {
        setState((prev) => ({
          ...prev,
          loading: false,
          error: e instanceof Error ? e.message : "Unknown error",
        }));
      }
    },
    [refresh]
  );

  const cancelExecution = useCallback(
    async (jobId: string): Promise<void> => {
      try {
        await cancelJob(jobId);
        // 取消成功后刷新session状态
        const sid = sessionIdRef.current;
        if (sid) {
          await refresh(sid);
        }
      } catch (e: unknown) {
        setState((prev) => ({
          ...prev,
          error: e instanceof Error ? e.message : "Cancel failed",
        }));
      }
    },
    [refresh]
  );

  return { ...state, sendInstruction, selectTurn, handleImageUpload, handleMaskUpload, clearMask, undo, redo, retry, cancelExecution };
}
