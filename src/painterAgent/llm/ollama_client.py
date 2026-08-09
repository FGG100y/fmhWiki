"""ollama 本地模型 LLM 客户端

通过 ollama 的 OpenAI 兼容接口 (http://localhost:11434/v1) 调用本地模型。
chat_json 做健壮 JSON 解析：去除 markdown 围栏、抽取首个 {...}。
chat_tools 做原生 agentic 工具调用循环（绕过 aisuite OllamaProvider 的 tool_calls 缺失）。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from painterAgent.config import config
from painterAgent.models import ModelCallRecord
from painterAgent.storage import store
from painterAgent.tools.base import registry
from painterAgent.tools.router import Capability, ModelRoute, register_route

logger = logging.getLogger(__name__)


class OllamaLLM:
    """ollama OpenAI 兼容客户端。

    chat_json 做健壮 JSON 解析：先尝试直接解析，失败后去除 markdown
    围栏并抽取首个 JSON 对象；仍失败则抛错（被 fallback 循环吞掉）。
    """

    def __init__(self) -> None:
        cfg = config.ollama
        self.client = AsyncOpenAI(
            api_key="ollama",  # ollama 不需要 key，但 openai SDK 要求非空
            base_url=cfg.base_url,
            max_retries=2,
            timeout=60.0,
        )
        self.model = cfg.model
        self.provider = "ollama"

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        session_id: str | None = None,
        turn_id: str | None = None,
        purpose: str = "llm_reasoning",
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        start = time.monotonic()
        status = "succeeded"
        error_message = None
        input_tokens = None
        output_tokens = None
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            if getattr(resp, "usage", None):
                input_tokens = resp.usage.prompt_tokens
                output_tokens = resp.usage.completion_tokens
            return resp.choices[0].message.content or ""
        except Exception as exc:
            status = "failed"
            error_message = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            store.record_model_call(
                ModelCallRecord(
                    call_id=f"call_{uuid.uuid4().hex[:12]}",
                    session_id=session_id,
                    turn_id=turn_id,
                    provider=self.provider,
                    model_name=self.model,
                    endpoint="chat.completions",
                    purpose=purpose,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    created_at=datetime.utcnow().isoformat(),
                )
            )

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        session_id: str | None = None,
        turn_id: str | None = None,
        purpose: str = "llm_reasoning",
    ) -> dict[str, Any]:
        text = await self.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            session_id=session_id,
            turn_id=turn_id,
            purpose=purpose,
        )
        return self._parse_json(text)

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> AsyncIterator[str]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    # ── Agentic 工具调用循环 ────────────────────────────────────────────────────

    async def chat_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
        max_turns: int = 5,
        temperature: float = 0.1,
        model: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        purpose: str = "agentic_planner",
    ) -> Any:
        """原生 agentic 工具调用循环（绕过 aisuite OllamaProvider）。

        直接用 AsyncOpenAI 调 ollama /v1/chat/completions，发送 tools 参数，
        在本地执行工具循环直至模型返回文本或达到 max_turns。

        Args:
            system_prompt: 系统提示。
            messages: 用户消息列表（不含 system）。
            tools: 可调用工具列表（async 函数）。
            max_turns: 最大工具调用轮数。
            temperature: 采样温度。
            model: 模型名，默认用 self.model。
            session_id / turn_id: 用于 telemetry。
            purpose: 记录到 model_calls 的用途标签。

        Returns:
            兼容 aisuite 的响应对象，含 choices[0].message 和
            choices[0].intermediate_messages（供 _extract_agent_steps 消费）。
        """
        from aisuite.utils.tools import Tools as AisuiteTools

        resolved_model = model or self.model

        # 1) 生成 OpenAI 工具 schema（复用 aisuite 的 schema 推导能力）
        tools_wrapper = AisuiteTools(list(tools))
        tool_schemas = tools_wrapper.tools(format="openai")
        tool_map: dict[str, Any] = {t.__name__: t for t in tools}

        # 2) 构建完整消息列表
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # 3) 工具调用循环
        intermediate_messages: list[Any] = []
        final_message: Any = None

        for _turn in range(max_turns):
            request_kwargs: dict[str, Any] = {
                "model": resolved_model,
                "messages": full_messages,
                "tools": tool_schemas,
                "temperature": temperature,
            }
            # qwen3 禁用 thinking 以保证 tool_calls 稳定输出
            if not config.ollama.think:
                request_kwargs["extra_body"] = {"think": False}

            # ── 调用 ollama ──────────────────────────────────────────────────────
            start = time.monotonic()
            status = "succeeded"
            error_message = None
            input_tokens = None
            output_tokens = None
            try:
                resp = await self.client.chat.completions.create(**request_kwargs)
                if getattr(resp, "usage", None):
                    input_tokens = resp.usage.prompt_tokens
                    output_tokens = resp.usage.completion_tokens
            except Exception as exc:
                status = "failed"
                error_message = str(exc)
                raise
            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                store.record_model_call(
                    ModelCallRecord(
                        call_id=f"call_{uuid.uuid4().hex[:12]}",
                        session_id=session_id,
                        turn_id=turn_id,
                        provider=self.provider,
                        model_name=resolved_model,
                        endpoint="chat.completions",
                        purpose=purpose,
                        latency_ms=latency_ms,
                        status=status,
                        error_message=error_message,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        created_at=datetime.utcnow().isoformat(),
                    )
                )

            msg = resp.choices[0].message

            # 清理 qwen3 可能的 <think> 块
            content = getattr(msg, "content", "") or ""
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            raw_tool_calls = getattr(msg, "tool_calls", None) or []

            # 构建兼容的 assistant 消息对象
            tc_objects = []
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    tc_id = getattr(tc, "id", "")
                    func = getattr(tc, "function", None)
                    tc_objects.append(
                        SimpleNamespace(
                            id=tc_id,
                            type=getattr(tc, "type", "function"),
                            function=SimpleNamespace(
                                name=getattr(func, "name", "") if func else "",
                                arguments=getattr(func, "arguments", "{}") if func else "{}",
                            ),
                        )
                    )

            assistant_msg = SimpleNamespace(
                role="assistant",
                content=content,
                tool_calls=tc_objects if tc_objects else None,
            )
            intermediate_messages.append(assistant_msg)

            # 无 tool_calls → 模型给出最终文本，结束循环
            if not raw_tool_calls:
                final_message = assistant_msg
                break

            # ── 执行工具调用 ──────────────────────────────────────────────────────
            # 追加 assistant 消息（含 tool_calls）到对话
            tc_dicts = []
            for tc in raw_tool_calls:
                tc_id = getattr(tc, "id", "")
                func = getattr(tc, "function", None)
                tc_dicts.append({
                    "id": tc_id,
                    "type": getattr(tc, "type", "function"),
                    "function": {
                        "name": getattr(func, "name", "") if func else "",
                        "arguments": getattr(func, "arguments", "{}") if func else "{}",
                    },
                })
            full_messages.append({
                "role": "assistant",
                "content": content if content else None,
                "tool_calls": tc_dicts,
            })

            for tc in raw_tool_calls:
                tc_id = getattr(tc, "id", "")
                func = getattr(tc, "function", None)
                tool_name = getattr(func, "name", "") if func else ""
                args_str = getattr(func, "arguments", "{}") if func else "{}"

                # 解析参数
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}

                # 执行工具
                tool_fn = tool_map.get(tool_name)
                if tool_fn is None:
                    result = {"error": f"unknown tool: {tool_name}"}
                else:
                    try:
                        result = await tool_fn(**args)
                    except Exception as exc:
                        result = {"error": f"{type(exc).__name__}: {exc}"}

                # 序列化结果
                result_str = json.dumps(result, ensure_ascii=False, default=str)

                # 追加 tool 消息到对话
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result_str,
                })

                # 记录到 intermediate_messages
                intermediate_messages.append(
                    SimpleNamespace(
                        role="tool",
                        name=tool_name,
                        tool_call_id=tc_id,
                        content=result_str,
                    )
                )

            final_message = assistant_msg  # 最后一条 assistant 消息

        # 4) 构建 aisuite 兼容的返回对象
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=final_message,
                    intermediate_messages=intermediate_messages,
                )
            ]
        )

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """健壮 JSON 解析：直接解析 → 去 markdown 围栏 → 抽取首个 {...}"""
        # 1) 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2) 去除 markdown 代码围栏 (```json ... ```)
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", text)
        cleaned = cleaned.replace("```", "")
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            pass

        # 3) 抽取首个 {...} 或 [...] 对象
        for pattern in [r"\{.*\}", r"\[.*\]"]:
            m = re.search(pattern, cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"OllamaLLM: 无法解析 JSON 输出: {text[:200]}")


# ── 注册 ──────────────────────────────────────────────────────────────────────

_ollama_llm = OllamaLLM()
registry.register("ollama_qwen3", _ollama_llm)

register_route(
    ModelRoute(
        name="ollama_qwen3",
        provider="ollama",
        capabilities=frozenset({Capability.prompt_enhance}),
        is_local=True,
        priority=0,  # 由 select() 中的 TEXT_LLM_ORDER 折算覆盖
    )
)
