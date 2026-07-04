import { useMemo } from "react";
import { TurnDetail } from "../api";

interface Props {
  turns: TurnDetail[];
  currentTurnId: string | null;
  onSelect: (turnId: string) => void;
  onRetry: (turnId: string) => void;
}

interface FlatNode {
  turn: TurnDetail;
  depth: number;
  isLast: boolean;
}

function buildTree(turns: TurnDetail[]): FlatNode[] {
  const childrenOf = new Map<string, TurnDetail[]>();
  const roots: TurnDetail[] = [];

  for (const t of turns) {
    if (t.parent_turn_id && turns.some((x) => x.turn_id === t.parent_turn_id)) {
      const arr = childrenOf.get(t.parent_turn_id) ?? [];
      arr.push(t);
      childrenOf.set(t.parent_turn_id, arr);
    } else {
      roots.push(t);
    }
  }

  const sorter = (a: TurnDetail, b: TurnDetail) =>
    a.created_at.localeCompare(b.created_at);
  roots.sort(sorter);
  for (const [, children] of childrenOf) children.sort(sorter);

  const result: FlatNode[] = [];

  function walk(t: TurnDetail, depth: number, isLast: boolean) {
    result.push({ turn: t, depth, isLast });
    const children = childrenOf.get(t.turn_id) ?? [];
    for (let i = 0; i < children.length; i++) {
      walk(children[i], depth + 1, i === children.length - 1);
    }
  }

  for (let i = 0; i < roots.length; i++) {
    walk(roots[i], 0, i === roots.length - 1);
  }

  return result;
}

function BranchLines({ depth, isLast }: { depth: number; isLast: boolean }) {
  if (depth === 0) return null;
  return (
    <span className="tree-branch">
      {isLast ? "└ " : "├ "}
    </span>
  );
}

export default function TurnTimeline({ turns, currentTurnId, onSelect, onRetry }: Props) {
  const flatNodes = useMemo(() => buildTree(turns), [turns]);

  if (turns.length === 0) {
    return (
      <aside className="timeline">
        <h3>编辑历史</h3>
        <p className="timeline-empty">暂无编辑记录</p>
      </aside>
    );
  }

  return (
    <aside className="timeline">
      <h3>编辑历史</h3>
      <ul className="timeline-list">
        {flatNodes.map((node) => (
          <li
            key={node.turn.turn_id}
            className={`timeline-item depth-${node.depth} ${node.turn.turn_id === currentTurnId ? "active" : ""} ${node.turn.status === "failed" ? "failed" : ""}`}
            onClick={() => onSelect(node.turn.turn_id)}
            style={{ paddingLeft: `${12 + node.depth * 20}px` }}
          >
            <BranchLines depth={node.depth} isLast={node.isLast} />
            <div className="timeline-content">
              <p className="timeline-instruction">{node.turn.user_instruction}</p>
              <p className="timeline-intent">
                {node.turn.intent && <span className="badge">{node.turn.intent}</span>}
                {node.turn.selected_tool && <span className="badge tool">{node.turn.selected_tool}</span>}
              </p>
              {node.turn.output_image_url && (
                <img
                  className="timeline-thumb"
                  src={node.turn.output_image_url}
                  alt={node.turn.user_instruction}
                />
              )}
              {node.turn.error_message && (
                <p className="timeline-error">{node.turn.error_message}</p>
              )}
              {node.turn.status === "failed" && (
                <button
                  className="btn-retry"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRetry(node.turn.turn_id);
                  }}
                  title="用相同指令重试"
                >
                  ↻ 重试
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
