# tests/test_cli.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import pytest
from ai_loop.cli import main


class TestInitCommand:
    def test_init_creates_directory_structure(self, tmp_project: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", str(tmp_project),
            "--name", "test",
            "--start-command", "npm start",
            "--health-url", "http://localhost:3000",
            "--base-url", "http://localhost:3000",
            "--goal", "Improve UX",
        ])

        assert result.exit_code == 0
        ai_dir = tmp_project / ".ai-loop"
        assert ai_dir.exists()
        assert (ai_dir / "config.yaml").exists()
        assert (ai_dir / "state.json").exists()
        assert (ai_dir / "rounds").is_dir()
        for role in ("orchestrator", "product", "developer", "reviewer"):
            assert (ai_dir / "workspaces" / role / "CLAUDE.md").exists()

    def test_init_rejects_existing(self, tmp_project: Path):
        (tmp_project / ".ai-loop").mkdir()
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", str(tmp_project),
            "--name", "test",
            "--start-command", "npm start",
            "--health-url", "http://localhost:3000",
            "--base-url", "http://localhost:3000",
        ])
        assert result.exit_code != 0
        assert "已存在" in result.output or "already exists" in result.output.lower()


class TestRunCommand:
    @patch("ai_loop.cli.Orchestrator")
    def test_run_single_round_and_stop(self, MockOrch: MagicMock, ai_loop_dir: Path):
        mock_orch = MagicMock()
        mock_orch.run_single_round.return_value = "Round completed successfully"
        MockOrch.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(ai_loop_dir.parent)], input="s\n")

        assert result.exit_code == 0
        mock_orch.run_single_round.assert_called_once()
