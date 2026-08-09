import { useRef, useState } from "react";
import { uploadImage } from "../api";
import type { ExecutionMode } from "../hooks/useSession";

export type ActiveTool = null | "whiteboard" | "mask-draw";

interface Props {
  activeTool: ActiveTool;
  hasReferenceImage: boolean;
  maskFilename: string | null;
  sketchFilename: string | null;
  loading: boolean;
  executionMode: ExecutionMode;
  onModeChange: (mode: ExecutionMode) => void;
  onUploadImage: (imageId: string, imageUrl: string, filename: string) => void;
  onStartWhiteboard: () => void;
  onUploadMask: (imageId: string, imageUrl: string) => void;
  onStartMaskDraw: () => void;
  onClearMask: () => void;
}

const MODES: { key: ExecutionMode; label: string; hint: string }[] = [
  { key: "deterministic", label: "单步", hint: "一次只做一个编辑，适合精确控制" },
  { key: "auto", label: "默认", hint: "由系统决定执行方式" },
  { key: "agentic", label: "多步", hint: "一句话包含多个编辑动作时自动拆解执行" },
];

export default function ActivityBar({
  activeTool,
  hasReferenceImage,
  maskFilename,
  sketchFilename,
  loading,
  executionMode,
  onModeChange,
  onUploadImage,
  onStartWhiteboard,
  onUploadMask,
  onStartMaskDraw,
  onClearMask,
}: Props) {
  const [uploading, setUploading] = useState(false);
  const [maskUploading, setMaskUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const maskRef = useRef<HTMLInputElement>(null);

  const isDrawing = activeTool !== null;
  const isDisabled = loading || isDrawing;

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const resp = await uploadImage(file);
      onUploadImage(resp.image_id, resp.image_url, file.name);
    } catch (err) {
      console.error("upload failed", err);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleMaskChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setMaskUploading(true);
    try {
      const resp = await uploadImage(file);
      onUploadMask(resp.image_id, resp.image_url);
    } catch (err) {
      console.error("mask upload failed", err);
    } finally {
      setMaskUploading(false);
      if (maskRef.current) maskRef.current.value = "";
    }
  };

  return (
    <div className="activity-bar">
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />
      <input
        ref={maskRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: "none" }}
        onChange={handleMaskChange}
      />

      {/* Upload Image */}
      <button
        className={`activity-bar-btn ${uploading ? "uploading" : ""}`}
        onClick={() => fileRef.current?.click()}
        disabled={isDisabled || uploading}
        title="上传图片"
      >
        <span className="activity-bar-icon">📷</span>
        <span className="activity-bar-label">图片</span>
      </button>

      {/* Whiteboard */}
      <button
        className={`activity-bar-btn ${activeTool === "whiteboard" ? "active" : ""} ${sketchFilename ? "has-content" : ""}`}
        onClick={onStartWhiteboard}
        disabled={isDisabled || uploading}
        title="白板绘制草图"
      >
        <span className="activity-bar-icon">✏️</span>
        <span className="activity-bar-label">白板</span>
        {sketchFilename && <span className="activity-bar-dot" />}
      </button>

      {/* Upload Mask */}
      <button
        className={`activity-bar-btn ${maskFilename ? "has-content" : ""}`}
        onClick={() => maskRef.current?.click()}
        disabled={isDisabled || maskUploading}
        title={maskFilename ? `Mask: ${maskFilename}（点击更换，悬停清除）` : "上传 Mask 图片"}
      >
        <span className="activity-bar-icon">🎭</span>
        <span className="activity-bar-label">Mask</span>
        {maskFilename && (
          <span
            className="activity-bar-dot activity-bar-dot-clear"
            onClick={(e) => {
              e.stopPropagation();
              onClearMask();
            }}
            title="清除 Mask"
          />
        )}
      </button>

      {/* Draw Mask */}
      <button
        className={`activity-bar-btn ${activeTool === "mask-draw" ? "active" : ""}`}
        onClick={onStartMaskDraw}
        disabled={isDisabled || !hasReferenceImage || maskUploading}
        title={hasReferenceImage ? "在图片上绘制 Mask" : "需要先上传参考图才能绘制 Mask"}
      >
        <span className="activity-bar-icon">🖌️</span>
        <span className="activity-bar-label">绘制</span>
      </button>

      {/* Separator */}
      <div className="activity-bar-sep" />

      {/* Execution Mode */}
      <div className="activity-bar-mode">
        {MODES.map((m) => (
          <button
            key={m.key}
            className={`mode-seg-btn ${executionMode === m.key ? "active" : ""}`}
            onClick={() => onModeChange(m.key)}
            disabled={loading}
            title={m.hint}
          >
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
}
