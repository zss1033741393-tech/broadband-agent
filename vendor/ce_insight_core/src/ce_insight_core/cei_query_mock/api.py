"""
外网 Mock 接口，模拟内网 cei_query 包的查询行为。
内网部署时将 import 路径从 cei_query_mock 换为 cei_query 即可。
支持天表和分钟表两种数据模式。
"""

import pandas as pd
import numpy as np


def query_subject_from_single_table(
    path: str,
    subspace,
    use_pandas: bool = True,
) -> list[pd.DataFrame]:
    """
    Mock 版三元组查询，返回结构与真实接口一致的假数据。
    自动判断 measures 中的字段是天表还是分钟表字段，返回对应格式的数据。
    """
    if hasattr(subspace, "model_dump"):
        config = subspace.model_dump()
    elif hasattr(subspace, "dict"):
        config = subspace.dict()
    elif isinstance(subspace, dict):
        config = subspace
    else:
        config = {}

    breakdown = config.get("breakdown", {})
    measures = config.get("measures", [])
    dimensions = config.get("dimensions", [[]])

    breakdown_name = breakdown.get("name", "portUuid")
    breakdown_type = breakdown.get("type", "UNORDERED")

    filter_values = _extract_filter_values(dimensions)

    # 判断是否为分钟表查询
    measure_names = {m.get("name", "") for m in measures}
    is_minute = bool(measure_names & MINUTE_TABLE_FIELDS)

    if is_minute:
        df = _generate_minute_data(breakdown_name, breakdown_type, measures, filter_values)
    elif breakdown_type == "ORDERED":
        df = _generate_time_series(breakdown_name, measures, filter_values)
    else:
        df = _generate_grouped_data(breakdown_name, measures, filter_values)

    return [df]


# ==================== 分钟表字段集合 ====================

def _build_minute_fields():
    """从 minute_schema_manager 动态获取所有分钟表字段"""
    try:
        from ce_insight_core.services.minute_schema_manager import get_all_minute_fields
        return get_all_minute_fields()
    except ImportError:
        return set()

MINUTE_TABLE_FIELDS = _build_minute_fields()

# 分钟表字段的值生成规则
MINUTE_FIELD_GENERATORS = {
    # 越限标记字段：大部分为 0，少量为 1
    "flag": [
        "oltRxPowerHigh", "oltRxWeakLight", "bipHigh", "fecHigh",
        "G10UpPlrHigh", "G1UpPlrHigh", "portUpPlrHigh",
        "homeRamHigh", "homeCpuMaxHigh", "diagLossHigh",
        "apRamHigh", "apCpuMaxHigh", "peakRxRateHigh",
        "roamDelayHigh", "diagTimeDelayHigh",
    ],
    # 计数字段：大部分为 0，偶尔有值
    "sparse_count": [
        "unclearedAlarmCount_A", "alarmCount", "unclearedAlarmCount_H",
        "zeroNegotiationRxRateCnt", "zeroAchievableRateCnt",
        "officePoorQualityCount", "gamePoorQualityCount",
        "videoCallPoorQualityCount", "liveVideoPoorQualityCount",
        "educationPoorQualityCount", "anchorVideoPoorQualityCount",
        "pointVideoPoorQualityCount", "generalTcpPoorQualityCount",
        "apExceHighCnt", "apWifiHighCnt", "apLanHighCnt", "apPonHighCnt",
        "apLanCnt", "apWifiCnt", "apPonCnt",
    ],
    # 误码/错误数：较小的正整数
    "error_count": [
        "ontDownstreamBipErrors", "ontRxFecErrors",
    ],
    # 丢包率：0~0.01 范围
    "packet_loss": [
        "G10UpPlr", "G1UpPlr", "portUpPlr",
    ],
    # 数据包计数：大正整数
    "packet_count": [
        "G10TxPacketCount", "G1TxPacketCount", "portTxPacketCount",
    ],
    # 流量/速率：正值
    "traffic": [
        "maxTxTraffic", "meanRxTraffic", "peakRxRate",
        "avgAchievableRate", "avgNegotiationTxRate", "avgNegotiationRxRate",
    ],
    # 光功率 dBm：负值
    "power_dbm": [
        "RxPower", "avgWifiSignal",
    ],
    # 利用率百分比 0~100
    "utilization": [
        "homeRamMax", "homeCpuMax", "apRamMax", "apCpuMax",
    ],
    # 占比 0~1
    "ratio": [
        "zeroNegotiationTxRatePercent", "zeroAchievableRatePercent",
        "dBmPercent", "avgDownLossRate",
    ],
    # 丢包率百分比 0~100
    "loss_percent": [
        "maxDiagLossRate", "avgDiagLossRate",
    ],
    # 时延 ms
    "latency_ms": [
        "maxDiagMaxTime", "avgDiagAvgTime", "minDiagMinTime",
    ],
    # 干扰采集点数
    "interference_count": [
        "midCnt", "highCnt", "lowCnt", "sumTotal",
    ],
    # 噪声/信噪比 dB
    "noise_snr": [
        "avgNoise", "avgSnr",
    ],
    # 终端/设备数量
    "sta_count": [
        "numSTA", "totalDevices", "numLanWiredDevices",
    ],
    # 告警类型列表（字符串）
    "alarm_list": [
        "alarmType_list",
    ],
}

