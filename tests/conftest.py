from pathlib import Path
import json
import pytest
import yaml


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal target project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "index.js").write_text("console.log('hello');")
    return project


@pytest.fixture
def sample_config() -> dict:
    """Legacy config format using browser/server (tests backward compat)."""
    return {
        "project": {
            "name": "test-project",
            "path": "/tmp/test-project",
            "description": "A test project",
        },
        "goals": ["Improve the UI"],
        "server": {
            "start_command": "npm start",
            "start_cwd": ".",
            "health_url": "http://localhost:3000",
            "health_timeout": 30,
            "stop_signal": "SIGTERM",
        },
        "browser": {"base_url": "http://localhost:3000"},
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }


@pytest.fixture
def cli_sample_config() -> dict:
    """New config format using verification (CLI project)."""
    return {
        "project": {
            "name": "test-cli",
            "path": "/tmp/test-cli",
            "description": "A CLI tool",
        },
        "goals": ["Add feature"],
        "verification": {
            "type": "cli",
            "test_command": "python -m pytest tests/ -v",
            "run_examples": ["test-cli --help"],
        },
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }


@pytest.fixture
def ai_loop_dir(tmp_project: Path, sample_config: dict) -> Path:
    """Create a .ai-loop directory structure inside a project."""
    ai_dir = tmp_project / ".ai-loop"
    ai_dir.mkdir()
    (ai_dir / "config.yaml").write_text(yaml.dump(sample_config))
    (ai_dir / "state.json").write_text(json.dumps({
        "current_round": 1,
        "phase": "idle",
        "retry_counts": {"review": 0, "acceptance": 0},
        "history": [],
    }))
    (ai_dir / "rounds").mkdir()
    (ai_dir / "rounds" / "001").mkdir()
    workspaces = ai_dir / "workspaces"
    for role in ("orchestrator", "product", "developer"):
        ws = workspaces / role
        ws.mkdir(parents=True)
        (ws / "CLAUDE.md").write_text(f"# Role: {role}\n")
        if role != "orchestrator":
            (ws / "notes").mkdir()
    return ai_dir


@pytest.fixture
def cli_ai_loop_dir(tmp_path: Path, cli_sample_config: dict) -> Path:
    """Create a .ai-loop directory for a CLI project (no server)."""
    project = tmp_path / "test-cli"
    project.mkdir()
    ai_dir = project / ".ai-loop"
    ai_dir.mkdir()
    cli_sample_config["project"]["path"] = str(project)
    (ai_dir / "config.yaml").write_text(yaml.dump(cli_sample_config))
    (ai_dir / "state.json").write_text(json.dumps({
        "current_round": 1,
        "phase": "idle",
        "retry_counts": {"review": 0, "acceptance": 0},
        "history": [],
    }))
    (ai_dir / "rounds").mkdir()
    (ai_dir / "rounds" / "001").mkdir()
    workspaces = ai_dir / "workspaces"
    for role in ("orchestrator", "product", "developer"):
        ws = workspaces / role
        ws.mkdir(parents=True)
        (ws / "CLAUDE.md").write_text(f"# Role: {role}\n")
        if role != "orchestrator":
            (ws / "notes").mkdir()
    return ai_dir
