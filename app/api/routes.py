"""FastAPI 路由定义"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.agent import BroadbandAgent
from app.agent.tracer import AgentTracer

router = APIRouter()

# Agent 单例（生产环境应通过依赖注入管理）
_agent: BroadbandAgent | None = None
_sessions: dict[str, AgentTracer] = {}


def get_agent() -> BroadbandAgent:
    global _agent
    if _agent is None:
        _agent = BroadbandAgent()
    return _agent


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    history: list[dict[str, str]] = []


class ChatResponse(BaseModel):
    session_id: str
    content: str
    thinking: str
    skill_used: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """处理对话请求"""
    agent = get_agent()

    # 获取或创建 tracer
    if req.session_id and req.session_id in _sessions:
        tracer = _sessions[req.session_id]
    else:
        tracer = AgentTracer()
        _sessions[tracer.session_id] = tracer

    result = await agent.run(req.message, req.history, tracer)
    return ChatResponse(
        session_id=tracer.session_id,
        content=result["content"],
        thinking=result["thinking"],
        skill_used=result["skill_used"],
    )


@router.get("/sessions/{session_id}/trace")
async def get_trace(session_id: str) -> dict:
    """获取会话轨迹摘要"""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    tracer = _sessions[session_id]
    return {
        "session_id": session_id,
        "steps": tracer.step,
        "skills_used": list(tracer.skills_used),
        "elapsed": tracer.elapsed(),
        "trace": tracer.read_trace_summary(),
    }


@router.get("/skills")
async def list_skills() -> dict:
    """列出所有可用 Skills"""
    from app.agent.skill_loader import discover_skills
    skills = discover_skills()
    return {"skills": [{"name": s["name"], "description": s["description"]} for s in skills]}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
