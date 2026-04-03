"""日志模块 — 提供 [Skill:xxx] 标签格式的结构化日志"""
import logging
from typing import Any


def get_skill_logger(skill_name: str) -> logging.Logger:
    """获取带 Skill 标签的 logger"""
    return logging.getLogger(f"Skill:{skill_name}")


class SkillLoggerAdapter(logging.LoggerAdapter):
    """为 Skill 日志自动添加 [Skill:xxx] 前缀"""

    def __init__(self, skill_name: str) -> None:
        logger = logging.getLogger("agent")
        super().__init__(logger, {"skill": skill_name})

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        return f"[Skill:{self.extra['skill']}] {msg}", kwargs

    def llm_call(self, model: str, tokens_in: int, latency_ms: int = 0) -> None:
        self.debug(
            "LLM 调用 | model=%s | tokens_in=%d | latency_ms=%d",
            model,
            tokens_in,
            latency_ms,
        )

    def skill_loaded(self, trigger: str = "") -> None:
        self.info("Agent 加载 Skill | trigger=%s", trigger)

    def skill_done(self, result: str = "") -> None:
        self.info("Skill 执行完成 | result=%s", result)

    def conflict(self, detail: str) -> None:
        self.warning("校验失败 | conflict=%s", detail)