# 反转映射：字段名 → 生成类型
_FIELD_TO_TYPE = {}
for gen_type, fields in MINUTE_FIELD_GENERATORS.items():
    for f in fields:
        _FIELD_TO_TYPE[f] = gen_type


def _generate_minute_data(
    breakdown_name: str,
    breakdown_type: str,
    measures: list[dict],
    filter_values: dict[str, list],
) -> pd.DataFrame:
    """生成分钟表 Mock 数据"""
    n = 120  # 分钟表数据量较大
    rng = np.random.default_rng(42)

    data: dict = {}

    # breakdown 列
    if breakdown_name == "time_id" or breakdown_type == "ORDERED":
        data["time_id"] = pd.date_range("2025-01-15 08:00", periods=n, freq="5min")
    elif breakdown_name in filter_values:
        groups = filter_values[breakdown_name]
        n = len(groups) * 20  # 每组 20 条
        data[breakdown_name] = [g for g in groups for _ in range(20)]
        data["time_id"] = pd.date_range("2025-01-15 08:00", periods=20, freq="5min").tolist() * len(groups)
    else:
        groups = _default_groups(breakdown_name, min(n, 10))
        per_group = n // len(groups)
        data[breakdown_name] = [g for g in groups for _ in range(per_group)]
        data["time_id"] = pd.date_range("2025-01-15 08:00", periods=per_group, freq="5min").tolist() * len(groups)
        n = len(data[breakdown_name])

    # 如果有设备过滤
    if "portUuid" in filter_values and "portUuid" not in data:
        data["portUuid"] = [filter_values["portUuid"][0]] * n

    # 生成度量列
    for m in measures:
        name = m.get("name", "value")
        gen_type = _FIELD_TO_TYPE.get(name, "default")
        data[name] = _generate_minute_values(rng, n, gen_type)

    return pd.DataFrame(data)


def _generate_minute_values(rng: np.random.Generator, n: int, gen_type: str) -> np.ndarray:
    """根据字段类型生成合理的分钟级数值"""
    if gen_type == "flag":
        # 90% 为 0，10% 为 1
        return rng.choice([0, 1], size=n, p=[0.9, 0.1])
    elif gen_type == "sparse_count":
        # 85% 为 0，15% 为 1~5
        vals = np.zeros(n, dtype=int)
        mask = rng.random(n) > 0.85
        vals[mask] = rng.integers(1, 6, size=mask.sum())
        return vals
    elif gen_type == "error_count":
        return rng.integers(0, 50, size=n)
    elif gen_type == "packet_loss":
        # 大部分接近 0，少量高值
        vals = rng.exponential(0.001, n)
        return np.clip(vals, 0, 0.1).round(6)
    elif gen_type == "traffic":
        return np.clip(rng.normal(500, 200, n), 0, 2000).round(2)
    elif gen_type == "power_dbm":
        return rng.normal(-22, 3, n).round(2)
    elif gen_type == "utilization":
        return np.clip(rng.normal(40, 20, n), 0, 100).round(1)
    elif gen_type == "loss_percent":
        vals = rng.exponential(2, n)
        return np.clip(vals, 0, 100).round(2)
    elif gen_type == "latency_ms":
        return np.clip(rng.normal(30, 20, n), 0, 500).round(1)
    elif gen_type == "interference_count":
        return rng.integers(0, 100, size=n)
    elif gen_type == "noise_snr":
        return rng.normal(-85, 5, n).round(1)
    elif gen_type == "sta_count":
        return rng.integers(1, 20, size=n)
    elif gen_type == "packet_count":
        return rng.integers(10000, 1000000, size=n)
    elif gen_type == "ratio":
        # 占比 0~1，大部分接近 0
        vals = rng.exponential(0.05, n)
        return np.clip(vals, 0, 1).round(4)
    elif gen_type == "alarm_list":
        # 返回字符串列表模拟
        return ["" if rng.random() > 0.1 else "DGI,LOS" for _ in range(n)]
    else:
        # 默认：天表得分字段
        return np.clip(rng.normal(70, 15, n), 0, 100).round(2)


