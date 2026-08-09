import { useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Step {
  title: string;
  body: string;
  hint?: string;
}

const STEPS: Step[] = [
  {
    title: "欢迎使用Painter Agent 👋",
    body: "用一句话生成图片，或上传自己的图片进行编辑。整个过程像聊天一样自然——直接说出你想要的效果即可。",
  },
  {
    title: "① 生成、上传或白板",
    body: "在底部输入框直接描述画面（例如「一只在草地上奔跑的柴犬」）即可文字生成图片；也可以点「选择图片」上传一张图作为编辑起点，或点「白板」自由绘制草图，让模型帮你完善成图。",
    hint: "按 Enter 发送，Shift+Enter 换行。",
  },
  {
    title: "② 局部重绘（Mask）",
    body: "只想修改图片的局部区域？点「绘制 Mask」在图上涂抹白色区域，或「上传 Mask」，再配合指令，模型只重绘白色区域。例如涂掉画面里的路人，指令写「把路人去掉」。",
  },
  {
    title: "③ 多轮迭代编辑",
    body: "每一次指令都会在上一张结果的基础上继续修改，例如「把背景换成海边日落」「让整体更暖一些」。反复微调，直到满意为止。",
  },
  {
    title: "④ 撤销、重做与历史",
    body: "顶部的 ↩ ↪ 可以撤销 / 重做。左侧「编辑历史」记录了每一步，点击任意节点即可回到该版本，并从这里开出新的编辑分支。结果图可随时下载、复制或分享，失败的任务可点击 ↻ 重试。",
    hint: "随时点击右上角的 ? 重新查看本教程。",
  },
];

export default function WelcomeGuide({ open, onClose }: Props) {
  const [step, setStep] = useState(0);

  if (!open) return null;

  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;
  const current = STEPS[step];

  const handleClose = () => {
    setStep(0);
    onClose();
  };

  return (
    <div className="guide-overlay" onClick={handleClose}>
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
        <p className="guide-body">{current.body}</p>
        {current.hint && <p className="guide-hint">💡 {current.hint}</p>}

        <div className="guide-dots">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`guide-dot ${i === step ? "active" : ""}`}
              onClick={() => setStep(i)}
            />
          ))}
        </div>

        <div className="guide-actions">
          {!isFirst ? (
            <button
              className="guide-btn-secondary"
              onClick={() => setStep((s) => s - 1)}
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
              onClick={() => setStep((s) => s + 1)}
            >
              下一步
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
