# tests/test_cli.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import yaml
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

    def test_init_creates_nonexistent_directory(self, tmp_path: Path):
        """init should auto-create nested directories that don't exist."""
        nested = tmp_path / "a" / "b" / "c"
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", str(nested),
            "--name", "test",
            "--type", "cli",
            "--test-command", "pytest",
            "--no-detect",
        ])
        assert result.exit_code == 0, result.output
        assert (nested / ".ai-loop").exists()
        assert (nested / ".ai-loop" / "config.yaml").exists()

    @patch("ai_loop.cli.detect_project_config")
    def test_init_auto_detect(self, mock_detect, tmp_project: Path):
        mock_detect.return_value = {
            "name": "my-app",
            "description": "A cool app",
            "start_command": "pnpm dev",
            "health_url": "http://localhost:5173",
            "base_url": "http://localhost:5173",
            "goals": ["Improve performance"],
        }
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(tmp_project)], input="y\n")

        assert result.exit_code == 0
        mock_detect.assert_called_once()
        config = yaml.safe_load((tmp_project / ".ai-loop" / "config.yaml").read_text())
        assert config["project"]["name"] == "my-app"
        assert config["server"]["start_command"] == "pnpm dev"
        assert config["goals"] == ["Improve performance"]


    def test_init_cli_with_run_examples(self, tmp_project: Path):
        """--run-example should be written to config.yaml run_examples."""
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", str(tmp_project),
            "--name", "my-cli",
            "--type", "cli",
            "--test-command", "pytest",
            "--run-example", "my-cli --help",
            "--run-example", "my-cli init /tmp/test",
            "--no-detect",
        ])
        assert result.exit_code == 0, result.output
        config = yaml.safe_load((tmp_project / ".ai-loop" / "config.yaml").read_text())
        assert config["verification"]["run_examples"] == ["my-cli --help", "my-cli init /tmp/test"]

    @patch("ai_loop.cli.detect_project_config")
    def test_init_cli_auto_detect(self, mock_detect, tmp_project: Path):
        """CLI project with auto-detect should use detected test_command."""
        mock_detect.return_value = {
            "name": "my-cli",
            "description": "A CLI tool",
            "test_command": "pytest tests/ -v",
            "run_examples": ["my-cli --help"],
        }
        runner = CliRunner()
        result = runner.invoke(main, [
            "init", str(tmp_project),
            "--type", "cli",
        ], input="y\n")

        assert result.exit_code == 0, result.output
        mock_detect.assert_called_once()
        config = yaml.safe_load((tmp_project / ".ai-loop" / "config.yaml").read_text())
        assert config["project"]["name"] == "my-cli"
        assert config["verification"]["test_command"] == "pytest tests/ -v"


class TestRunCommand:
    @patch("ai_loop.cli.Orchestrator")
    def test_run_single_round_and_stop(self, MockOrch: MagicMock, ai_loop_dir: Path):
        mock_orch = MagicMock()
        mock_orch.current_round = 1
        mock_orch.run_single_round.return_value = "Round completed successfully"
        MockOrch.return_value = mock_orch

        runner = CliRunner()
        result = runner.invoke(main, ["run", str(ai_loop_dir.parent)], input="s\n")

        assert result.exit_code == 0
        mock_orch.run_single_round.assert_called_once()

    @patch("ai_loop.cli.Orchestrator")
    def test_run_error_add_goal_no_persist(self, MockOrch: MagicMock, ai_loop_dir: Path):
        """Error recovery path: [g] should NOT persist goal to config.yaml."""
        mock_orch = MagicMock()
        mock_orch.current_round = 1
        mock_orch.run_single_round.side_effect = [RuntimeError("boom"), "OK"]
        MockOrch.return_value = mock_orch

        config_before = yaml.safe_load((ai_loop_dir / "config.yaml").read_text())
        goals_before = list(config_before.get("goals", []))

        runner = CliRunner()
        # g -> enter goal -> s (stop after retry succeeds)
        result = runner.invoke(
            main, ["run", str(ai_loop_dir.parent)],
            input="g\n新目标\ns\n",
        )
        assert result.exit_code == 0

        config_after = yaml.safe_load((ai_loop_dir / "config.yaml").read_text())
        assert config_after.get("goals", []) == goals_before
        mock_orch.add_goal.assert_called_once_with("新目标")

    @patch("ai_loop.cli.Orchestrator")
    def test_run_complete_add_goal_no_persist(self, MockOrch: MagicMock, ai_loop_dir: Path):
        """Round complete path: [g] should NOT persist goal to config.yaml."""
        mock_orch = MagicMock()
        mock_orch.current_round = 1
        mock_orch.run_single_round.return_value = "Round completed"
        MockOrch.return_value = mock_orch

        config_before = yaml.safe_load((ai_loop_dir / "config.yaml").read_text())
        goals_before = list(config_before.get("goals", []))

        runner = CliRunner()
        # g -> enter goal -> s (stop)
        result = runner.invoke(
            main, ["run", str(ai_loop_dir.parent)],
            input="g\n新目标\ns\n",
        )
        assert result.exit_code == 0

        config_after = yaml.safe_load((ai_loop_dir / "config.yaml").read_text())
        assert config_after.get("goals", []) == goals_before
        mock_orch.add_goal.assert_called_once_with("新目标")
