from __future__ import annotations

from typing import Any, Protocol

from painterAgent.models import EditRequest, EditResult, GenerateRequest, GenerateResult


class ImageTool(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...

    async def edit(self, request: EditRequest) -> EditResult: ...


class ModelRegistry:
    """统一模型注册表：按 route name 存储客户端实例，图片与文本能力共用。

    图片客户端实现 ImageTool，文本客户端实现 chat/chat_json/chat_stream（duck typing）。
    """

    def __init__(self) -> None:
        self._clients: dict[str, Any] = {}

    def register(self, name: str, client: Any) -> None:
        self._clients[name] = client

    def get(self, name: str) -> Any:
        client = self._clients.get(name)
        if client is None:
            msg = f"未知路由: {name}"
            raise ValueError(msg)
        return client

    def has(self, name: str) -> bool:
        return name in self._clients


registry = ModelRegistry()

# 向后兼容别名
ImageToolRegistry = ModelRegistry
