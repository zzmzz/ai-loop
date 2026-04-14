from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json


@dataclass
class LoopState:
    current_round: int = 1
    phase: str = "idle"
    retry_counts: dict = field(default_factory=lambda: {"review": 0, "acceptance": 0})
    history: list[dict] = field(default_factory=list)

    def complete_round(self, summary: str) -> None:
        self.history.append({
            "round": self.current_round,
            "result": "completed",
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.current_round += 1
        self.phase = "idle"
        self.retry_counts = {"review": 0, "acceptance": 0}

    def increment_retry(self, kind: str) -> int:
        self.retry_counts[kind] = self.retry_counts.get(kind, 0) + 1
        return self.retry_counts[kind]

    def round_dir(self, ai_loop_dir: Path) -> Path:
        return ai_loop_dir / "rounds" / f"{self.current_round:03d}"

    def to_dict(self) -> dict:
        return {
            "current_round": self.current_round,
            "phase": self.phase,
            "retry_counts": self.retry_counts,
            "history": self.history,
        }


def load_state(path: Path) -> LoopState:
    if not path.exists():
        return LoopState()
    with open(path) as f:
        data = json.load(f)
    return LoopState(
        current_round=data.get("current_round", 1),
        phase=data.get("phase", "idle"),
        retry_counts=data.get("retry_counts", {"review": 0, "acceptance": 0}),
        history=data.get("history", []),
    )


def save_state(state: LoopState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
