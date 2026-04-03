"""Agent 轨迹记录模块 — 每次会话保存到 traces/{session_id}/"""
import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


class AgentTracer:
    def __init__(self) -> None:
        self.session_id: str = str(uuid4())[:8]
        self.trace_dir: Path = Path(f"traces/{self.session_id}")
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        (self.trace_dir / "artifacts").mkdir(exist_ok=True)
        (self.trace_dir / "artifacts/plans").mkdir(exist_ok=True)
        (self.trace_dir / "artifacts/configs").mkdir(exist_ok=True)
        self._trace_file = (self.trace_dir / "trace.jsonl").open("a", encoding="utf-8")
        self.step: int = 0
        self.start_time: float = time.time()
        self.skills_used: set[str] = set()

    def log(self, event_type: str, **kwargs: Any) -> dict[str, Any]:
        """记录一步轨迹"""
        self.step += 1
        record: dict[str, Any] = {
            "step": self.step,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "type": event_type,
            **kwargs,
        }
        # 追踪 Skill 使用情况
        if skill := kwargs.get("skill"):
            self.skills_used.add(skill)
        self._trace_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._trace_file.flush()
        return record

    def save_artifact(self, subpath: str, data: dict[str, Any]) -> str:
        """保存阶段输出物"""
        path = self.trace_dir / "artifacts" / subpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def save_conversation(self, messages: list[dict[str, Any]]) -> None:
        """保存完整对话记录"""
        path = self.trace_dir / "conversation.json"
        path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_trace_summary(self) -> list[list[str]]:
        """读取轨迹摘要，用于 Gradio Trace 面板展示"""
        rows: list[list[str]] = []
        trace_path = self.trace_dir / "trace.jsonl"
        if not trace_path.exists():
            return rows
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                rows.append([
                    str(r.get("step", "")),
                    r.get("type", ""),
                    r.get("skill", ""),
                    r.get("content", r.get("action", r.get("result", "")))[:60],
                ])
            except json.JSONDecodeError:
                continue
        return rows

    def elapsed(self) -> int:
        """返回已用时间（秒）"""
        return int(time.time() - self.start_time)

    def close(self) -> None:
        self._trace_file.close()