# ==================== 天表数据生成（原有逻辑） ====================

def _extract_filter_values(dimensions) -> dict[str, list]:
    """从 dimensions 中提取 IN 条件的过滤值。对 None / 非列表结构做兜底。"""
    filters = {}
    if not dimensions or not isinstance(dimensions, list):
        return filters
    # 兼容单层 dimensions（LLM 常见错误）
    if dimensions and not isinstance(dimensions[0], list):
        dimensions = [dimensions]
    for dim_group in dimensions:
        if not isinstance(dim_group, list):
            continue
        for dim_filter in dim_group:
            if not isinstance(dim_filter, dict):
                continue
            dim_info = dim_filter.get("dimension") or {}
            dim_name = dim_info.get("name", "") if isinstance(dim_info, dict) else ""
            conditions = dim_filter.get("conditions") or []
            if not isinstance(conditions, list):
                continue
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                if cond.get("oper") == "IN" and "values" in cond:
                    filters[dim_name] = cond["values"]
    return filters


def _generate_time_series(
    breakdown_name: str,
    measures: list[dict],
    filter_values: dict[str, list],
) -> pd.DataFrame:
    """生成天表时序类 Mock 数据（ORDERED breakdown）"""
    n = 30
    rng = np.random.default_rng(42)

    data: dict = {
        breakdown_name: pd.date_range("2025-01-01", periods=n, freq="D"),
    }

    if "portUuid" in filter_values:
        data["portUuid"] = [filter_values["portUuid"][0]] * n

    for m in measures:
        name = m.get("name", "value")
        base = _score_base(name)
        trend = np.linspace(0, -5, n)
        noise = rng.normal(0, 3, n)
        data[name] = np.clip(base + trend + noise, 0, 100).round(2)

    return pd.DataFrame(data)


def _generate_grouped_data(
    breakdown_name: str,
    measures: list[dict],
    filter_values: dict[str, list],
) -> pd.DataFrame:
    """生成天表分组类 Mock 数据（UNORDERED breakdown）"""
    rng = np.random.default_rng(42)

    if breakdown_name in filter_values:
        groups = filter_values[breakdown_name]
    else:
        n = 20
        groups = _default_groups(breakdown_name, n)

    n = len(groups)
    data: dict = {breakdown_name: groups}

    for m in measures:
        name = m.get("name", "value")
        base = _score_base(name)
        data[name] = np.clip(rng.normal(base, 10, n), 0, 100).round(2)

    data["date"] = pd.date_range("2025-01-01", periods=n, freq="D").tolist()
    return pd.DataFrame(data)


def _default_groups(breakdown_name: str, n: int) -> list[str]:
    prefixes = {
        "portUuid": "port",
        "deviceId": "device",
        "oltId": "olt",
        "gatewayMac": "mac",
    }
    prefix = prefixes.get(breakdown_name, breakdown_name)
    return [f"{prefix}_{i}" for i in range(n)]


def _score_base(measure_name: str) -> float:
    bases = {
        "CEI_score": 75.0,
        "Wifi_score": 65.0,
        "Stability_score": 80.0,
        "Gateway_score": 78.0,
        "ODN_score": 82.0,
        "Rate_score": 70.0,
        "Service_score": 85.0,
        "OLT_score": 77.0,
        "STA_score": 73.0,
    }
    return bases.get(measure_name, 70.0)
