import json
from datetime import datetime, timezone
from typing import Optional

from app.db.database import get_db


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def save_session(session_id: str, user_id: str = "") -> None:
    """创建或更新会话记录"""
    now = _now()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO sessions (session_id, user_id, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at""",
            (session_id, user_id, now, now),
        )
        await db.commit()


async def get_session(session_id: str) -> Optional[dict]:
    """查询会话记录"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def save_intent_goal(session_id: str, intent_goal: dict) -> None:
    """保存意图解析结果"""
    async with get_db() as db:
        await db.execute(
            "INSERT INTO intent_goals (session_id, intent_goal_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(intent_goal, ensure_ascii=False), _now()),
        )
        await db.commit()


async def get_intent_goal(session_id: str) -> Optional[dict]:
    """获取最新的意图解析结果"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT intent_goal_json FROM intent_goals WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        return json.loads(row["intent_goal_json"]) if row else None


async def save_plan_result(session_id: str, plan_result: dict, retry_count: int = 0) -> None:
    """保存方案生成结果"""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO plan_results (session_id, plan_result_json, retry_count, created_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, json.dumps(plan_result, ensure_ascii=False), retry_count, _now()),
        )
        await db.commit()


async def get_plan_result(session_id: str) -> Optional[dict]:
    """获取最新的方案结果"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT plan_result_json FROM plan_results WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        return json.loads(row["plan_result_json"]) if row else None


async def save_pipeline_output(
    session_id: str, output: dict, output_files: list[str]
) -> None:
    """保存 Pipeline 最终输出"""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO pipeline_outputs (session_id, output_json, output_files, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                session_id,
                json.dumps(output, ensure_ascii=False),
                json.dumps(output_files),
                _now(),
            ),
        )
        await db.commit()


async def get_pipeline_output(session_id: str) -> Optional[dict]:
    """获取最新的 Pipeline 输出"""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT output_json FROM pipeline_outputs
               WHERE session_id=? ORDER BY id DESC LIMIT 1""",
            (session_id,),
        )
        row = await cursor.fetchone()
        return json.loads(row["output_json"]) if row else None


async def save_user_profile(
    user_id: str,
    profile: dict,
    app_history: Optional[dict] = None,
    network_kpi: Optional[dict] = None,
) -> None:
    """保存用户画像"""
    async with get_db() as db:
        await db.execute(
            """INSERT INTO user_profiles (user_id, profile_json, app_history_json, network_kpi_json, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 profile_json=excluded.profile_json,
                 app_history_json=excluded.app_history_json,
                 network_kpi_json=excluded.network_kpi_json,
                 updated_at=excluded.updated_at""",
            (
                user_id,
                json.dumps(profile, ensure_ascii=False),
                json.dumps(app_history, ensure_ascii=False) if app_history else None,
                json.dumps(network_kpi, ensure_ascii=False) if network_kpi else None,
                _now(),
            ),
        )
        await db.commit()


async def save_trace(
    session_id: str,
    stage: str,
    event_type: str,
    component: str,
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    model: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[float] = None,
    extra: Optional[dict] = None,
) -> None:
    """保存 Agent 运行轨迹记录

    Args:
        session_id: 会话 ID
        stage: Pipeline 阶段，如 "Stage1"、"Stage2"
        event_type: 事件类型，如 "llm_call"、"tool_call"、"stage_start"、"stage_end"
        component: 组件名，如 "IntentParser"
        input_data: 输入数据 dict
        output_data: 输出数据 dict
        model: LLM 模型名（llm_call 时填写）
        tokens_in: 输入 token 数
        tokens_out: 输出 token 数
        latency_ms: 耗时毫秒
        extra: 附加信息 dict
    """
    async with get_db() as db:
        await db.execute(
            """INSERT INTO agent_traces
               (session_id, stage, event_type, component,
                input_data, output_data, model, tokens_in, tokens_out,
                latency_ms, extra, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                stage,
                event_type,
                component,
                json.dumps(input_data, ensure_ascii=False) if input_data else None,
                json.dumps(output_data, ensure_ascii=False) if output_data else None,
                model,
                tokens_in,
                tokens_out,
                latency_ms,
                json.dumps(extra, ensure_ascii=False) if extra else None,
                _now(),
            ),
        )
        await db.commit()


async def get_traces(session_id: str) -> list[dict]:
    """查询会话的全部运行轨迹，按时间顺序排列

    Args:
        session_id: 会话 ID

    Returns:
        轨迹记录列表
    """
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, stage, event_type, component,
                      input_data, output_data, model,
                      tokens_in, tokens_out, latency_ms, extra, created_at
               FROM agent_traces
               WHERE session_id = ?
               ORDER BY id ASC""",
            (session_id,),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            # 反序列化 JSON 字段
            for field in ("input_data", "output_data", "extra"):
                if item[field]:
                    item[field] = json.loads(item[field])
            result.append(item)
        return result


async def get_user_profile(user_id: str) -> Optional[dict]:
    """查询用户历史画像"""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT profile_json, app_history_json, network_kpi_json FROM user_profiles WHERE user_id=?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "profile": json.loads(row["profile_json"]),
            "app_history": json.loads(row["app_history_json"]) if row["app_history_json"] else {},
            "network_kpi": json.loads(row["network_kpi_json"]) if row["network_kpi_json"] else {},
        }
