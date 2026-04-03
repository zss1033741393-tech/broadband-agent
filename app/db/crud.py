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
