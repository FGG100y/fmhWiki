import { useState } from "react";
import type { ActiveTool } from "./ActivityBar";
import type { ExecutionMode } from "../hooks/useSession";

interface Props {
  loading: boolean;
  activeTool: ActiveTool;
  uploadedFilename: string | null;
  maskFilename: string | null;
  sketchFilename: string | null;
  currentJobId: string | null;
  executionMode: ExecutionMode;
  onModeChange: (mode: ExecutionMode) => void;
  onSubmit: (instruction: string) => void;
  onCancel: (jobId: string) => void;
}

const MODE_LABELS: Record<ExecutionMode, string> = {
  deterministic: "确定性",
  auto: "自动",
  agentic: "Agentic",
};

const MODE_HINTS: Record<ExecutionMode, string> = {
  deterministic: "每次执行单个编辑，适合示范操作",
  auto: "系统自动选择（默认）",
  agentic: "模型自主拆解多步编辑",
};

function getPlaceholder(
  activeTool: ActiveTool,
  uploadedFilename: string | null,
  maskFilename: string | null,
  sketchFilename: string | null
): string {
  if (activeTool === "whiteboard") {
    return "请在右侧白板上绘制草图，完成后点击确认…";
  }
  if (activeTool === "mask-draw") {
    return "请在右侧图片上绘制 Mask，完成后点击确认…";
  }
  if (sketchFilename !== null) {
    return "已绘制草稿，输入美化指令…";
  }
  if (uploadedFilename !== null) {
    return `已选 ${uploadedFilename}，输入修图指令…`;
  }
  if (maskFilename !== null) {
    return "已上传 Mask，输入局部编辑指令…";
  }
  return "输入修图指令，例如：把背景换成海边日落…";
}

export default function ChatInput({
  loading,
  activeTool,
  uploadedFilename,
  maskFilename,
  sketchFilename,
  currentJobId,
  executionMode,
  onModeChange,
  onSubmit,
  onCancel,
}: Props) {
  const [value, setValue] = useState("");
  const isDrawing = activeTool !== null;

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading || isDrawing) return;
    onSubmit(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const cycleMode = () => {
    const modes: ExecutionMode[] = ["deterministic", "auto", "agentic"];
    const idx = modes.indexOf(executionMode);
    onModeChange(modes[(idx + 1) % modes.length]);
  };

  const placeholder = getPlaceholder(
    activeTool,
    uploadedFilename,
    maskFilename,
    sketchFilename
  );

  return (
    <div className="chat-input">
      <button
        className="mode-switch"
        onClick={cycleMode}
        disabled={loading}
        title={MODE_HINTS[executionMode]}
        type="button"
      >
        {MODE_LABELS[executionMode]}
      </button>
      <input
        className="input-field"
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading || isDrawing}
      />
      {loading && currentJobId ? (
        <button
          className="btn-cancel"
          onClick={() => onCancel(currentJobId)}
          title="取消当前任务"
        >
          取消
        </button>
      ) : (
        <button
          className="btn-send"
          onClick={handleSubmit}
          disabled={loading || isDrawing || !value.trim()}
        >
          发送
        </button>
      )}
    </div>
  );
}
