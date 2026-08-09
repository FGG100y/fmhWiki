import { useState, useRef, useCallback } from "react";
import { useSession } from "./hooks/useSession";
import { useTheme } from "./hooks/useTheme";
import TurnTimeline from "./components/TurnTimeline";
import ImageViewer from "./components/ImageViewer";
import ChatHistory from "./components/ChatHistory";
import ActivityBar, { ActiveTool } from "./components/ActivityBar";
import ChatInput from "./components/ChatInput";
import WelcomeGuide from "./components/WelcomeGuide";

const GUIDE_SEEN_KEY = "painterAgent:guide-seen";
const SPLIT_RATIO_KEY = "painterAgent:split-ratio";
const SPLIT_MIN = 0.2;
const SPLIT_MAX = 0.8;
const SPLIT_DEFAULT = 0.4;

function loadSplitRatio(): number {
  const raw = localStorage.getItem(SPLIT_RATIO_KEY);
  const n = raw ? Number(raw) : NaN;
  if (!Number.isFinite(n)) return SPLIT_DEFAULT;
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, n));
}

export default function App() {
  const [guideOpen, setGuideOpen] = useState(
    () => localStorage.getItem(GUIDE_SEEN_KEY) !== "1"
  );
  const [manualCollapsed, setManualCollapsed] = useState(true);
  const [chatRatio, setChatRatio] = useState(loadSplitRatio);
  const [activeTool, setActiveTool] = useState<ActiveTool>(null);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);

  const splitRef = useRef<HTMLDivElement>(null);
  const resizingRef = useRef(false);

  const closeGuide = () => {
    localStorage.setItem(GUIDE_SEEN_KEY, "1");
    setGuideOpen(false);
  };

  const { theme, toggleTheme } = useTheme();

  const {
    turns,
    currentTurnId,
    loading,
    error,
    currentOutputUrl,
    currentInputUrl,
    currentInstruction,
    sendInstruction,
    selectTurn,
    handleImageUpload,
    handleMaskUpload,
    clearMask,
    maskFilename,
    handleMaskDrawingConfirm,
    handleSketchDrawingConfirm,
    sketchFilename,
    retry,
    deleteTurn,
    currentJobId,
    cancelExecution,
    hasPreviousSession,
    resumeSession,
    dismissPreviousSession,
  } = useSession();

  const sidebarCollapsed = manualCollapsed;

  const hasReferenceImage = !!(currentInputUrl || currentOutputUrl);

  // Wrap confirm callbacks to clear activeTool after upload
  const onMaskConfirm = useCallback(
    async (blob: Blob) => {
      await handleMaskDrawingConfirm(blob);
      setActiveTool(null);
    },
    [handleMaskDrawingConfirm]
  );

  const onMaskCancel = useCallback(() => {
    setActiveTool(null);
  }, []);

  const onSketchConfirm = useCallback(
    async (blob: Blob) => {
      await handleSketchDrawingConfirm(blob);
      setActiveTool(null);
      setUploadedFilename("白板草稿");
    },
    [handleSketchDrawingConfirm]
  );

  const onSketchCancel = useCallback(() => {
    setActiveTool(null);
  }, []);

  // ActivityBar callbacks
  const onUploadImage = useCallback(
    (imageId: string, imageUrl: string, filename: string) => {
      handleImageUpload(imageId, imageUrl);
      setUploadedFilename(filename);
    },
    [handleImageUpload]
  );

  const onStartWhiteboard = useCallback(() => {
    setActiveTool("whiteboard");
  }, []);

  const onUploadMask = useCallback(
    (imageId: string, imageUrl: string) => {
      handleMaskUpload(imageId, imageUrl);
    },
    [handleMaskUpload]
  );

  const onStartMaskDraw = useCallback(() => {
    setActiveTool("mask-draw");
  }, []);

  const onClearMask = useCallback(() => {
    clearMask();
  }, [clearMask]);

  // ChatInput callbacks
  const handleSend = useCallback(
    (instruction: string) => {
      setUploadedFilename(null);
      sendInstruction(instruction);
    },
    [sendInstruction]
  );

  const handleChatResize = useCallback((ratio: number) => {
    const clamped = Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, ratio));
    setChatRatio(clamped);
    localStorage.setItem(SPLIT_RATIO_KEY, String(clamped));
  }, []);

  const handleResizePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      resizingRef.current = true;
      splitRef.current?.classList.add("resizing");
      document.body.style.userSelect = "none";
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    []
  );

  const handleResizePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!resizingRef.current || !splitRef.current) return;
      const rect = splitRef.current.getBoundingClientRect();
      if (rect.width === 0) return;
      handleChatResize((e.clientX - rect.left) / rect.width);
    },
    [handleChatResize]
  );

  const handleResizePointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      splitRef.current?.classList.remove("resizing");
      document.body.style.userSelect = "";
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    },
    []
  );

  return (
    <div className="app">
      <header className="header">
        <h1>Painter Agent</h1>
        <div className="header-actions">
          <button
            className="btn-help"
            onClick={() => setGuideOpen(true)}
            title="使用教程"
          >
            ?
          </button>

          <button
            className="btn-sidebar-toggle"
            onClick={() => setManualCollapsed((v) => !v)}
            title={manualCollapsed ? "展开时间线" : "折叠时间线"}
          >
            {sidebarCollapsed ? "⤢" : "⤡"}
          </button>
          <button
            className="btn-theme"
            onClick={toggleTheme}
            title={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
          >
            {theme === "dark" ? "◑" : "◐"}
          </button>
          {error && <span className="header-error">{error}</span>}
        </div>
      </header>
      {hasPreviousSession && (
        <div className="resume-bar">
          <span>检测到上次会话记录</span>
          <button onClick={resumeSession} disabled={loading}>
            恢复上次会话
          </button>
          <button className="resume-bar-dismiss" onClick={dismissPreviousSession} title="忽略">
            ✕
          </button>
        </div>
      )}
      <div className="body">
        <ActivityBar
          activeTool={activeTool}
          hasReferenceImage={hasReferenceImage}
          maskFilename={maskFilename}
          sketchFilename={sketchFilename}
          loading={loading}
          onUploadImage={onUploadImage}
          onStartWhiteboard={onStartWhiteboard}
          onUploadMask={onUploadMask}
          onStartMaskDraw={onStartMaskDraw}
          onClearMask={onClearMask}
        />
        <div className="split-pane" ref={splitRef}>
          <div
            className="chat-panel"
            style={{ width: `${chatRatio * 100}%` }}
          >
            <ChatHistory
              turns={turns}
              currentTurnId={currentTurnId}
              loading={loading}
              onSelect={selectTurn}
              onRetry={retry}
              onDelete={deleteTurn}
            />
            <ChatInput
              loading={loading}
              activeTool={activeTool}
              uploadedFilename={uploadedFilename}
              maskFilename={maskFilename}
              sketchFilename={sketchFilename}
              currentJobId={currentJobId}
              onSubmit={handleSend}
              onCancel={cancelExecution}
            />
          </div>
          <div
            className="resize-handle"
            role="separator"
            aria-orientation="vertical"
            onPointerDown={handleResizePointerDown}
            onPointerMove={handleResizePointerMove}
            onPointerUp={handleResizePointerUp}
            onDoubleClick={() => handleChatResize(SPLIT_DEFAULT)}
            title="拖拽调整左右比例（双击恢复默认）"
          />
          <div className="workspace-panel">
            <ImageViewer
              inputUrl={currentInputUrl}
              outputUrl={currentOutputUrl}
              instruction={currentInstruction}
              loading={loading}
              activeTool={activeTool}
              onMaskDrawingConfirm={onMaskConfirm}
              onMaskDrawingCancel={onMaskCancel}
              onSketchDrawingConfirm={onSketchConfirm}
              onSketchDrawingCancel={onSketchCancel}
            />
          </div>
        </div>
        <TurnTimeline
          turns={turns}
          currentTurnId={currentTurnId}
          onSelect={selectTurn}
          onRetry={retry}
          onDelete={deleteTurn}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setManualCollapsed((v) => !v)}
        />
      </div>
      <WelcomeGuide open={guideOpen} onClose={closeGuide} />
    </div>
  );
}
