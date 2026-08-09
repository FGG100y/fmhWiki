import { useMemo, useState, useCallback, useEffect } from "react";
import { TurnDetail } from "../api";

interface Props {
  turns: TurnDetail[];
  currentTurnId: string | null;
  onSelect: (turnId: string) => void;
  onRetry: (turnId: string) => void;
  onDelete: (turnId: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

interface FlatNode {
  turn: TurnDetail;
  depth: number;
  isLast: boolean;
  rootId: string;
}

function buildTree(turns: TurnDetail[]): { nodes: FlatNode[]; rootIds: string[] } {
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

  const nodes: FlatNode[] = [];
  const rootIds: string[] = [];

  function walk(t: TurnDetail, depth: number, isLast: boolean, rootId: string) {
    nodes.push({ turn: t, depth, isLast, rootId });
    const children = childrenOf.get(t.turn_id) ?? [];
    for (let i = 0; i < children.length; i++) {
      walk(children[i], depth + 1, i === children.length - 1, rootId);
    }
  }

  for (let i = 0; i < roots.length; i++) {
    rootIds.push(roots[i].turn_id);
    walk(roots[i], 0, i === roots.length - 1, roots[i].turn_id);
  }

  return { nodes, rootIds };
}

function BranchLines({ depth, isLast }: { depth: number; isLast: boolean }) {
  if (depth === 0) return null;
  return (
    <span className="tree-branch">
      {isLast ? "└ " : "├ "}
    </span>
  );
}

export default function TurnTimeline({ turns, currentTurnId, onSelect, onRetry, onDelete, collapsed, onToggleCollapse }: Props) {
  const { nodes: flatNodes, rootIds } = useMemo(() => buildTree(turns), [turns]);

  const [collapsedRoots, setCollapsedRoots] = useState<Set<string>>(() => {
    // 默认只展开最后一个根（最新原图），其余折叠
    if (rootIds.length > 1) {
      return new Set(rootIds.slice(0, -1));
    }
    return new Set();
  });

  // 当 rootIds 变化时（上传新图片），自动折叠之前的根
  useEffect(() => {
    if (rootIds.length > 1) {
      setCollapsedRoots(new Set(rootIds.slice(0, -1)));
    }
  }, [rootIds]);

  const toggleCollapse = useCallback((rootId: string) => {
    setCollapsedRoots((prev) => {
      const next = new Set(prev);
      if (next.has(rootId)) {
        next.delete(rootId);
      } else {
        next.add(rootId);
      }
      return next;
    });
  }, []);

  const visibleNodes = useMemo(
    () => flatNodes.filter((n) => !collapsedRoots.has(n.rootId) || n.turn.turn_id === n.rootId),
    [flatNodes, collapsedRoots]
  );

  if (collapsed) {
    return (
      <aside className="timeline timeline-collapsed">
        <button
          className="timeline-expand-btn"
          onClick={onToggleCollapse}
          title="展开时间线"
        >
          ☰
        </button>
      </aside>
    );
  }

  if (turns.length === 0) {
    return (
      <aside className="timeline">
        <div className="timeline-header">
          <h3>编辑历史</h3>
          <button
            className="timeline-collapse-btn"
            onClick={onToggleCollapse}
            title="折叠时间线"
          >
            ✕
          </button>
        </div>
        <p className="timeline-empty">暂无编辑记录</p>
      </aside>
    );
  }

  return (
    <aside className="timeline">
      <div className="timeline-header">
        <h3>编辑历史</h3>
        <button
          className="timeline-collapse-btn"
          onClick={onToggleCollapse}
          title="折叠时间线"
        >
          ✕
        </button>
      </div>
      <ul className="timeline-list">
        {visibleNodes.map((node) => {
          const isRoot = node.turn.turn_id === node.rootId;
          const collapsed = collapsedRoots.has(node.rootId);
          return (
            <li
              key={node.turn.turn_id}
              className={`timeline-item depth-${node.depth} ${node.turn.turn_id === currentTurnId ? "active" : ""} ${node.turn.status === "failed" ? "failed" : ""}`}
              onClick={() => onSelect(node.turn.turn_id)}
              style={{ paddingLeft: `${12 + node.depth * 20}px` }}
            >
              {isRoot && (
                <button
                  className="btn-collapse"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleCollapse(node.rootId);
                  }}
                  title={collapsed ? "展开" : "折叠"}
                >
                  {collapsed ? "▶" : "▼"}
                </button>
              )}
              {!isRoot && <BranchLines depth={node.depth} isLast={node.isLast} />}
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
                <button
                  className="btn-delete-turn"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("确定删除这条记录？")) {
                      onDelete(node.turn.turn_id);
                    }
                  }}
                  title="删除此记录"
                >
                  ×
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
