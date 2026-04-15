from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
import pytest
from ai_loop.roles.base import RoleRunner, parse_frontmatter


class TestParseFrontmatter:
    def test_parses_yaml_frontmatter(self):
        content = (
            "---\n"
            "round: 1\n"
            "role: product\n"
            "phase: requirement\n"
            "result: null\n"
            "---\n"
            "# My requirement\n"
            "Some content here\n"
        )
        fm, body = parse_frontmatter(content)
        assert fm["round"] == 1
        assert fm["role"] == "product"
        assert fm["result"] is None
        assert "# My requirement" in body

    def test_no_frontmatter_returns_empty(self):
        content = "# Just a heading\nNo frontmatter"
        fm, body = parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_result_field_extraction(self):
        content = "---\nresult: APPROVE\n---\nLooks good."
        fm, _ = parse_frontmatter(content)
        assert fm["result"] == "APPROVE"


class TestRoleRunner:
    @patch("ai_loop.roles.base.subprocess.Popen")
    def test_call_sends_prompt_via_stdin_and_reads_result(self, mock_popen: MagicMock):
        """RoleRunner.call() should write prompt JSON to stdin and return result from stdout."""
        events = [
            '{"type": "system", "session_id": "sess-123"}',
            '{"type": "result", "result": "Final output", "session_id": "sess-123"}',
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(events))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        runner = RoleRunner(role_name="product", allowed_tools=["Read", "Bash"])
        output = runner.call("Do something", cwd="/tmp/ws")

        assert output == "Final output"
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "--input-format" in cmd
        assert "stream-json" in cmd
        assert "--output-format" in cmd
        assert "--permission-prompt-tool" in cmd
        # Verify prompt was written to stdin
        mock_proc.stdin.write.assert_called_once()
        written = mock_proc.stdin.write.call_args[0][0]
        import json as _json
        msg = _json.loads(written.strip())
        assert msg["type"] == "user"
        assert "Do something" in msg["message"]["content"]
        mock_proc.stdin.close.assert_called_once()

    @patch("ai_loop.roles.base.subprocess.Popen")
    def test_call_auto_approves_control_requests(self, mock_popen: MagicMock):
        """RoleRunner should auto-approve control_request events."""
        events = [
            '{"type": "control_request", "request_id": "req-1", "request": {"subtype": "can_use_tool", "tool_name": "Read", "input": {}}}',
            '{"type": "result", "result": "Done", "session_id": "sess-1"}',
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(events))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        runner = RoleRunner(role_name="dev", allowed_tools=["Read"])
        output = runner.call("Do something", cwd="/tmp")

        assert output == "Done"
        # stdin.write called twice: once for prompt, once for permission response
        assert mock_proc.stdin.write.call_count == 2
        import json as _json
        perm_response = _json.loads(mock_proc.stdin.write.call_args_list[1][0][0].strip())
        assert perm_response["type"] == "control_response"
        assert perm_response["response"]["response"]["behavior"] == "allow"

    @patch("ai_loop.roles.base.subprocess.Popen")
    def test_call_with_interaction_callback_on_needs_input(self, mock_popen: MagicMock):
        """When needs_input detected and callback provided, should send user answer and continue."""
        # First result has needs_input, second result is final
        events = [
            '{"type": "result", "result": "Which approach?\\n{\\"needs_input\\": true}", "session_id": "s1"}',
            '{"type": "result", "result": "Final output after answer", "session_id": "s1"}',
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(events))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        callback = MagicMock(return_value="Use approach A")
        runner = RoleRunner(role_name="dev", allowed_tools=["Read"])
        output = runner.call("Design something", cwd="/tmp", interaction_callback=callback)

        assert output == "Final output after answer"
        callback.assert_called_once()
        # The question text passed to callback should be the content before the marker
        question_arg = callback.call_args[0][0]
        assert "Which approach?" in question_arg

    @patch("ai_loop.roles.base.subprocess.Popen")
    def test_call_without_callback_ignores_needs_input(self, mock_popen: MagicMock):
        """Without interaction_callback, needs_input marker is ignored and result returned as-is."""
        events = [
            '{"type": "result", "result": "Output\\n{\\"needs_input\\": true}", "session_id": "s1"}',
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(events))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        runner = RoleRunner(role_name="dev", allowed_tools=["Read"])
        output = runner.call("Do something", cwd="/tmp")

        assert "needs_input" in output
        mock_proc.stdin.close.assert_called_once()

    @patch("ai_loop.roles.base.subprocess.Popen")
    def test_call_nonzero_exit_raises(self, mock_popen: MagicMock):
        """Non-zero exit code should raise RuntimeError."""
        events = [
            '{"type": "result", "result": "", "session_id": "s1"}',
        ]
        mock_proc = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(return_value=iter(events))
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = "error occurred"
        mock_popen.return_value = mock_proc

        runner = RoleRunner(role_name="dev", allowed_tools=["Read"])
        with pytest.raises(RuntimeError, match="Claude CLI 调用失败"):
            runner.call("Do something", cwd="/tmp")


from ai_loop.roles.product import ProductRole
from ai_loop.roles.developer import DeveloperRole
from ai_loop.roles.reviewer import ReviewerRole
from ai_loop.config import VerificationConfig


