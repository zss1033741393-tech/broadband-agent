import os
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# 数据库路径从环境变量读取，默认 ./data/agent.db
DB_PATH = os.getenv("SQLITE_DB_PATH", "./data/agent.db")

# 建表 SQL
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS intent_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    intent_goal_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS plan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    plan_result_json TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS pipeline_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    output_json TEXT NOT NULL,
    output_files TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    app_history_json TEXT,
    network_kpi_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,            -- Stage1 / Stage2 / Stage3 / Stage4
    event_type TEXT NOT NULL,       -- stage_start / stage_end / followup / error
    component TEXT NOT NULL,        -- IntentParser / PlanFiller / ConstraintChecker / ConfigTranslator
    input_data TEXT,                -- 输入内容（JSON 字符串）
    output_data TEXT,               -- 输出内容（JSON 字符串）
    latency_ms REAL,                -- 耗时（毫秒）
    extra TEXT,                     -- 附加信息（JSON 字符串）
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS llm_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    stage TEXT NOT NULL,            -- Stage1 / Stage2 / Stage3 / Stage4
    component TEXT NOT NULL,        -- IntentParser / PlanFiller 等
    -- 请求参数
    model TEXT NOT NULL,
    temperature REAL,
    max_tokens INTEGER,
    is_stream INTEGER DEFAULT 0,    -- 是否流式（0/1）
    -- 请求消息（完整 messages 数组，含 system/user/assistant/tool）
    request_messages TEXT,          -- JSON array: [{role, content}]
    -- 响应
    response_content TEXT,          -- 最终回复文本
    reasoning_content TEXT,         -- 推理过程（CoT/thinking，如 o1/deepseek-r1）
    -- Tool 调用
    tool_calls TEXT,                -- JSON array: [{id, name, arguments}]
    tool_results TEXT,              -- JSON array: [{tool_call_id, name, content}]
    -- Token 用量
    tokens_in INTEGER,              -- 输入 token 数（prompt tokens）
    tokens_out INTEGER,             -- 输出 token 数（completion tokens）
    tokens_reasoning INTEGER,       -- 推理 token 数（部分模型支持）
    -- 耗时
    latency_ms REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


async def init_db() -> None:
    """初始化数据库，创建所有表"""
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """获取数据库连接的异步上下文管理器"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
