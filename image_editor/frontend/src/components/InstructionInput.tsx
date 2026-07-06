import { useState, useRef } from "react";
import { uploadImage } from "../api";

interface Props {
  onSubmit: (instruction: string) => void;
  loading: boolean;
  onImageUpload: (imageId: string, imageUrl: string) => void;
  onMaskUpload: (imageId: string, imageUrl: string) => void;
  maskFilename: string | null;
  onClearMask: () => void;
  maskDrawingMode: boolean;
  onStartMaskDrawing: () => void;
  hasInputImage: boolean;
  currentJobId: string | null;
  onCancel: (jobId: string) => void;
}

export default function InstructionInput({
  onSubmit,
  loading,
  onImageUpload,
  onMaskUpload,
  maskFilename,
  onClearMask,
  maskDrawingMode,
  onStartMaskDrawing,
  hasInputImage,
  currentJobId,
  onCancel,
}: Props) {
  const [value, setValue] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadedFilename, setUploadedFilename] = useState<string | null>(null);
  const [maskUploading, setMaskUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const maskRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    if (maskDrawingMode) return;
    onSubmit(trimmed);
    setValue("");
    setUploadedFilename(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const resp = await uploadImage(file);
      onImageUpload(resp.image_id, resp.image_url);
      setUploadedFilename(file.name);
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
      onMaskUpload(resp.image_id, resp.image_url);
    } catch (err) {
      console.error("mask upload failed", err);
    } finally {
      setMaskUploading(false);
      if (maskRef.current) maskRef.current.value = "";
    }
  };

  return (
    <div className="input-bar">
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
      <button
        className="btn-upload"
        onClick={() => fileRef.current?.click()}
        disabled={loading || uploading}
        title="选择图片作为修图起点"
      >
        {uploading ? "上传中…" : uploadedFilename ? "已选图片" : "选择图片"}
      </button>
      <button
        className={`btn-upload btn-mask ${maskFilename ? "btn-mask-active" : ""}`}
        onClick={() => maskRef.current?.click()}
        disabled={loading || maskUploading || maskDrawingMode}
        title="上传 Mask 图片（白色区域=编辑区域）"
      >
        {maskUploading
          ? "上传中…"
          : maskFilename
          ? `Mask: ${maskFilename}`
          : "上传 Mask"}
      </button>
      <button
        className={`btn-upload btn-mask-draw ${maskDrawingMode ? "btn-mask-active" : ""}`}
        onClick={onStartMaskDrawing}
        disabled={loading || !hasInputImage}
        title="在图片上绘制 Mask（白色区域=编辑区域）"
      >
        {maskDrawingMode ? "绘制中…" : "绘制 Mask"}
      </button>
      {maskFilename && !maskDrawingMode && (
        <button
          className="btn-mask-clear"
          onClick={onClearMask}
          disabled={loading}
          title="清除 Mask"
        >
          ×
        </button>
      )}
      <input
        className="input-field"
        type="text"
        placeholder={
          uploadedFilename
            ? `已选 ${uploadedFilename}，输入修图指令…`
            : maskFilename
            ? `已上传 Mask，输入局部编辑指令…`
            : maskDrawingMode
            ? "请在左侧图片上绘制 Mask，完成后点击确认…"
            : "请输入修图指令，例如：把背景换成海边日落…"
        }
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading || maskDrawingMode}
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
          disabled={loading || maskDrawingMode || !value.trim()}
        >
          发送
        </button>
      )}
    </div>
  );
}
