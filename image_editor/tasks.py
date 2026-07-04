"""Dramatiq 配置 — 异步任务队列"""

from __future__ import annotations

import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker

# 配置 Redis broker
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_broker = RedisBroker(url=_redis_url)
dramatiq.set_broker(_broker)
