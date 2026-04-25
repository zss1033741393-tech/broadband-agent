"""GET/PUT /api/engine — 引擎切换配置。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.engine_config import get_config, set_config
from api.models import ok

router = APIRouter(prefix="/engine", tags=["engine"])


@router.get("")
async def get_engine() -> dict[str, Any]:
    """获取当前引擎配置。"""
    return ok(get_config())


@router.put("")
async def set_engine(body: dict[str, Any]) -> dict[str, Any]:
    """更新引擎配置（合并式）。"""
    cfg = set_config(body)
    return ok(cfg)


@router.get("/health")
async def engine_health() -> dict[str, Any]:
    """检查当前引擎的健康状态。"""
    cfg = get_config()
    if cfg["engine"] == "opencode":
        from api.opencode_bridge import OpenCodeClient

        oc = OpenCodeClient(cfg["opencode_url"])
        healthy = await oc.health()
        return ok(
            {
                "engine": "opencode",
                "healthy": healthy,
                "url": cfg["opencode_url"],
            }
        )
    return ok({"engine": "agno", "healthy": True})
