from painterAgent.tools import doubao_image  # noqa: F401 — triggers registry.register()

# 条件导入本地模型工具（依赖可选，缺失时跳过）
try:
    from painterAgent.tools import moebius_image  # noqa: F401
except ImportError:
    pass

try:
    from painterAgent.tools import lama_image  # noqa: F401
except ImportError:
    pass
