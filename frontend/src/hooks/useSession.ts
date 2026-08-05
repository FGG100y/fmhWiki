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
  uploadImage,
  deleteTurn as apiDeleteTurn,
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
  maskDrawingMode: boolean;
  sketchDrawingMode: boolean;
  sketchFilename: string | null;
  currentJobId: string | null;
  canUndo: boolean;
  canRedo: boolean;
  hasPreviousSession: boolean;
}

const LAST_WORK_SESSION_KEY = "painterAgent:last-work-session";

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
    maskDrawingMode: false,
    sketchDrawingMode: false,
    sketchFilename: null,
    currentJobId: null,
    canUndo: false,
    canRedo: false,
    hasPreviousSession: false,
  });

  const sessionIdRef = useRef<string | null>(null);

  const refresh = useCallback(async (sid: string, showOutput = false) => {
    try {
      const data: SessionResponse = await getSession(sid);
      const currentTurn = data.turns.find(
        (t) => t.turn_id === data.current_turn_id
      );
      // 只把「已成功产出结果」的子节点视为真正的子节点；
      // 失败/排队/生成中的 turn 没有 output，不能让当前结果被误判为「有子节点的历史结果」。
      const realChildren = data.turns
        .filter(
          (t) => t.parent_turn_id === data.current_turn_id && !!t.output_image_url
        )
        .sort((a, b) => a.created_at.localeCompare(b.created_at));
      const hasChild = realChildren.length > 0;
      const outputUrl = currentTurn?.output_image_url ?? null;
      const inputUrl = currentTurn?.input_image_url ?? null;
      const isRoot = inputUrl === outputUrl; // 根 turn，output==input，没意义
      const childOutputUrl = hasChild
        ? realChildren[0].output_image_url
        : null;
      // 统一逻辑：左侧始终显示「当前选中 turn 的结果」，右侧显示其第一个子节点的结果（如有）
      let currentOutputUrl: string | null;
      let currentInputUrl: string | null;
      if (isRoot) {
        // 根 turn：左侧=原始图，右侧=第一个修改结果
        currentInputUrl = inputUrl;
        currentOutputUrl = childOutputUrl;
      } else if (showOutput) {
        // 刚完成编辑：左侧=输入，右侧=新结果（对比视图）
        currentInputUrl = inputUrl;
        currentOutputUrl = outputUrl;
      } else {
        // 浏览历史：左侧=选中结果，右侧=第一个子节点结果（如有）
        currentInputUrl = outputUrl;
        currentOutputUrl = childOutputUrl;
      }
      setState((prev) => ({
        ...prev,
        sessionId: data.session_id,
        currentTurnId: data.current_turn_id,
        turns: data.turns,
        loading: false,
        error: null,
        currentOutputUrl,
        currentInputUrl,
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
      // 默认启动一个全新的空白会话；
      // 若浏览器记录过「有实际编辑的会话」，仅提示用户可显式恢复。
      const lastWork = localStorage.getItem(LAST_WORK_SESSION_KEY);
      try {
        const session = await createSession("default-project");
        if (cancelled) return;
        sessionIdRef.current = session.session_id;
        if (lastWork) {
          setState((prev) => ({ ...prev, hasPreviousSession: true }));
        }
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

  const resumeSession = useCallback(async () => {
    const resumeId = localStorage.getItem(LAST_WORK_SESSION_KEY);
    if (!resumeId) return;
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const existing = await getSession(resumeId);
      sessionIdRef.current = existing.session_id;
      setState((prev) => ({ ...prev, hasPreviousSession: false }));
      await refresh(existing.session_id);
    } catch (e: unknown) {
      localStorage.removeItem(LAST_WORK_SESSION_KEY);
      setState((prev) => ({
        ...prev,
        loading: false,
        hasPreviousSession: false,
        error: e instanceof Error ? e.message : "恢复会话失败",
      }));
    }
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
        localStorage.setItem(LAST_WORK_SESSION_KEY, sid);
        
        // 如果返回了job_id，开始轮询job状态
        if (result.job_id) {
          setState((prev) => ({ ...prev, currentJobId: result.job_id }));
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
                  sketchDrawingMode: false,
                  sketchFilename: null,
                  currentJobId: null,
                }));
                await refresh(sid, true);
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
                sketchDrawingMode: false,
                sketchFilename: null,
                currentJobId: null,
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
            sketchDrawingMode: false,
            sketchFilename: null,
          }));
          await refresh(sid, true);
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
      sketchFilename: null,
      sketchDrawingMode: false,
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
      maskDrawingMode: false,
    }));
  }, []);

  const startMaskDrawing = useCallback(() => {
    setState((prev) => ({
      ...prev,
      maskDrawingMode: true,
      sketchDrawingMode: false,
    }));
  }, []);

  const cancelMaskDrawing = useCallback(() => {
    setState((prev) => ({
      ...prev,
      maskDrawingMode: false,
    }));
  }, []);

  const handleMaskDrawingConfirm = useCallback(
    async (blob: Blob) => {
      const file = new File([blob], `mask_${Date.now()}.png`, {
        type: "image/png",
      });
      try {
        const resp = await uploadImage(file);
        setState((prev) => ({
          ...prev,
          maskImageId: resp.image_id,
          maskImageUrl: resp.image_url,
          maskFilename: "已绘制",
          maskDrawingMode: false,
        }));
      } catch (err) {
        setState((prev) => ({
          ...prev,
          maskDrawingMode: false,
          error: err instanceof Error ? err.message : "Mask 上传失败",
        }));
      }
    },
    []
  );

  const startSketchDrawing = useCallback(() => {
    setState((prev) => ({
      ...prev,
      sketchDrawingMode: true,
      maskDrawingMode: false,
    }));
  }, []);

  const cancelSketchDrawing = useCallback(() => {
    setState((prev) => ({
      ...prev,
      sketchDrawingMode: false,
    }));
  }, []);

  const handleSketchDrawingConfirm = useCallback(
    async (blob: Blob) => {
      const file = new File([blob], `sketch_${Date.now()}.png`, {
        type: "image/png",
      });
      try {
        const resp = await uploadImage(file);
        setState((prev) => ({
          ...prev,
          uploadedImageId: resp.image_id,
          uploadedImageUrl: resp.image_url,
          currentInputUrl: resp.image_url,
          sketchDrawingMode: false,
          sketchFilename: "白板草稿",
        }));
      } catch (err) {
        setState((prev) => ({
          ...prev,
          sketchDrawingMode: false,
          error: err instanceof Error ? err.message : "白板草稿上传失败",
        }));
      }
    },
    []
  );

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
                await refresh(sid, true);
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
          await refresh(sid, true);
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
        setState((prev) => ({ ...prev, currentJobId: null, loading: false }));
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

  const deleteTurn = useCallback(
    async (turnId: string) => {
      const sid = sessionIdRef.current;
      if (!sid) return;
      try {
        await apiDeleteTurn(sid, turnId);
        await refresh(sid);
      } catch (e: unknown) {
        setState((prev) => ({
          ...prev,
          error: e instanceof Error ? e.message : "Delete failed",
        }));
      }
    },
    [refresh]
  );

  return { ...state, sendInstruction, selectTurn, handleImageUpload, handleMaskUpload, clearMask, startMaskDrawing, cancelMaskDrawing, handleMaskDrawingConfirm, startSketchDrawing, cancelSketchDrawing, handleSketchDrawingConfirm, undo, redo, retry, cancelExecution, deleteTurn, resumeSession };
}
