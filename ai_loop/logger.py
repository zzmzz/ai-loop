import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class EventLogger:
    """Structured JSONL event logger for ai-loop rounds."""

    def __init__(self, log_dir: Path, round_num: int):
        self._log_dir = log_dir
        self._round_num = round_num
        log_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = log_dir / f"round-{round_num:03d}.jsonl"
        self._file = None

    def _ensure_open(self):
        if self._file is None:
            self._file = open(self._file_path, "a", encoding="utf-8")

    def _write(self, event: dict) -> None:
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        event["round"] = self._round_num
        self._ensure_open()
        self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

    def log_ai_call(self, role: str, phase: str, prompt: str) -> None:
        self._write({
            "event_type": "ai_call",
            "role": role,
            "phase": phase,
            "prompt_length": len(prompt),
            "prompt_preview": prompt[:200],
        })

    def log_ai_result(self, role: str, phase: str, result: str,
                      duration_ms: float = 0, cost_usd: float = 0,
                      turns: int = 0) -> None:
        self._write({
            "event_type": "ai_result",
            "role": role,
            "phase": phase,
            "result_length": len(result),
            "result_preview": result[:200],
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
            "turns": turns,
        })

    def log_brain_decision(self, decision_point: str, decision: str,
                           reason: str) -> None:
        self._write({
            "event_type": "brain_decision",
            "decision_point": decision_point,
            "decision": decision,
            "reason": reason,
        })

    def log_user_interaction(self, interaction_type: str,
                             question: str, answer: str) -> None:
        self._write({
            "event_type": "user_interaction",
            "interaction_type": interaction_type,
            "question_preview": question[:200],
            "answer": answer,
        })

    def log_phase_transition(self, from_phase: str, to_phase: str) -> None:
        self._write({
            "event_type": "phase_transition",
            "from_phase": from_phase,
            "to_phase": to_phase,
        })

    def log_error(self, context: str, error: str) -> None:
        self._write({
            "event_type": "error",
            "context": context,
            "error": error[:500],
        })

    def set_round(self, round_num: int) -> None:
        """Switch to a new round, closing the current log file."""
        self.close()
        self._round_num = round_num
        self._file_path = self._log_dir / f"round-{round_num:03d}.jsonl"
