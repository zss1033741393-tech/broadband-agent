from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.pipeline import PipelineState, run_pipeline
from app.db.crud import get_pipeline_output, get_session, get_traces, get_llm_traces

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


class ChatRequest(BaseModel):
    """对话请求"""

    user_input: str
    user_id: str = "anonymous"
    session_id: Optional[str] = None
    dialog_history: Optional[list[dict]] = None


class ChatResponse(BaseModel):
    """对话响应"""

    session_id: str
    status: str                          # init / waiting_followup / running / done / error
    followup_question: str = ""          # 追问内容（status=waiting_followup 时）
    output_files: list[str] = []         # 生成的配置文件路径
    intent_summary: dict = {}            # 意图解析摘要
    error_message: str = ""


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """主对话接口：接收用户输入，驱动 Pipeline 执行

    - 首次输入：触发完整 Pipeline
    - 追问回复：携带 session_id 续接对话，补充缺失信息
    """
    try:
        state: PipelineState = await run_pipeline(
            user_input=request.user_input,
            user_id=request.user_id,
            session_id=request.session_id,
            dialog_history=request.dialog_history,
        )

        intent_summary = {}
        if state.intent_goal:
            intent_summary = {
                "user_type": state.intent_goal.user_type,
                "scenario": state.intent_goal.scenario,
                "priority_level": state.intent_goal.guarantee_target.priority_level,
            }

        return ChatResponse(
            session_id=state.session_id,
            status=state.status,
            followup_question=state.followup_question,
            output_files=state.output.output_files if state.output else [],
            intent_summary=intent_summary,
            error_message=state.error_message,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=dict)
async def get_session_info(session_id: str) -> dict:
    """查询会话信息"""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/output/{session_id}", response_model=dict)
async def get_output(session_id: str) -> dict:
    """获取 Pipeline 最终输出配置"""
    output = await get_pipeline_output(session_id)
    if not output:
        raise HTTPException(status_code=404, detail="该会话尚无输出配置")
    return output


@router.get("/traces/{session_id}", response_model=list)
async def get_session_traces(session_id: str) -> list:
    """查询会话的 Agent 运行轨迹

    返回该会话下所有 Stage 的执行轨迹，包括：
    - stage_start / stage_end：各阶段的输入输出和耗时
    - llm_call：LLM 调用记录（model、tokens、latency）
    - tool_call：Tool 函数调用记录
    - followup：追问事件
    - error：异常事件
    """
    traces = await get_traces(session_id)
    if not traces:
        raise HTTPException(status_code=404, detail="该会话暂无轨迹记录")
    return traces


@router.get("/llm-traces/{session_id}", response_model=list)
async def get_session_llm_traces(session_id: str) -> list:
    """查询会话的 LLM 请求级详细轨迹

    每条记录对应一次 LLM API 调用，包含：
    - model / temperature / max_tokens / is_stream：请求参数
    - request_messages：发送给模型的完整 messages 数组（含 system/user/tool）
    - response_content：模型最终回复文本
    - reasoning_content：模型推理过程（CoT/thinking，支持 o1/deepseek-r1 等）
    - tool_calls：模型发起的工具调用 [{id, name, arguments}]
    - tool_results：工具执行结果 [{tool_call_id, name, content}]
    - tokens_in / tokens_out / tokens_reasoning：token 用量
    - latency_ms：本次请求耗时
    """
    traces = await get_llm_traces(session_id)
    if not traces:
        raise HTTPException(status_code=404, detail="该会话暂无 LLM 请求记录")
    return traces


@router.get("/health")
async def health() -> dict:
    """健康检查"""
    return {"status": "ok"}
