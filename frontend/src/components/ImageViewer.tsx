import { useState, useRef, useCallback, useEffect } from "react";
import MaskCanvas from "./MaskCanvas";
import SketchCanvas from "./SketchCanvas";
import type { ActiveTool } from "./ActivityBar";

interface Props {
  inputUrl: string | null;
  outputUrl: string | null;
  instruction: string | null;
  loading: boolean;
  activeTool: ActiveTool;
  maskUrl?: string | null;
  onMaskDrawingConfirm: (maskBlob: Blob) => void;
  onMaskDrawingCancel: () => void;
  onSketchDrawingConfirm: (blob: Blob) => void;
  onSketchDrawingCancel: () => void;
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
        text: "用Painter Agent 生成",
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

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 8;
const ZOOM_STEP = 0.15;

export default function ImageViewer({
  inputUrl,
  outputUrl,
  instruction,
  loading,
  activeTool,
  maskUrl,
  onMaskDrawingConfirm,
  onMaskDrawingCancel,
  onSketchDrawingConfirm,
  onSketchDrawingCancel,
}: Props) {
  const [zoomUrl, setZoomUrl] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const zoomState = useRef({
    scale: 1,
    x: 0,
    y: 0,
    dragging: false,
    lastX: 0,
    lastY: 0,
    pinchDist: 0,
    pinchScale: 1,
  });

  // ── Mask overlay ────────────────────────────────────
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const maskContainerRef = useRef<HTMLDivElement>(null);
  const baseImgRef = useRef<HTMLImageElement>(null);
  const processedMaskRef = useRef<HTMLCanvasElement | null>(null);
  const [processedMaskReady, setProcessedMaskReady] = useState(0);
  const maskUrlRef = useRef<string | null | undefined>(null);

  // Preprocess mask image: convert to red overlay (transparent where no mask)
  useEffect(() => {
    if (!maskUrl) {
      processedMaskRef.current = null;
      maskUrlRef.current = null;
      setProcessedMaskReady(0);
      return;
    }
    maskUrlRef.current = maskUrl;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      // Only update if this is still the current mask
      if (maskUrlRef.current !== maskUrl) return;
      const canvas = document.createElement("canvas");
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0);
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const data = imageData.data;
      for (let i = 0; i < data.length; i += 4) {
        const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
        if (brightness > 15) {
          data[i] = 220;       // R — warm red
          data[i + 1] = 30;
          data[i + 2] = 30;
          data[i + 3] = Math.min(255, brightness * 1.2);
        } else {
          data[i + 3] = 0;     // fully transparent
        }
      }
      ctx.putImageData(imageData, 0, 0);
      processedMaskRef.current = canvas;
      setProcessedMaskReady((n) => n + 1);
    };
    img.src = maskUrl;
  }, [maskUrl]);

  // Render mask overlay canvas sized to match the base img element
  useEffect(() => {
    const canvas = maskCanvasRef.current;
    const container = maskContainerRef.current;
    const baseImg = baseImgRef.current;
    if (!canvas || !container || !baseImg) return;
    if (!maskUrl) return;

    const renderOverlay = () => {
      const processed = processedMaskRef.current;
      if (!processed) return;
      const imgRect = baseImg.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const cw = containerRect.width;
      const ch = containerRect.height;
      if (cw === 0 || ch === 0) return;
      canvas.width = cw * dpr;
      canvas.height = ch * dpr;
      canvas.style.width = `${cw}px`;
      canvas.style.height = `${ch}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cw, ch);
      // Draw processed mask at the same position/size as the base img
      const ox = imgRect.left - containerRect.left;
      const oy = imgRect.top - containerRect.top;
      ctx.globalAlpha = 0.5;
      ctx.drawImage(processed, ox, oy, imgRect.width, imgRect.height);
    };

    renderOverlay();
    const observer = new ResizeObserver(renderOverlay);
    observer.observe(baseImg);
    return () => observer.disconnect();
  }, [maskUrl, processedMaskReady]);

  const applyTransform = useCallback(() => {
    const img = imgRef.current;
    if (!img) return;
    const { scale, x, y } = zoomState.current;
    img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    img.style.cursor = scale > 1 ? "grab" : "default";
  }, []);

  const resetZoom = useCallback(() => {
    zoomState.current = { scale: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0, pinchDist: 0, pinchScale: 1 };
    applyTransform();
  }, [applyTransform]);

  useEffect(() => {
    if (!zoomUrl) return;
    resetZoom();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomUrl(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomUrl, resetZoom]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const s = zoomState.current;
    const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
    s.scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, s.scale + delta));
    if (s.scale <= 1) { s.x = 0; s.y = 0; }
    applyTransform();
  }, [applyTransform]);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    const s = zoomState.current;
    if (s.scale <= 1) return;
    s.dragging = true;
    s.lastX = e.clientX;
    s.lastY = e.clientY;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    if (imgRef.current) imgRef.current.style.cursor = "grabbing";
  }, []);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const s = zoomState.current;
    if (!s.dragging) return;
    s.x += e.clientX - s.lastX;
    s.y += e.clientY - s.lastY;
    s.lastX = e.clientX;
    s.lastY = e.clientY;
    applyTransform();
  }, [applyTransform]);

  const handlePointerUp = useCallback(() => {
    zoomState.current.dragging = false;
    if (imgRef.current) {
      imgRef.current.style.cursor = zoomState.current.scale > 1 ? "grab" : "default";
    }
  }, []);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      zoomState.current.pinchDist = Math.hypot(dx, dy);
      zoomState.current.pinchScale = zoomState.current.scale;
    }
  }, []);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const dist = Math.hypot(dx, dy);
      const s = zoomState.current;
      s.scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, s.pinchScale * (dist / s.pinchDist)));
      if (s.scale <= 1) { s.x = 0; s.y = 0; }
      applyTransform();
    }
  }, [applyTransform]);

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

  const isShowingOutput = !!outputUrl;
  const mainUrl = outputUrl ?? inputUrl;
  const showReference = !!inputUrl && isShowingOutput && inputUrl !== outputUrl;

  if (activeTool === "mask-draw") {
    return (
      <main className="viewer">
        <MaskCanvas
          imageUrl={inputUrl || outputUrl || ""}
          onConfirm={onMaskDrawingConfirm}
          onCancel={onMaskDrawingCancel}
        />
        {toast && <div className="toast">{toast}</div>}
      </main>
    );
  }

  if (activeTool === "whiteboard") {
    return (
      <main className="viewer">
        <SketchCanvas
          onConfirm={onSketchDrawingConfirm}
          onCancel={onSketchDrawingCancel}
        />
        {toast && <div className="toast">{toast}</div>}
      </main>
    );
  }

  return (
    <main className="viewer">
      <div className="viewer-focus">
        <div className="image-panel">
          <div className="image-label">
            {isShowingOutput ? "结果图片" : "输入图片"}
            {isShowingOutput && (
              <span className="image-actions">
                <button
                  className="btn-download"
                  onClick={() => handleShare(outputUrl!)}
                  title="分享到其他 App"
                >
                  分享
                </button>
                <button
                  className="btn-download"
                  onClick={() => handleCopy(outputUrl!)}
                  title="复制图片到剪贴板"
                >
                  复制
                </button>
                <button
                  className="btn-download"
                  onClick={() => downloadImage(outputUrl!)}
                  title="下载结果图"
                >
                  下载
                </button>
              </span>
            )}
          </div>
          <div
            className={`image-container output-container${maskUrl && !isShowingOutput ? " mask-container" : ""}`}
            ref={maskUrl && !isShowingOutput ? maskContainerRef : undefined}
            style={maskUrl && !isShowingOutput ? { position: "relative" } : undefined}
          >
            {mainUrl ? (
              <>
                <img
                  ref={baseImgRef}
                  src={mainUrl}
                  alt={isShowingOutput ? "结果图片" : "输入图片"}
                  className="zoomable"
                  onClick={() => setZoomUrl(mainUrl)}
                  title="点击放大"
                />
                {maskUrl && !isShowingOutput && (
                  <canvas
                    ref={maskCanvasRef}
                    className="mask-overlay-canvas"
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: "100%",
                      pointerEvents: "none",
                    }}
                  />
                )}
              </>
            ) : (
              <div className="image-placeholder">
                {loading ? (
                  <span className="spinner" />
                ) : (
                  "输入指令开始修图"
                )}
              </div>
            )}
          </div>
        </div>

        {showReference && (
          <div className="reference-thumb">
            <div className="reference-label">输入</div>
            <img
              src={inputUrl!}
              alt="输入图片"
              onClick={() => setZoomUrl(inputUrl)}
              title="点击放大输入图"
            />
          </div>
        )}
      </div>
      {instruction && (
        <div className="current-instruction">
          <strong>当前指令：</strong>
          {instruction}
        </div>
      )}
      {toast && <div className="toast">{toast}</div>}
      {zoomUrl && (
        <div
          className="zoom-overlay"
          onClick={() => setZoomUrl(null)}
          onWheel={handleWheel}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
        >
          <button
            className="zoom-close"
            onClick={() => setZoomUrl(null)}
            title="关闭"
          >
            ×
          </button>
          <div className="zoom-hint">滚轮缩放 · 拖拽平移 · 双指手势</div>
          <div
            className="zoom-image-wrap"
            ref={containerRef}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
          >
            <img
              ref={imgRef}
              src={zoomUrl}
              alt="放大预览"
              className="zoom-image"
              draggable={false}
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </main>
  );
}
