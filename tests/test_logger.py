import json
from pathlib import Path

import pytest

from ai_loop.logger import EventLogger


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


class TestEventLogger:
    def test_creates_log_directory(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        assert log_dir.exists()
        logger.close()

    def test_log_file_created_on_first_write(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_phase_transition("start", "product:explore")
        logger.close()
        assert (log_dir / "round-001.jsonl").exists()

    def test_jsonl_format(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=2)
        logger.log_ai_call("product", "explore", "test prompt content")
        logger.close()

        lines = (log_dir / "round-002.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event_type"] == "ai_call"
        assert event["round"] == 2
        assert event["role"] == "product"
        assert event["phase"] == "explore"
        assert event["prompt_length"] == len("test prompt content")
        assert event["prompt_preview"] == "test prompt content"
        assert "timestamp" in event

    def test_log_ai_result(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_ai_result(
            role="developer", phase="implement",
            result="code changes applied",
            duration_ms=5000, cost_usd=0.05, turns=3,
        )
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert event["event_type"] == "ai_result"
        assert event["result_length"] == len("code changes applied")
        assert event["duration_ms"] == 5000
        assert event["cost_usd"] == 0.05
        assert event["turns"] == 3

    def test_log_brain_decision(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_brain_decision("post_requirement", "PROCEED", "clear enough")
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert event["event_type"] == "brain_decision"
        assert event["decision_point"] == "post_requirement"
        assert event["decision"] == "PROCEED"
        assert event["reason"] == "clear enough"

    def test_log_user_interaction(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_user_interaction("collaboration_qa", "What do you prefer?", "option A")
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert event["event_type"] == "user_interaction"
        assert event["interaction_type"] == "collaboration_qa"
        assert event["question_preview"] == "What do you prefer?"
        assert event["answer"] == "option A"

    def test_log_error(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_error("developer:implement", "Claude CLI timeout")
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert event["event_type"] == "error"
        assert event["context"] == "developer:implement"
        assert event["error"] == "Claude CLI timeout"

    def test_multiple_events_appended(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_phase_transition("start", "product:explore")
        logger.log_ai_call("product", "explore", "prompt")
        logger.log_ai_result("product", "explore", "result", 1000, 0.01, 2)
        logger.close()

        lines = (log_dir / "round-001.jsonl").read_text().strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(l)["event_type"] for l in lines]
        assert types == ["phase_transition", "ai_call", "ai_result"]

    def test_prompt_preview_truncated(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        long_prompt = "x" * 500
        logger.log_ai_call("product", "explore", long_prompt)
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert len(event["prompt_preview"]) == 200
        assert event["prompt_length"] == 500

    def test_error_truncated(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        long_error = "e" * 1000
        logger.log_error("ctx", long_error)
        logger.close()

        event = json.loads((log_dir / "round-001.jsonl").read_text().strip())
        assert len(event["error"]) == 500

    def test_set_round_switches_file(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_phase_transition("start", "product:explore")
        logger.set_round(2)
        logger.log_phase_transition("start", "product:explore")
        logger.close()

        assert (log_dir / "round-001.jsonl").exists()
        assert (log_dir / "round-002.jsonl").exists()
        lines_1 = (log_dir / "round-001.jsonl").read_text().strip().split("\n")
        lines_2 = (log_dir / "round-002.jsonl").read_text().strip().split("\n")
        assert len(lines_1) == 1
        assert len(lines_2) == 1

    def test_close_idempotent(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.log_phase_transition("start", "end")
        logger.close()
        logger.close()  # should not raise

    def test_no_file_created_without_writes(self, log_dir: Path):
        logger = EventLogger(log_dir, round_num=1)
        logger.close()
        assert not (log_dir / "round-001.jsonl").exists()
