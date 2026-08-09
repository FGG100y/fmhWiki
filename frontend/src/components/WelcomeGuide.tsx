import { useLayoutEffect, useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onStepChange: (step: number) => void;
}

interface Step {
  title: string;
  body: string;
  hint?: string;
  /** 对应 UI 区域的描述，用于定位 */
  target?: string;
}

const STEPS: Step[] = [
  {
    title: "欢迎使用 Painter Agent 👋",
    body: "用一句话生成图片，或上传自己的图片进行编辑。整个过程像聊天一样自然——直接说出你想要的效果即可。",
  },
  {
    title: "① 选择执行方式",
    body: "左侧工具栏底部有三个模式按钮，决定了系统如何处理你的指令：\n\n• 单步 — 一次只做一个编辑，适合精确控制或示范操作\n• 默认 — 由系统决定，日常使用推荐\n• 多步 — 一句话包含多个编辑动作时（如「把背景换成海边，人物衣服改成红色」），模型会自动拆解并依次执行",
    hint: "不确定时保持「默认」即可。",
    target: "左侧工具栏底部的 单步 | 默认 | 多步 按钮",
  },
  {
    title: "② 上传图片 / 输入指令",
    body: "在底部输入框直接描述画面（例如「一只在草地上奔跑的柴犬」）即可文字生成图片；也可以点左侧工具栏「图片」上传一张图作为编辑起点，或点「白板」自由绘制草图，让模型帮你完善成图。",
    hint: "按 Enter 发送，Shift+Enter 换行。",
    target: "底部输入框和左侧工具栏的 图片 | 白板 按钮",
  },
  {
    title: "③ 局部重绘（Mask）",
    body: "只想修改图片的局部区域？点左侧工具栏「绘制」在图上涂抹白色区域，或点「Mask」上传遮罩图片，再配合指令，模型只重绘被标记的区域。例如涂掉画面里的路人，指令写「把路人去掉」。",
    target: "左侧工具栏的 Mask | 绘制 按钮",
  },
  {
    title: "④ 迭代与历史",
    body: "每一步编辑都会基于上一步结果继续。右侧「编辑历史」面板记录了每一步，点击任意节点即可回到该版本，并从那里开出新的编辑分支。结果图可随时下载，失败的任务可点击 ↻ 重试。",
    hint: "随时点击右上角的 ? 重新查看本教程。",
    target: "右侧「编辑历史」面板",
  },
];

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export default function WelcomeGuide({ open, onClose, onStepChange }: Props) {
  const [step, setStep] = useState(0);
  const [targetRects, setTargetRects] = useState<Rect[]>([]);

  // 切步骤时同步通知 App（消除高亮与遮罩开洞之间的延迟）
  const goToStep = (next: number) => {
    setStep(next);
    onStepChange(next);
  };

  const handleClose = () => {
    setStep(0);
    onStepChange(-1);
    onClose();
  };

  // 用 useLayoutEffect：在浏览器绘制前同步测量，消除聚光灯滞后
  useLayoutEffect(() => {
    if (!open) return;

    const measure = () => {
      const els = document.querySelectorAll<HTMLElement>(".guide-highlight");
      const rects: Rect[] = [];
      els.forEach((el) => {
        const r = el.getBoundingClientRect();
        rects.push({ top: r.top, left: r.left, width: r.width, height: r.height });
      });
      setTargetRects(rects);
    };

    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
      setTargetRects([]);
    };
  }, [open, step]);

  if (!open) return null;

  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];

  // 高亮区域 padding，洞口比高亮元素稍大一圈
  const HOLE_PAD = 6;
  const RR = 8; // 洞口圆角

  return (
    <div className="guide-overlay" onClick={handleClose}>
      {targetRects.length > 0 ? (
        <svg
          className="guide-mask-svg"
          style={{ position: "fixed", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        >
          <defs>
            <mask id="guide-spotlight-mask">
              <rect width="100%" height="100%" fill="white" />
              {targetRects.map((r, i) => (
                <rect
                  key={i}
                  x={r.left - HOLE_PAD}
                  y={r.top - HOLE_PAD}
                  width={r.width + HOLE_PAD * 2}
                  height={r.height + HOLE_PAD * 2}
                  fill="black"
                  rx={RR}
                  ry={RR}
                />
              ))}
            </mask>
          </defs>
          <rect
            width="100%"
            height="100%"
            className="guide-mask-overlay"
            mask="url(#guide-spotlight-mask)"
          />
        </svg>
      ) : (
        <div className="guide-dim" />
      )}
      <div
        className="guide-modal"
        role="dialog"
        aria-modal="true"
        aria-label="使用教程"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="guide-skip" onClick={handleClose} title="关闭">
          ✕
        </button>
        <h2 className="guide-title">{current.title}</h2>
        {current.target && (
          <p className="guide-target">📍 {current.target}</p>
        )}
        <p className="guide-body" style={{ whiteSpace: "pre-line" }}>{current.body}</p>
        {current.hint && <p className="guide-hint">💡 {current.hint}</p>}

        <div className="guide-dots">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`guide-dot ${i === step ? "active" : ""}`}
              onClick={() => goToStep(i)}
            />
          ))}
        </div>

        <div className="guide-actions">
          {!isFirst ? (
            <button
              className="guide-btn-secondary"
              onClick={() => goToStep(step - 1)}
            >
              上一步
            </button>
          ) : (
            <button className="guide-btn-secondary" onClick={handleClose}>
              跳过
            </button>
          )}
          {isLast ? (
            <button className="guide-btn-primary" onClick={handleClose}>
              开始使用
            </button>
          ) : (
            <button
              className="guide-btn-primary"
              onClick={() => goToStep(step + 1)}
            >
              下一步
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
