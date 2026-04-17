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
        # REQ-2: prompt should contain file CONTENT inline, not just path
        assert "# Fix login" in prompt

    @patch("ai_loop.brain.RoleRunner.call")
    def test_decide_round_summary(self, mock_call: MagicMock, ai_loop_dir: Path):
        mock_call.return_value = '{"decision": "PASS", "reason": "ok", "details": "summary text"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        for f in ("requirement.md", "design.md", "dev-log.md", "acceptance.md"):
            (round_dir / f).write_text(f"# {f}")

        result = brain.decide("round_summary", round_dir=round_dir)

        assert result.decision == "PASS"
        assert result.details == "summary text"

    def test_brain_allowed_tools_empty(self, ai_loop_dir: Path):
        """REQ-2: Brain should use no tools (content is inlined)."""
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        assert brain._runner.allowed_tools == []

    @patch("ai_loop.brain.RoleRunner.call")
    def test_decide_prompt_contains_file_content_not_path(self, mock_call: MagicMock, ai_loop_dir: Path):
        """REQ-2: prompt should say '相关文件内容' and '根据上述文件内容'."""
        mock_call.return_value = '{"decision": "PROCEED", "reason": "ok"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("req body text")

        brain.decide("post_requirement", round_dir=round_dir)

        prompt = mock_call.call_args[0][0]
        assert "相关文件内容" in prompt
        assert "根据上述文件内容" in prompt

    @patch("ai_loop.brain.RoleRunner.call")
    def test_summarize_memories(self, mock_call: MagicMock, ai_loop_dir: Path):
        """REQ-3: Brain should be able to summarize old memories."""
        mock_call.return_value = "This is a compressed summary"
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))

        result = brain.summarize_memories("### Round 001\n- old note\n### Round 002\n- old note 2")

        assert result == "This is a compressed summary"
        prompt = mock_call.call_args[0][0]
        assert "old note" in prompt

    def test_brain_decision_with_memories(self):
        """REQ-4: BrainDecision should parse memories field from JSON."""
        raw = json.dumps({
            "decision": "PASS",
            "reason": "ok",
            "details": "summary",
            "memories": {
                "product": "product memory",
                "developer": "developer memory",
            }
        })
        d = BrainDecision.from_claude_output(raw)
        assert d.memories == {
            "product": "product memory",
            "developer": "developer memory",
        }

    def test_brain_decision_without_memories_defaults_empty(self):
        """REQ-4: Missing memories field should default to empty dict."""
        raw = '{"decision": "PASS", "reason": "ok"}'
        d = BrainDecision.from_claude_output(raw)
        assert d.memories == {}

    @patch("ai_loop.brain.RoleRunner.call")
    def test_round_summary_instruction_requests_memories(self, mock_call: MagicMock, ai_loop_dir: Path):
        """REQ-4: round_summary prompt should request per-role memories."""
        mock_call.return_value = '{"decision": "PASS", "reason": "ok", "details": "sum"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        for f in ("requirement.md", "design.md", "dev-log.md", "acceptance.md"):
            (round_dir / f).write_text(f"# {f}")

        brain.decide("round_summary", round_dir=round_dir)

        prompt = mock_call.call_args[0][0]
        assert "memories" in prompt
        assert "product" in prompt
        assert "developer" in prompt

    @patch("ai_loop.brain.RoleRunner.call")
    def test_round_summary_no_generic_format_hint(self, mock_call: MagicMock, ai_loop_dir: Path):
        """round_summary prompt should not contain the generic JSON format hint."""
        mock_call.return_value = '{"decision": "PASS", "reason": "ok", "details": "sum"}'
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("# req")

        brain.decide("round_summary", round_dir=round_dir)

        prompt = mock_call.call_args[0][0]
        # Should NOT contain the generic format that lacks memories field
        assert '"details": "补充细节（可选）"' not in prompt
        # Should contain the round_summary-specific format reference
        assert "按上述格式输出" in prompt

    @patch("ai_loop.brain.RoleRunner.call")
    def test_generate_code_digest(self, mock_call: MagicMock, ai_loop_dir: Path):
        """REQ-5: Brain should generate code digest from project info."""
        mock_call.return_value = "# Code Digest\n\nProject structure summary"
        brain = Brain(orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator"))
        digest_path = ai_loop_dir / "code-digest.md"

        brain.generate_code_digest(
            project_path="/tmp/project",
            digest_path=digest_path,
            tree_output="src/\n  app.py",
            diff_output="+ new line",
        )

        assert digest_path.exists()
        assert "Project structure summary" in digest_path.read_text()
        prompt = mock_call.call_args[0][0]
        assert "src/" in prompt
        assert "new line" in prompt
