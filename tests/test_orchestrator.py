# tests/test_orchestrator.py
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest
from ai_loop.orchestrator import Orchestrator
from ai_loop.brain import BrainDecision
from ai_loop.config import load_config
from ai_loop.state import load_state
import yaml


@pytest.fixture
def orch(ai_loop_dir: Path, sample_config: dict) -> Orchestrator:
    # Point config path to actual project dir
    sample_config["project"]["path"] = str(ai_loop_dir.parent)
    config_path = ai_loop_dir / "config.yaml"
    config_path.write_text(yaml.dump(sample_config))
    return Orchestrator(ai_loop_dir)


class TestOrchestrator:
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_single_round_happy_path(
        self, mock_stop, mock_start, mock_brain, mock_role, orch: Orchestrator
    ):
        # Brain always approves
        mock_brain.return_value = BrainDecision(decision="PROCEED", reason="ok")

        # Override acceptance brain call to return PASS
        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
            if point == "post_review":
                return BrainDecision(decision="APPROVE", reason="ok")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Good round")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = orch.run_single_round()

        assert summary is not None
        # Verify roles were called in correct order
        role_calls = [c[0][0] for c in mock_role.call_args_list]
        assert "product:explore" in role_calls
        assert "developer:design" in role_calls
        assert "developer:implement" in role_calls
        assert "reviewer:review" in role_calls
        assert "product:acceptance" in role_calls

    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_review_rework_loop(
        self, mock_stop, mock_start, mock_brain, mock_role, orch: Orchestrator
    ):
        call_count = {"review": 0}

        def brain_side_effect(point, **kwargs):
            if point == "post_review":
                call_count["review"] += 1
                if call_count["review"] < 3:
                    return BrainDecision(decision="REWORK", reason="needs fix")
                return BrainDecision(decision="APPROVE", reason="ok now")
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        orch.run_single_round()

        # Developer fix_review should have been called twice
        role_calls = [c[0][0] for c in mock_role.call_args_list]
        assert role_calls.count("developer:fix_review") == 2


@pytest.fixture
def cli_orch(cli_ai_loop_dir: Path) -> Orchestrator:
    return Orchestrator(cli_ai_loop_dir)


class TestOrchestratorCliProject:
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    def test_server_not_started_for_cli_project(
        self, mock_brain, mock_role, cli_orch: Orchestrator
    ):
        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
            if point == "post_review":
                return BrainDecision(decision="APPROVE", reason="ok")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = cli_orch.run_single_round()
        assert summary is not None
