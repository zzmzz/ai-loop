from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import pytest
from ai_loop.brain import Brain, BrainDecision


class TestBrainDecision:
    def test_parse_valid_json(self):
        raw = '{"decision": "PROCEED", "reason": "Looks clear", "details": ""}'
        d = BrainDecision.from_claude_output(raw)
        assert d.decision == "PROCEED"
        assert d.reason == "Looks clear"

    def test_parse_json_embedded_in_text(self):
        raw = 'Here is my analysis:\n```json\n{"decision": "REFINE", "reason": "Too vague"}\n```'
        d = BrainDecision.from_claude_output(raw)
        assert d.decision == "REFINE"

    def test_parse_fallback_on_garbage(self):
        raw = "I think we should proceed because it looks fine"
        d = BrainDecision.from_claude_output(raw)
        assert d.decision == "PROCEED"
        assert "fallback" in d.reason.lower() or "parse" in d.reason.lower()


class TestBrain:
    @patch("ai_loop.brain.RoleRunner.call")
    def test_decide_post_requirement(self, mock_call: MagicMock, ai_loop_dir: Path):
        mock_call.return_value = '{"decision": "PROCEED", "reason": "Clear enough"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("---\nresult: null\n---\n# Fix login")

        result = brain.decide("post_requirement", round_dir=round_dir)

        assert result.decision == "PROCEED"
        mock_call.assert_called_once()
        prompt = mock_call.call_args[0][0]
        assert "requirement.md" in prompt

    @patch("ai_loop.brain.RoleRunner.call")
    def test_decide_post_review_approve(self, mock_call: MagicMock, ai_loop_dir: Path):
        mock_call.return_value = '{"decision": "APPROVE", "reason": "All good"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("# req")
        (round_dir / "review.md").write_text("---\nresult: APPROVE\n---\nLGTM")

        result = brain.decide("post_review", round_dir=round_dir)

        assert result.decision == "APPROVE"

    @patch("ai_loop.brain.RoleRunner.call")
    def test_decide_round_summary(self, mock_call: MagicMock, ai_loop_dir: Path):
        mock_call.return_value = '{"decision": "PASS", "reason": "ok", "details": "summary text"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        for f in ("requirement.md", "design.md", "dev-log.md", "review.md", "acceptance.md"):
            (round_dir / f).write_text(f"# {f}")

        result = brain.decide("round_summary", round_dir=round_dir)

        assert result.decision == "PASS"
        assert result.details == "summary text"
