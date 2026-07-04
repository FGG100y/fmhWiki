import { useState } from "react";

interface Props {
  inputUrl: string | null;
  outputUrl: string | null;
  instruction: string | null;
  loading: boolean;
}

async function fetchAsBlob(url: string): Promise<Blob> {
  const res = await fetch(url);
  return res.blob();
}

async function toPngBlob(blob: Blob): Promise<Blob> {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return blob;
  ctx.drawImage(bitmap, 0, 0);
  return new Promise((resolve) =>
    canvas.toBlob((b) => resolve(b ?? blob), "image/png")
  );
}

function triggerDownload(url: string, filename: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function downloadImage(url: string) {
  const filename = `result_${Date.now()}.png`;
  try {
    const blob = await fetchAsBlob(url);
    const objectUrl = URL.createObjectURL(blob);
    triggerDownload(objectUrl, filename);
    URL.revokeObjectURL(objectUrl);
  } catch {
    triggerDownload(url, filename);
  }
}

async function copyImage(url: string): Promise<boolean> {
  try {
    const blob = await fetchAsBlob(url);
    const png = await toPngBlob(blob);
    await navigator.clipboard.write([
      new ClipboardItem({ "image/png": png }),
    ]);
    return true;
  } catch {
    return false;
  }
}

async function shareImage(url: string): Promise<"shared" | "copied" | "failed"> {
  try {
    const blob = await fetchAsBlob(url);
    const file = new File([blob], `result_${Date.now()}.png`, {
      type: blob.type || "image/png",
    });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({
        files: [file],
        title: "我的修图作品",
        text: "用多轮修图 Agent 生成",
      });
      return "shared";
    }
    if (navigator.share && /^https?:/.test(url)) {
      await navigator.share({ title: "我的修图作品", url });
      return "shared";
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return "shared";
  }
  const copied = await copyImage(url);
  return copied ? "copied" : "failed";
}

export default function ImageViewer({
  inputUrl,
  outputUrl,
  instruction,
  loading,
}: Props) {
  const [zoomUrl, setZoomUrl] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2000);
  };

  const handleCopy = async (url: string) => {
    const ok = await copyImage(url);
    showToast(ok ? "已复制图片到剪贴板" : "复制失败，请改用下载");
  };

  const handleShare = async (url: string) => {
    const result = await shareImage(url);
    if (result === "copied") showToast("当前环境不支持系统分享，已复制到剪贴板");
    else if (result === "failed") showToast("分享失败，请改用下载");
  };

  return (
    <main className="viewer">
      <div className="viewer-grid">
        <div className="image-panel">
          <div className="image-label">输入图片</div>
          <div className="image-container">
            {inputUrl ? (
              <img
                src={inputUrl}
                alt="输入图片"
                className="zoomable"
                onClick={() => setZoomUrl(inputUrl)}
                title="点击放大"
              />
            ) : (
              <div className="image-placeholder">
                {loading ? "生成中…" : "首轮将从文字生成图片"}
              </div>
            )}
          </div>
        </div>
        <div className="image-panel">
          <div className="image-label">
            结果图片
            {outputUrl && (
              <span className="image-actions">
                <button
                  className="btn-download"
                  onClick={() => handleShare(outputUrl)}
                  title="分享到其他 App"
                >
                  分享
                </button>
                <button
                  className="btn-download"
                  onClick={() => handleCopy(outputUrl)}
                  title="复制图片到剪贴板"
                >
                  复制
                </button>
                <button
                  className="btn-download"
                  onClick={() => downloadImage(outputUrl)}
                  title="下载结果图"
                >
                  下载
                </button>
              </span>
            )}
          </div>
          <div className="image-container">
            {outputUrl ? (
              <img
                src={outputUrl}
                alt="结果图片"
                className="zoomable"
                onClick={() => setZoomUrl(outputUrl)}
                title="点击放大"
              />
            ) : (
              <div className="image-placeholder">
                {loading ? (
                  <span className="spinner" />
                ) : instruction ? (
                  "处理失败"
                ) : (
                  "输入指令开始修图"
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      {instruction && (
        <div className="current-instruction">
          <strong>当前指令：</strong>
          {instruction}
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
      {zoomUrl && (
        <div className="zoom-overlay" onClick={() => setZoomUrl(null)}>
          <button
            className="zoom-close"
            onClick={() => setZoomUrl(null)}
            title="关闭"
          >
            ×
          </button>
          <img
            src={zoomUrl}
            alt="放大预览"
            className="zoom-image"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </main>
  );
}
