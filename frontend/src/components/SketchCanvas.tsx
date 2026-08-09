import { useRef, useState, useCallback, useEffect } from "react";

interface Props {
  onConfirm: (blob: Blob) => void;
  onCancel: () => void;
}

const COLORS = ["#000000", "#e74c3c", "#3498db", "#2ecc71", "#f1c40f", "#9b59b6"];
const MIN_SIZE = 512;
const MAX_SIZE = 4096;

interface CanvasDims {
  width: number;
  height: number;
}

/** Brush slider range scales with the shorter canvas dimension */
function brushRange(shortSide: number) {
  return {
    min: Math.max(1, Math.round(shortSide * 0.002)),
    max: Math.round(shortSide * 0.10),
  };
}

function defaultBrush(shortSide: number) {
  return Math.round(shortSide * 0.015);
}

export default function SketchCanvas({ onConfirm, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const drawingRef = useRef(false);
  const lastPosRef = useRef({ x: 0, y: 0 });

  const [canvasDims, setCanvasDims] = useState<CanvasDims>({ width: MIN_SIZE, height: MIN_SIZE });
  const [tool, setTool] = useState<"draw" | "erase">("draw");
  const [color, setColor] = useState("#000000");
  const [brushSize, setBrushSize] = useState(defaultBrush(MIN_SIZE));

  // Observe container size and set canvas dimensions to fill available space
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.min(MAX_SIZE, Math.max(MIN_SIZE, Math.floor(entry.contentRect.width)));
        const h = Math.min(MAX_SIZE, Math.max(MIN_SIZE, Math.floor(entry.contentRect.height)));
        setCanvasDims((prev) =>
          prev.width === w && prev.height === h ? prev : { width: w, height: h }
        );
      }
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // Initialize canvas with white background when dimensions change
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }, [canvasDims]);

  const shortSide = Math.min(canvasDims.width, canvasDims.height);
  const brush = brushRange(shortSide);
  // Clamp current brush value within range (handles resize shrinking the range)
  const clampedBrush = Math.min(brush.max, Math.max(brush.min, brushSize));

  const getPos = useCallback((e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * canvas.height,
    };
  }, []);

  const drawLine = useCallback(
    (x1: number, y1: number, x2: number, y2: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.globalCompositeOperation =
        tool === "erase" ? "destination-out" : "source-over";
      ctx.strokeStyle = tool === "erase" ? "rgba(0,0,0,1)" : color;
      ctx.lineWidth = clampedBrush;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    },
    [tool, color, clampedBrush]
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
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }, []);

  const handleConfirm = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const exportCanvas = document.createElement("canvas");
    exportCanvas.width = canvas.width;
    exportCanvas.height = canvas.height;
    const ctx = exportCanvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, exportCanvas.width, exportCanvas.height);
    ctx.drawImage(canvas, 0, 0);
    exportCanvas.toBlob((blob) => {
      if (blob) onConfirm(blob);
    }, "image/png");
  }, [onConfirm]);

  return (
    <div className="sketch-canvas-wrapper">
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
        <span className="sketch-color-palette">
          {COLORS.map((c) => (
            <button
              key={c}
              className={`sketch-color-btn ${color === c ? "active" : ""}`}
              style={{ backgroundColor: c }}
              onClick={() => setColor(c)}
              title={c}
            />
          ))}
        </span>
        <input
          type="range"
          min={brush.min}
          max={brush.max}
          value={clampedBrush}
          onChange={(e) => setBrushSize(Number(e.target.value))}
          className="mask-brush-slider"
          title={`画笔大小: ${clampedBrush}px`}
        />
        <span className="mask-brush-label">{clampedBrush}px</span>
        <button className="mask-tool-btn" onClick={handleClear} title="清除全部">
          🗑️
        </button>
        <div className="mask-toolbar-spacer" />
        <button className="mask-btn-cancel" onClick={onCancel}>
          取消
        </button>
        <button className="mask-btn-confirm" onClick={handleConfirm}>
          确认草稿
        </button>
      </div>
      <div
        className="sketch-canvas-container"
        ref={containerRef}
        style={{ cursor: tool === "draw" ? "crosshair" : "cell" }}
      >
        <canvas
          ref={canvasRef}
          width={canvasDims.width}
          height={canvasDims.height}
          className="sketch-canvas"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        />
      </div>
    </div>
  );
}
