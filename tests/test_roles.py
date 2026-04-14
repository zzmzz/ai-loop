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
    @patch("ai_loop.roles.base.subprocess.run")
    def test_call_claude_captures_output(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            stdout="Claude output here",
            stderr="",
            returncode=0,
        )
        runner = RoleRunner(
            role_name="product",
            allowed_tools=["Read", "Bash"],
        )
        output = runner.call("Do something", cwd="/tmp/ws")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd
        assert "--allowedTools" in cmd
        assert output == "Claude output here"

    @patch("ai_loop.roles.base.subprocess.run")
    def test_call_claude_nonzero_exit_raises(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="error occurred",
            returncode=1,
        )
        runner = RoleRunner(role_name="dev", allowed_tools=["Read"])

        with pytest.raises(RuntimeError, match="Claude CLI 调用失败"):
            runner.call("Do something", cwd="/tmp")


from ai_loop.roles.product import ProductRole
from ai_loop.roles.developer import DeveloperRole
from ai_loop.roles.reviewer import ReviewerRole


class TestProductRole:
    def test_explore_prompt_includes_base_url(self):
        role = ProductRole(base_url="http://localhost:3000")
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "http://localhost:3000" in prompt
        assert "requirement.md" in prompt
        assert "Fix login" in prompt

    def test_acceptance_prompt_includes_requirement(self):
        role = ProductRole(base_url="http://localhost:3000")
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "requirement.md" in prompt
        assert "acceptance.md" in prompt
        assert "PASS" in prompt and "FAIL" in prompt

    def test_clarify_prompt(self):
        role = ProductRole(base_url="http://localhost:3000")
        prompt = role.build_prompt("clarify", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "design.md" in prompt
        assert "clarification.md" in prompt


class TestDeveloperRole:
    def test_design_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt("design", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "requirement.md" in prompt
        assert "design.md" in prompt
        assert "待确认问题" in prompt

    def test_implement_prompt_includes_tdd(self):
        role = DeveloperRole()
        prompt = role.build_prompt("implement", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "RED" in prompt
        assert "GREEN" in prompt
        assert "dev-log.md" in prompt

    def test_fix_review_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt("fix_review", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "review.md" in prompt


class TestReviewerRole:
    def test_review_prompt(self):
        role = ReviewerRole()
        prompt = role.build_prompt("review", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "requirement.md" in prompt
        assert "design.md" in prompt
        assert "git diff" in prompt
        assert "APPROVE" in prompt
        assert "REQUEST_CHANGES" in prompt
