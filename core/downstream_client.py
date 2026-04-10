"""下游系统客户端 — mock + real 双实现。

通过 configs/downstream.yaml 的 mode 字段切换。
"""

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "downstream.yaml"


def _load_config() -> Dict[str, Any]:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---- Mock 响应 ----

_MOCK_RESPONSES: Dict[str, list] = {
    "dispatch_cei": [
        {"status": "success", "message": "CEI Spark 配置下发成功", "config_id": "CEI-20260407-001"},
        {"status": "partial_success", "message": "CEI 配置下发部分成功，2/3 节点已生效", "config_id": "CEI-20260407-002"},
        {"status": "failed", "message": "CEI 配置下发失败：目标 OLT 不可达", "error_code": "E1001"},
    ],
    "dispatch_fault": [
        {"status": "success", "message": "故障配置 API 下发成功", "task_id": "FAULT-20260407-001"},
        {"status": "failed", "message": "故障配置下发失败：参数校验不通过", "error_code": "E2001"},
    ],
    "dispatch_loop": [
        {"status": "success", "message": "远程闭环配置下发成功", "loop_id": "LOOP-20260407-001"},
        {"status": "failed", "message": "远程闭环下发失败：目标设备离线", "error_code": "E3001"},
    ],
    "dispatch_wifi": [
        {"status": "success", "message": "Wifi 仿真配置下发成功", "sim_id": "WIFI-20260407-001"},
        {"status": "partial_success", "message": "Wifi 仿真部分完成", "sim_id": "WIFI-20260407-002"},
    ],
    "constraint_check": [
        {"passed": True, "message": "所有约束校验通过", "warnings": []},
        {"passed": True, "message": "约束校验通过，但有警告", "warnings": ["时段与现有策略有重叠，请确认优先级"]},
        {"passed": False, "message": "约束校验不通过", "errors": ["CEI 配置与现有网络拓扑冲突", "保障时段超出 SLA 范围"]},
    ],
    "data_query": [
        {
            "status": "success",
            "data": [
                {"pon_port": "PON-1/0/1", "cei_score": 62.5, "user_count": 48, "bandwidth_util": 0.87},
                {"pon_port": "PON-1/0/3", "cei_score": 55.2, "user_count": 52, "bandwidth_util": 0.93},
                {"pon_port": "PON-2/0/2", "cei_score": 71.8, "user_count": 35, "bandwidth_util": 0.72},
                {"pon_port": "PON-2/0/5", "cei_score": 48.9, "user_count": 60, "bandwidth_util": 0.95},
                {"pon_port": "PON-3/0/1", "cei_score": 82.1, "user_count": 28, "bandwidth_util": 0.55},
            ],
            "query_time_ms": 230,
        },
    ],
}


def _mock_dispatch(endpoint: str, payload: Any = None) -> Dict[str, Any]:
    """Mock 模式：随机返回预设响应之一。"""
    responses = _MOCK_RESPONSES.get(endpoint, [{"status": "success", "message": "mock ok"}])
    resp = random.choice(responses)
    logger.debug(f"[mock] {endpoint} → {resp.get('status', 'ok')}")
    return resp


async def dispatch(endpoint: str, payload: Any = None) -> Dict[str, Any]:
    """统一下游调用接口。

    Args:
        endpoint: 端点名称 (dispatch_cei / dispatch_fault / ...)
        payload: 请求体

    Returns:
        响应字典
    """
    cfg = _load_config()
    mode = cfg.get("mode", "mock")

    if mode == "mock":
        return _mock_dispatch(endpoint, payload)

    # real 模式
    endpoint_cfg = cfg.get("endpoints", {}).get(endpoint, {})
    url = endpoint_cfg.get("url", "")
    timeout = endpoint_cfg.get("timeout", 10)

    if not url:
        return {"status": "error", "message": f"未配置端点 {endpoint}"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload or {})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception(f"下游调用失败: {endpoint}")
        return {"status": "error", "message": str(e)}