class TestProductRole:
    def test_explore_prompt_includes_base_url(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "http://localhost:3000" in prompt
        assert "requirement.md" in prompt
        assert "Fix login" in prompt

    def test_acceptance_prompt_includes_requirement(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "acceptance.md" in prompt
        assert "PASS" in prompt and "FAIL" in prompt
        # REQ-1: should NOT instruct to read requirement.md
        assert "阅读本轮需求" not in prompt
        assert "下方附带的需求文档" in prompt

    def test_clarify_prompt(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("clarify", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "clarification.md" in prompt
        # REQ-1: should NOT instruct to read design.md
        assert "请阅读：" not in prompt
        assert "已附在下方" in prompt


class TestProductRoleCli:
    def test_explore_prompt_cli_uses_run_examples(self):
        verification = VerificationConfig(
            type="cli",
            test_command="pytest tests/ -v",
            run_examples=["my-cli --help", "my-cli init /tmp/test"],
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Add feature"])

        assert "my-cli --help" in prompt
        assert "pytest tests/ -v" in prompt
        assert "Playwright" not in prompt
        assert "requirement.md" in prompt
        # REQ-5: should reference code-digest.md and incremental reading
        assert "code-digest.md" in prompt
        assert "变更部分" in prompt

    def test_acceptance_prompt_cli_uses_test_command(self):
        verification = VerificationConfig(
            type="cli",
            test_command="pytest tests/ -v",
            run_examples=["my-cli --help"],
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Add feature"])

        assert "pytest tests/ -v" in prompt
        assert "my-cli --help" in prompt
        assert "Playwright" not in prompt
        assert "PASS" in prompt and "FAIL" in prompt
        # REQ-1: should NOT instruct to read requirement.md
        assert "阅读本轮需求" not in prompt
        assert "下方附带的需求文档" in prompt

    def test_context_appended_to_prompt(self):
        verification = VerificationConfig(type="cli", test_command="pytest")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt(
            "explore", round_num=1, round_dir="/r/001",
            goals=["Add feature"], context="## Extra context\nSome info",
        )

        assert "## Extra context" in prompt
        assert "Some info" in prompt


class TestProductRoleWeb:
    def test_explore_prompt_web_uses_playwright(self):
        verification = VerificationConfig(
            type="web",
            base_url="http://localhost:3000",
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Fix login"])

        assert "http://localhost:3000" in prompt
        assert "Playwright" in prompt
        assert "requirement.md" in prompt
        # REQ-5: should reference code-digest.md and incremental reading
        assert "code-digest.md" in prompt
        assert "变更部分" in prompt

    def test_acceptance_prompt_web_uses_playwright(self):
        verification = VerificationConfig(
            type="web",
            base_url="http://localhost:3000",
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Fix login"])

        assert "http://localhost:3000" in prompt
        assert "Playwright" in prompt
        assert "PASS" in prompt and "FAIL" in prompt


class TestDeveloperRole:
    def test_design_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt("design", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "design.md" in prompt
        assert "待确认问题" in prompt
        # REQ-1: should NOT instruct to read requirement.md
        assert "阅读需求文档" not in prompt
        assert "已附在下方" in prompt

    def test_implement_prompt_includes_tdd(self):
        role = DeveloperRole()
        prompt = role.build_prompt("implement", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "RED" in prompt
        assert "GREEN" in prompt
        assert "dev-log.md" in prompt
        # REQ-1: should NOT instruct to read design/clarification
        assert "阅读设计文档" not in prompt
        assert "如有澄清文档也请阅读" not in prompt
        assert "已附在下方" in prompt

    def test_fix_review_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt("fix_review", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "dev-log.md" in prompt  # output file reference
        # REQ-1: should NOT instruct to read review.md
        assert "阅读审查意见" not in prompt
        assert "已附在下方" in prompt

    def test_verify_prompt_no_file_path(self):
        role = DeveloperRole()
        prompt = role.build_prompt("verify", round_num=1, round_dir="/r/001", goals=["Fix login"])
        # REQ-1: should reference "下方附带的需求文档" not file path
        assert "对照下方附带的需求文档" in prompt
        assert "对照 /r/001/requirement.md" not in prompt


class TestDeveloperRoleContext:
    def test_context_appended_to_design_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt(
            "design", round_num=1, round_dir="/r/001",
            goals=["Fix login"], context="## requirement.md\nFix the bug",
        )
        assert "## requirement.md" in prompt
        assert "Fix the bug" in prompt
        assert "design.md" in prompt  # original content still present


class TestReviewerRole:
    def test_review_prompt(self):
        role = ReviewerRole()
        prompt = role.build_prompt("review", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "git diff" in prompt
        assert "APPROVE" in prompt
        assert "REQUEST_CHANGES" in prompt
        # REQ-1: should NOT list file paths to read
        assert "1. 需求：" not in prompt
        assert "2. 设计：" not in prompt
        assert "已附在下方" in prompt


class TestReviewerRoleContext:
    def test_context_appended_to_review_prompt(self):
        role = ReviewerRole()
        prompt = role.build_prompt(
            "review", round_num=1, round_dir="/r/001",
            goals=["Fix login"], context="## requirement.md\nThe requirement",
        )
        assert "## requirement.md" in prompt
        assert "The requirement" in prompt
        assert "git diff" in prompt  # original content still present
