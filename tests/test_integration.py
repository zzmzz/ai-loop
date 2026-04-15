# tests/test_integration.py
"""
Integration test: runs a full single round with a mock Claude CLI.
Instead of calling the real `claude` binary, we patch subprocess.Popen
to return canned stream-json responses per role.
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
import yaml
import pytest
from ai_loop.orchestrator import Orchestrator
from ai_loop.state import load_state


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
    @patch("ai_loop.roles.base.subprocess.Popen")
    @patch("ai_loop.server.subprocess.Popen")
    @patch("ai_loop.server.requests.get")
    def test_full_round_completes(self, mock_get, mock_server_popen, mock_role_popen, full_project: Path):
        # Mock server health check
        mock_server_popen.return_value = MagicMock(poll=MagicMock(return_value=None))
        mock_get.return_value = MagicMock(status_code=200)

        # Mock RoleRunner Popen - return stream-json result events.
        # The mock captures stdin writes to detect Brain decision calls
        # and returns appropriate JSON responses.
        def make_mock_proc(*args, **kwargs):
            mock_proc = MagicMock()
            captured_input = []

            def capture_write(data):
                captured_input.append(data)

            mock_proc.stdin.write = MagicMock(side_effect=capture_write)
            mock_proc.stdin.flush = MagicMock()

            def stdout_iter():
                # _send_message wraps prompt in JSON via json.dumps, which
                # escapes Chinese chars as \uXXXX. Match on ASCII keywords
                # from the Brain decision_point values instead.
                raw = " ".join(captured_input)
                is_brain = any(dp in raw for dp in (
                    "post_requirement", "post_design", "post_implementation",
                    "post_review", "post_acceptance", "round_summary",
                ))
                if is_brain:
                    if "post_acceptance" in raw:
                        result = '{"decision": "PASS", "reason": "ok"}'
                    elif "post_review" in raw:
                        result = '{"decision": "APPROVE", "reason": "ok"}'
                    elif "round_summary" in raw:
                        result = '{"decision": "PASS", "reason": "ok", "details": "Round completed"}'
                    else:
                        result = '{"decision": "PROCEED", "reason": "ok"}'
                else:
                    result = "Role output"
                yield json.dumps({"type": "result", "result": result, "session_id": "s1"})

            mock_proc.stdout.__iter__ = MagicMock(side_effect=stdout_iter)
            mock_proc.wait.return_value = None
            mock_proc.returncode = 0
            return mock_proc

        mock_role_popen.side_effect = make_mock_proc

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
