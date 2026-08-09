import { useRef, useState, useCallback, useEffect } from "react";

interface Props {
  imageUrl: string;
  onConfirm: (maskBlob: Blob) => void;
  onCancel: () => void;
}

export default function MaskCanvas({ imageUrl, onConfirm, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const drawingRef = useRef(false);
  const lastPosRef = useRef({ x: 0, y: 0 });

  const [brushSize, setBrushSize] = useState(20);
  const [tool, setTool] = useState<"draw" | "erase">("draw");
  const [loaded, setLoaded] = useState(false);

  const getPos = useCallback(
    (e: React.PointerEvent | PointerEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      };
    },
    []
  );

  const drawLine = useCallback(
    (x1: number, y1: number, x2: number, y2: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.globalCompositeOperation =
        tool === "erase" ? "destination-out" : "source-over";
      ctx.strokeStyle = tool === "erase" ? "rgba(0,0,0,1)" : "rgba(255,0,0,0.5)";
      ctx.lineWidth = brushSize;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    },
    [tool, brushSize]
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      drawingRef.current = true;
      const pos = getPos(e);
      lastPosRef.current = pos;
      const canvas = canvasRef.current;
      if (canvas) canvas.setPointerCapture(e.pointerId);
      drawLine(pos.x, pos.y, pos.x, pos.y);
    },
    [getPos, drawLine]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!drawingRef.current) return;
      const pos = getPos(e);
      drawLine(lastPosRef.current.x, lastPosRef.current.y, pos.x, pos.y);
      lastPosRef.current = pos;
    },
    [getPos, drawLine]
  );

  const handlePointerUp = useCallback(() => {
    drawingRef.current = false;
  }, []);

  const handleClear = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }, []);

  const handleConfirm = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = img.naturalWidth;
    exportCanvas.height = img.naturalHeight;
    const ctx = exportCanvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
    ctx.drawImage(canvas, 0, 0, exportCanvas.width, exportCanvas.height);
    exportCanvas.toBlob((blob) => {
      if (blob) onConfirm(blob);
    }, "image/png");
  }, [onConfirm]);

  useEffect(() => {
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      imgRef.current = img;
      setLoaded(true);
    };
    img.src = imageUrl;
    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  // Resize canvas to match the container and image aspect ratio.
  // Runs on container resize AND when the image finishes loading.
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    const img = imgRef.current;
    if (!canvas || !container || !img) return;

    const resize = () => {
      const containerW = container.clientWidth;
      const containerH = container.clientHeight;
      if (containerW === 0 || containerH === 0) return;
      const scale = Math.min(containerW / img.width, containerH / img.height, 1);
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      canvas.width = w;
      canvas.height = h;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    return () => observer.disconnect();
  }, [imageUrl, loaded]);

  return (
    <div className="mask-canvas-wrapper">
      <div className="mask-canvas-toolbar">
        <button
          className={`mask-tool-btn ${tool === "draw" ? "active" : ""}`}
          onClick={() => setTool("draw")}
          title="画笔"
        >
          ✏️
        </button>
        <button
          className={`mask-tool-btn ${tool === "erase" ? "active" : ""}`}
          onClick={() => setTool("erase")}
          title="橡皮擦"
        >
          🧹
        </button>
        <input
          type="range"
          min={4}
          max={80}
          value={brushSize}
          onChange={(e) => setBrushSize(Number(e.target.value))}
          className="mask-brush-slider"
          title={`画笔大小: ${brushSize}px`}
        />
        <span className="mask-brush-label">{brushSize}px</span>
        <button className="mask-tool-btn" onClick={handleClear} title="清除全部">
          🗑️
        </button>
        <div className="mask-toolbar-spacer" />
        <button className="mask-btn-cancel" onClick={onCancel}>
          取消
        </button>
        <button className="mask-btn-confirm" onClick={handleConfirm} disabled={!loaded}>
          确认 Mask
        </button>
      </div>
      <div
        className="mask-canvas-container"
        ref={containerRef}
        style={{ cursor: tool === "draw" ? "crosshair" : "cell" }}
      >
        <img
          src={imageUrl}
          alt="底图"
          className="mask-base-img"
          draggable={false}
        />
        <canvas
          ref={canvasRef}
          className="mask-draw-canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        />
      </div>
    </div>
  );
}
