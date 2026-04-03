"""数据库 CRUD 操作"""
import time

import aiosqlite


async def create_session(db: aiosqlite.Connection, session_id: str) -> None:
    """创建新会话记录"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
        (session_id, now, now),
    )
    await db.commit()


async def save_message(
    db: aiosqlite.Connection,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """保存对话消息"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    await db.commit()


async def save_artifact(
    db: aiosqlite.Connection,
    session_id: str,
    artifact_type: str,
    file_path: str,
) -> None:
    """保存输出物记录"""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    await db.execute(
        "INSERT INTO artifacts (session_id, artifact_type, file_path, created_at) VALUES (?, ?, ?, ?)",
        (session_id, artifact_type, file_path, now),
    )
    await db.commit()


async def get_session_messages(
    db: aiosqlite.Connection,
    session_id: str,
) -> list[dict]:
    """获取会话的所有消息"""
    async with db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]
