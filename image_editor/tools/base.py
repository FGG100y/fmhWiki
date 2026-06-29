from __future__ import annotations

from typing import Protocol

from image_editor.models import EditRequest, EditResult, GenerateRequest, GenerateResult


class ImageTool(Protocol):
    async def generate(self, request: GenerateRequest) -> GenerateResult: ...

    async def edit(self, request: EditRequest) -> EditResult: ...


class ImageToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ImageTool] = {}

    def register(self, name: str, tool: ImageTool) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> ImageTool:
        tool = self._tools.get(name)
        if tool is None:
            msg = f"未知工具: {name}"
            raise ValueError(msg)
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools


registry = ImageToolRegistry()
