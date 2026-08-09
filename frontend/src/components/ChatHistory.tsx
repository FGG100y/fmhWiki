import { useMemo, useRef, useEffect } from "react";
import { TurnDetail } from "../api";

interface Props {
  turns: TurnDetail[];
  currentTurnId: string | null;
  loading: boolean;
  onSelect: (turnId: string) => void;
  onRetry: (turnId: string) => void;
  onDelete: (turnId: string) => void;
}

function findParent(
  turn: TurnDetail,
  turns: TurnDetail[]
): TurnDetail | undefined {
  if (!turn.parent_turn_id) return undefined;
  return turns.find((t) => t.turn_id === turn.parent_turn_id);
}

export default function ChatHistory({
  turns,
  currentTurnId,
  loading,
  onSelect,
  onRetry,
  onDelete,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(
    () => [...turns].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [turns]
  );

  // Auto-scroll to bottom when new turns arrive or loading changes
  useEffect(() => {
    const el = listRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [turns.length, loading]);

  if (turns.length === 0) {
    return (
      <div className="chat-panel-inner">
        <div className="chat-header">
          <h3>对话记录</h3>
        </div>
        <div className="chat-list" ref={listRef}>
          <div className="chat-empty">
            {loading ? "生成中…" : "暂无对话，输入指令开始"}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-panel-inner">
      <div className="chat-header">
        <h3>对话记录</h3>
        <span className="chat-count">{turns.length} 轮</span>
      </div>
      <div className="chat-list" ref={listRef}>
        {sorted.map((turn, idx) => {
          const parent = findParent(turn, turns);
          const prevTurn = idx > 0 ? sorted[idx - 1] : null;
          const isBranch =
            turn.parent_turn_id &&
            prevTurn &&
            prevTurn.turn_id !== turn.parent_turn_id;

          return (
            <div key={turn.turn_id}>
              {isBranch && parent && (
                <div className="chat-branch-note">
                  — 分支自「{parent.user_instruction}」
                </div>
              )}
              <div
                className={`chat-entry ${turn.turn_id === currentTurnId ? "active" : ""} ${turn.status === "failed" ? "failed" : ""}`}
                onClick={() => onSelect(turn.turn_id)}
              >
                {/* User bubble */}
                <div className="chat-user-bubble">
                  {turn.user_instruction}
                </div>

                {/* AI reply bubble */}
                <div className="chat-ai-bubble">
                  {turn.output_image_url ? (
                    <img
                      className="chat-thumb"
                      src={turn.output_image_url}
                      alt={turn.user_instruction}
                    />
                  ) : turn.status === "failed" ? (
                    <div className="chat-ai-error">
                      {turn.error_message || "生成失败"}
                    </div>
                  ) : (
                    <div style={{ color: "var(--text-muted)" }}>
                      {loading ? "生成中…" : "等待生成"}
                    </div>
                  )}

                  {(turn.intent || turn.selected_tool) && (
                    <div className="chat-intent">
                      {turn.intent && (
                        <span className="badge">{turn.intent}</span>
                      )}
                      {turn.selected_tool && (
                        <span className="badge tool">
                          {turn.selected_tool}
                        </span>
                      )}
                    </div>
                  )}

                  <div className="chat-actions">
                    {turn.status === "failed" && (
                      <button
                        className="btn-retry"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRetry(turn.turn_id);
                        }}
                      >
                        ↻ 重试
                      </button>
                    )}
                    <button
                      className="btn-delete-turn chat-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm("确定删除这条记录？")) {
                          onDelete(turn.turn_id);
                        }
                      }}
                      title="删除此记录"
                    >
                      ×
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="chat-typing">生成中…</div>
        )}
      </div>
    </div>
  );
}
