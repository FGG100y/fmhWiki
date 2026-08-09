"""示范注入与偏好记忆 — agentic 模式的"记忆分层"。

工作记忆（working memory）：会话内最近的示范记录（build_demonstration）
长期记忆（long-term memory）：跨会话聚合的偏好档案（build_preference_profile）

两者都是 turn 历史的只读投影，零新增存储，只作用于提示层。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from painterAgent.storage import store

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────────────────────────


@dataclass
class DemoSample:
    """示范记录中的单步"""
    step_index: int
    task_type: str  # generate / edit / inpaint
    tool: str       # 实际后端工具名
    prompt: str     # 生效的 rewritten_prompt
    has_mask: bool
    input_image_id: str
    output_image_id: str


@dataclass
class Demonstration:
    """示范记录：turn 历史的只读投影"""
    session_id: str
    steps: list[DemoSample] = field(default_factory=list)
    rendered: str = ""


@dataclass
class PreferenceProfile:
    """偏好档案：跨会话聚合的稳定倾向"""
    project_id: str
    tool_by_task: dict[str, str] = field(default_factory=dict)
    mask_usage_rate: float = 0.0
    prompt_language: str = ""
    prompt_len_avg: int = 0
    common_params: dict = field(default_factory=dict)


# ── 示范注入（工作记忆） ──────────────────────────────────────────────────────


def build_demonstration(
    session_id: str,
    before_turn_id: str,
    max_steps: int = 6,
) -> Demonstration | None:
    """把用户最近的确定性编辑操作投影为示范记录。

    Args:
        session_id: 会话 ID。
        before_turn_id: 当前 turn ID；示范取其之前的 turn。
        max_steps: 示范最多包含的步数（截取最近 N 步）。

    Returns:
        Demonstration 或 None（无符合条件的示范）。
    """
    try:
        session = store.get_session_with_turns(session_id)
    except Exception:
        logger.debug("build_demonstration: session not found")
        return None

    if session is None:
        return None

    turns = session.turns if hasattr(session, 'turns') else session.get("turns", [])
    if not turns:
        return None

    # 筛选：当前 turn 之前的、成功的确定性 turn
    eligible = []
    for t in turns:
        tid = t.get("turn_id") if isinstance(t, dict) else getattr(t, "turn_id", "")
        if tid == before_turn_id:
            break
        status = t.get("status") if isinstance(t, dict) else getattr(t, "status", "")
        output_id = t.get("output_image_id") if isinstance(t, dict) else getattr(t, "output_image_id", "")
        if status == "succeeded" and output_id:
            eligible.append(t)

    if not eligible:
        logger.debug("build_demonstration: no eligible turns before %s", before_turn_id)
        return None

    # 截取最后 max_steps 步
    recent = eligible[-max_steps:]
    steps = _turns_to_samples(recent)
    demo = Demonstration(session_id=session_id, steps=steps)
    demo.rendered = render_demo_prompt(demo)
    logger.info(
        "build_demonstration: session=%s steps=%d rendered_len=%d",
        session_id, len(steps), len(demo.rendered),
    )
    return demo


def _turns_to_samples(turns: list) -> list[DemoSample]:
    """将 turn 列表转换为 DemoSample 列表"""
    samples = []
    for i, t in enumerate(turns, 1):
        if isinstance(t, dict):
            selected_tool = t.get("selected_tool", "")
            # 从 selected_tool 推断 task_type
            task_type = ""
            if selected_tool:
                if "generate" in selected_tool:
                    task_type = "generate"
                elif "inpaint" in selected_tool:
                    task_type = "inpaint"
                elif "edit" in selected_tool:
                    task_type = "edit"
            samples.append(DemoSample(
                step_index=i,
                task_type=task_type,
                tool=selected_tool,
                prompt=t.get("rewritten_prompt") or t.get("user_instruction", ""),
                has_mask=bool(t.get("mask_image_id")),
                input_image_id=t.get("input_image_id") or "",
                output_image_id=t.get("output_image_id") or "",
            ))
        else:
            selected_tool = getattr(t, "selected_tool", "")
            task_type = ""
            if selected_tool:
                if "generate" in selected_tool:
                    task_type = "generate"
                elif "inpaint" in selected_tool:
                    task_type = "inpaint"
                elif "edit" in selected_tool:
                    task_type = "edit"
            samples.append(DemoSample(
                step_index=i,
                task_type=task_type,
                tool=selected_tool,
                prompt=getattr(t, "rewritten_prompt", "") or getattr(t, "user_instruction", ""),
                has_mask=bool(getattr(t, "mask_image_id", None)),
                input_image_id=getattr(t, "input_image_id", "") or "",
                output_image_id=getattr(t, "output_image_id", "") or "",
            ))
    return samples


def render_demo_prompt(demo: Demonstration) -> str:
    """把示范记录渲染为注入文本块（few-shot 方法参考）。"""
    if not demo.steps:
        return ""

    lines = [
        "",
        "## 用户示范方法（最近编辑操作记录）",
        "以下是用户最近在确定性模式下的编辑操作，请模仿其工具选择、prompt 措辞与操作顺序，",
        "但针对当前指令重新规划，**不得复用示范中的图片**、不得照搬示范步骤。",
        "",
    ]
    for s in demo.steps:
        mask_flag = "有mask" if s.has_mask else "无mask"
        prompt_summary = s.prompt[:80] + ("..." if len(s.prompt) > 80 else "")
        lines.append(
            f"步骤{s.step_index}: 任务类型={s.task_type} | 工具={s.tool} | "
            f"{mask_flag} | prompt=\"{prompt_summary}\" | 输出图id={s.output_image_id}"
        )

    return "\n".join(lines)


# ── 偏好记忆（长期记忆） ──────────────────────────────────────────────────────


def build_preference_profile(
    project_id: str,
    min_turns: int = 3,
) -> PreferenceProfile | None:
    """把项目内用户主动的确定性 turn 聚合为偏好档案。

    Args:
        project_id: 项目 ID，聚合范围。
        min_turns: 有效样本下限；不足返回 None（不注入）。

    Returns:
        PreferenceProfile 或 None。
    """
    # 获取项目下所有会话的 turns
    sessions = store.list_sessions_by_project(project_id)
    if not sessions:
        logger.debug("build_preference_profile: no sessions in project %s", project_id)
        return None

    all_turns = []
    for s in sessions:
        sid = s.get("session_id") if isinstance(s, dict) else getattr(s, "session_id", "")
        try:
            session = store.get_session_with_turns(sid)
        except Exception:
            continue
        if session is None:
            continue
        turns = session.turns if hasattr(session, 'turns') else session.get("turns", [])
        for t in turns:
            status = t.get("status") if isinstance(t, dict) else getattr(t, "status", "")
            exec_mode = t.get("execution_mode") if isinstance(t, dict) else getattr(t, "execution_mode", "")
            # 只统计成功的、确定性模式的 turn（排除 agentic 及其降级）
            if status == "succeeded" and exec_mode in ("deterministic", ""):
                all_turns.append(t)

    if len(all_turns) < min_turns:
        logger.debug(
            "build_preference_profile: %d eligible turns < min=%d",
            len(all_turns), min_turns,
        )
        return None

    profile = _aggregate_turns(project_id, all_turns)
    logger.info(
        "build_preference_profile: project=%s turns=%d mask_rate=%.1f%% lang=%s",
        project_id, len(all_turns), profile.mask_usage_rate * 100, profile.prompt_language,
    )
    return profile


def _aggregate_turns(project_id: str, turns: list) -> PreferenceProfile:
    """统计聚合"""
    profile = PreferenceProfile(project_id=project_id)

    tool_counts: dict[str, dict[str, int]] = {}  # task_type → tool → count
    mask_count = 0
    total_prompt_len = 0
    chinese_count = 0
    prompt_count = 0

    for t in turns:
        if isinstance(t, dict):
            selected_tool = t.get("selected_tool", "")
            task_type = ""
            if selected_tool:
                if "generate" in selected_tool:
                    task_type = "generate"
                elif "inpaint" in selected_tool:
                    task_type = "inpaint"
                elif "edit" in selected_tool:
                    task_type = "edit"
            if task_type and selected_tool:
                tool_counts.setdefault(task_type, {})
                tool_counts[task_type][selected_tool] = tool_counts[task_type].get(selected_tool, 0) + 1
            if t.get("mask_image_id"):
                mask_count += 1
            instruction = t.get("user_instruction", "")
            total_prompt_len += len(instruction)
            prompt_count += 1
            # 简单中文检测
            if any('一' <= c <= '鿿' for c in instruction):
                chinese_count += 1
        else:
            selected_tool = getattr(t, "selected_tool", "")
            task_type = ""
            if selected_tool:
                if "generate" in selected_tool:
                    task_type = "generate"
                elif "inpaint" in selected_tool:
                    task_type = "inpaint"
                elif "edit" in selected_tool:
                    task_type = "edit"
            if task_type and selected_tool:
                tool_counts.setdefault(task_type, {})
                tool_counts[task_type][selected_tool] = tool_counts[task_type].get(selected_tool, 0) + 1
            if getattr(t, "mask_image_id", None):
                mask_count += 1
            instruction = getattr(t, "user_instruction", "")
            total_prompt_len += len(instruction)
            prompt_count += 1
            if any('一' <= c <= '鿿' for c in instruction):
                chinese_count += 1

    # 每个 task_type 选最常用工具
    for task_type, counts in tool_counts.items():
        profile.tool_by_task[task_type] = max(counts, key=counts.get)  # type: ignore[arg-type]

    total = len(turns)
    profile.mask_usage_rate = mask_count / total if total > 0 else 0.0
    profile.prompt_language = "中文" if (chinese_count / prompt_count > 0.5 if prompt_count else False) else "英文"
    profile.prompt_len_avg = total_prompt_len // prompt_count if prompt_count > 0 else 0

    return profile


def render_preference_prompt(profile: PreferenceProfile) -> str:
    """把偏好档案渲染为注入文本块（全局风格约束）。"""
    lines = [
        "",
        "## 用户长期偏好（跨会话稳定倾向）",
        "以下偏好统计自该用户的历史操作，请将其视为**一贯风格约束**：",
        "",
    ]

    if profile.tool_by_task:
        tools_desc = ", ".join(f"{t}:{tool}" for t, tool in profile.tool_by_task.items())
        lines.append(f"- 惯用工具: {tools_desc}")

    if profile.mask_usage_rate > 0:
        pct = int(profile.mask_usage_rate * 100)
        label = "频繁使用 mask 做局部重绘" if pct > 50 else "偶尔使用 mask"
        lines.append(f"- mask 使用: {pct}% 的 turn 使用 mask（{label}）")

    if profile.prompt_language:
        lines.append(f"- prompt 语言: 倾向{profile.prompt_language}")

    if profile.prompt_len_avg > 0:
        lines.append(f"- prompt 平均长度: {profile.prompt_len_avg} 字符")

    if len(lines) <= 5:
        return ""  # 无有意义信息

    return "\n".join(lines)
