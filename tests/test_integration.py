# tests/test_integration.py
"""
Integration test: runs a full single round with a mock Claude CLI.
Instead of calling the real `claude` binary, we patch subprocess.run
to return canned responses per role.
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import yaml
import pytest
from ai_loop.orchestrator import Orchestrator
from ai_loop.state import load_state


MOCK_RESPONSES = {
    "product": {
        "explore": "Written requirement.md",
        "clarify": "Written clarification.md",
        "acceptance": "Written acceptance.md",
    },
    "developer": {
        "design": "Written design.md",
        "implement": "Written dev-log.md",
        "verify": "Verification passed",
        "fix_review": "Fixed issues",
    },
    "reviewer": {
        "review": "Written review.md",
    },
    "brain": "default_brain",
}


def mock_subprocess_run(cmd, **kwargs):
    """Route mock responses based on the prompt content."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stderr = ""

    prompt = ""
    if "-p" in cmd:
        idx = cmd.index("-p")
        if idx + 1 < len(cmd):
            prompt = cmd[idx + 1]

    # Brain calls: return JSON decisions
    if "决策大脑" in prompt or "决策点" in prompt:
        if "post_acceptance" in prompt or "acceptance" in prompt.lower():
            mock.stdout = '{"decision": "PASS", "reason": "ok"}'
        elif "post_review" in prompt or "审查" in prompt:
            mock.stdout = '{"decision": "APPROVE", "reason": "ok"}'
        elif "round_summary" in prompt:
            mock.stdout = '{"decision": "PASS", "reason": "ok", "details": "Round completed"}'
        else:
            mock.stdout = '{"decision": "PROCEED", "reason": "ok"}'
    else:
        mock.stdout = "Role output"

    return mock


@pytest.fixture
def full_project(tmp_path: Path) -> Path:
    """Set up a complete project with .ai-loop initialized."""
    project = tmp_path / "myproject"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "app.js").write_text("console.log('app');")

    ai_dir = project / ".ai-loop"
    ai_dir.mkdir()
    (ai_dir / "rounds").mkdir()

    config = {
        "project": {"name": "myproject", "path": str(project), "description": "Test"},
        "goals": ["Improve UX"],
        "server": {
            "start_command": "echo ok",
            "start_cwd": ".",
            "health_url": "http://localhost:3000",
            "health_timeout": 2,
            "stop_signal": "SIGTERM",
        },
        "browser": {"base_url": "http://localhost:3000"},
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }
    (ai_dir / "config.yaml").write_text(yaml.dump(config))
    (ai_dir / "state.json").write_text(json.dumps({
        "current_round": 1, "phase": "idle",
        "retry_counts": {"review": 0, "acceptance": 0}, "history": [],
    }))

    workspaces = ai_dir / "workspaces"
    for role in ("orchestrator", "product", "developer", "reviewer"):
        ws = workspaces / role
        ws.mkdir(parents=True)
        (ws / "CLAUDE.md").write_text(f"# Role: {role}\n\n## 累积记忆\n")
        if role != "orchestrator":
            (ws / "notes").mkdir()

    return project


class TestIntegration:
    @patch("ai_loop.roles.base.subprocess.run", side_effect=mock_subprocess_run)
    @patch("ai_loop.server.subprocess.Popen")
    @patch("ai_loop.server.requests.get")
    def test_full_round_completes(self, mock_get, mock_popen, mock_run, full_project: Path):
        # Mock server health check
        mock_popen.return_value = MagicMock(poll=MagicMock(return_value=None))
        mock_get.return_value = MagicMock(status_code=200)

        ai_dir = full_project / ".ai-loop"
        orch = Orchestrator(ai_dir)
        summary = orch.run_single_round()

        assert summary is not None
        assert "ESCALATE" not in summary

        # State should advance to round 2
        state = load_state(ai_dir / "state.json")
        assert state.current_round == 2
        assert len(state.history) == 1

        # Memory should be updated
        for role in ("product", "developer", "reviewer"):
            claude_md = ai_dir / "workspaces" / role / "CLAUDE.md"
            assert "Round 001" in claude_md.read_text()
