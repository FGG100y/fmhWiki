import { useState } from "react";
import { useSession } from "./hooks/useSession";
import TurnTimeline from "./components/TurnTimeline";
import ImageViewer from "./components/ImageViewer";
import InstructionInput from "./components/InstructionInput";
import WelcomeGuide from "./components/WelcomeGuide";

const GUIDE_SEEN_KEY = "image-editor:guide-seen";

export default function App() {
  const [guideOpen, setGuideOpen] = useState(
    () => localStorage.getItem(GUIDE_SEEN_KEY) !== "1"
  );

  const closeGuide = () => {
    localStorage.setItem(GUIDE_SEEN_KEY, "1");
    setGuideOpen(false);
  };

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
    maskDrawingMode,
    startMaskDrawing,
    cancelMaskDrawing,
    handleMaskDrawingConfirm,
    undo,
    redo,
    canUndo,
    canRedo,
    retry,
    deleteTurn,
    currentJobId,
    cancelExecution,
  } = useSession();

  return (
    <div className="app">
      <header className="header">
        <h1>多轮修图 Agent</h1>
        <div className="header-actions">
          <button
            className="btn-help"
            onClick={() => setGuideOpen(true)}
            title="使用教程"
          >
            ?
          </button>
          <button
            className="btn-undo"
            onClick={undo}
            disabled={loading || !canUndo}
            title="撤销"
          >
            ↩
          </button>
          <button
            className="btn-redo"
            onClick={redo}
            disabled={loading || !canRedo}
            title="重做"
          >
            ↪
          </button>
          {error && <span className="header-error">{error}</span>}
        </div>
      </header>
      <div className="body">
        <TurnTimeline
          turns={turns}
          currentTurnId={currentTurnId}
          onSelect={selectTurn}
          onRetry={retry}
          onDelete={deleteTurn}
        />
        <div className="main-area">
          <ImageViewer
            inputUrl={currentInputUrl}
            outputUrl={currentOutputUrl}
            instruction={currentInstruction}
            loading={loading}
            maskDrawingMode={maskDrawingMode}
            onMaskDrawingConfirm={handleMaskDrawingConfirm}
            onMaskDrawingCancel={cancelMaskDrawing}
          />
          <InstructionInput
            onSubmit={sendInstruction}
            loading={loading}
            onImageUpload={handleImageUpload}
            onMaskUpload={handleMaskUpload}
            maskFilename={maskFilename}
            onClearMask={clearMask}
            maskDrawingMode={maskDrawingMode}
            onStartMaskDrawing={startMaskDrawing}
            hasInputImage={!!currentInputUrl}
            currentJobId={currentJobId}
            onCancel={cancelExecution}
          />
        </div>
      </div>
      <WelcomeGuide open={guideOpen} onClose={closeGuide} />
    </div>
  );
}
