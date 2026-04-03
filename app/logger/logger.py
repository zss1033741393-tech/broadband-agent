import logging
import logging.config
import logging.handlers
import os
import time
import yaml
from contextlib import contextmanager
from typing import Generator


def setup_logging() -> None:
    """初始化日志配置，从 configs/logging.yaml 加载"""
    # 确保日志目录存在
    os.makedirs("logs", exist_ok=True)

    config_path = "configs/logging.yaml"
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    else:
        # fallback：基础配置
        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="[%(asctime)s] [%(levelname)s] %(message)s",
        )


def get_logger(stage: str, component: str) -> logging.LoggerAdapter:
    """获取带 stage/component 上下文的 logger

    Args:
        stage: 当前 Pipeline Stage，如 "Stage1"、"Stage2"
        component: 当前组件名，如 "IntentParser"、"PlanFiller"

    Returns:
        带上下文字段的 LoggerAdapter
    """
    logger = logging.getLogger("pipeline")
    return logging.LoggerAdapter(logger, {"stage": stage, "component": component})


@contextmanager
def log_step(
    logger: logging.LoggerAdapter, action: str, **extra: object
) -> Generator[None, None, None]:
    """计时上下文管理器，自动记录步骤开始、完成和耗时

    Args:
        logger: 由 get_logger 获取的 LoggerAdapter
        action: 步骤描述
        **extra: 附加的日志字段
    """
    start = time.perf_counter()
    logger.debug(f"{action} 开始")
    try:
        yield
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error(f"{action} 异常 | latency_ms={elapsed:.0f} | error={e}")
        raise
    else:
        elapsed = (time.perf_counter() - start) * 1000
        logger.debug(f"{action} 完成 | latency_ms={elapsed:.0f}")


def log_llm_call(
    logger: logging.LoggerAdapter,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
) -> None:
    """记录 LLM 调用信息（模型、token 用量、延迟）

    Args:
        logger: 由 get_logger 获取的 LoggerAdapter
        model: 模型名称
        tokens_in: 输入 token 数
        tokens_out: 输出 token 数
        latency_ms: 调用延迟（毫秒）
    """
    logger.debug(
        f"LLM 调用 | model={model} | tokens_in={tokens_in} "
        f"| tokens_out={tokens_out} | latency_ms={latency_ms:.0f}"
    )
