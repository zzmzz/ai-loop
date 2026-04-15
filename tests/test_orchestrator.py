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
    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_single_round_happy_path(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
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

    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_review_rework_loop(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
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


class TestOrchestratorMemoryCompact:
    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_memory_compact_called_when_exceeding_window(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
    ):
        """REQ-3: _update_all_memories should trigger compact when rounds > window."""
        # Pre-populate memories so count exceeds window
        for role_name in ("orchestrator", "product", "developer", "reviewer"):
            claude_md = orch._dir / "workspaces" / role_name / "CLAUDE.md"
            text = claude_md.read_text()
            if "## 累积记忆" not in text:
                text += "\n## 累积记忆\n"
            for i in range(1, 8):
                text += f"\n### Round {i:03d}\n- Round {i} note\n"
            claude_md.write_text(text)

        orch._config.limits.memory_window = 3

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

        with patch.object(orch._memory, "compact_memories") as mock_compact:
            orch.run_single_round()
            # compact_memories should have been called for each role's CLAUDE.md
            assert mock_compact.call_count == 4


class TestOrchestratorRoleSpecificMemories:
    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_role_specific_memories(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
    ):
        """REQ-4: Different roles should get different memory content."""
        # Ensure CLAUDE.md has memory section
        for role_name in ("orchestrator", "product", "developer", "reviewer"):
            claude_md = orch._dir / "workspaces" / role_name / "CLAUDE.md"
            text = claude_md.read_text()
            if "## 累积记忆" not in text:
                claude_md.write_text(text + "\n## 累积记忆\n")

        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
            if point == "post_review":
                return BrainDecision(decision="APPROVE", reason="ok")
            if point == "round_summary":
                return BrainDecision(
                    decision="PASS", reason="ok", details="generic summary",
                    memories={
                        "product": "product specific memory",
                        "developer": "developer specific memory",
                        "reviewer": "reviewer specific memory",
                    },
                )
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        orch.run_single_round()

        # Check each role got its specific memory
        product_md = (orch._dir / "workspaces" / "product" / "CLAUDE.md").read_text()
        assert "product specific memory" in product_md

        developer_md = (orch._dir / "workspaces" / "developer" / "CLAUDE.md").read_text()
        assert "developer specific memory" in developer_md

        reviewer_md = (orch._dir / "workspaces" / "reviewer" / "CLAUDE.md").read_text()
        assert "reviewer specific memory" in reviewer_md

        # Orchestrator gets generic summary (no key in memories dict)
        orch_md = (orch._dir / "workspaces" / "orchestrator" / "CLAUDE.md").read_text()
        assert "generic summary" in orch_md


class TestOrchestratorCodeDigest:
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_code_digest_generated_after_round(
        self, mock_stop, mock_start, mock_brain, mock_role, orch: Orchestrator
    ):
        """REQ-5: _update_code_digest should be called after each round."""
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

        with patch.object(orch, "_update_code_digest") as mock_digest:
            orch.run_single_round()
            mock_digest.assert_called_once()

    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_explore_includes_digest_context(
        self, mock_stop, mock_start, mock_brain, orch: Orchestrator
    ):
        """REQ-5: product:explore should include code-digest.md content in context."""
        # Create a code-digest.md file
        digest_path = orch._dir / "code-digest.md"
        digest_path.write_text("# Code Digest\nProject has auth module")

        # Patch RoleRunner.call to capture the prompt passed to it
        with patch.object(orch._runners["product"], "call") as mock_call:
            orch._call_role(
                "product:explore", 1,
                orch._dir / "rounds" / "001",
                ["test goal"],
            )
            mock_call.assert_called_once()
            prompt_arg = mock_call.call_args[0][0]
            assert "Project has auth module" in prompt_arg
            assert "code-digest.md" in prompt_arg


class TestUpdateCodeDigest:
    @patch("ai_loop.orchestrator.subprocess.run")
    def test_update_code_digest_subprocess_calls(self, mock_subprocess, orch: Orchestrator):
        """Verify subprocess calls for tree and diff in _update_code_digest."""
        mock_subprocess.return_value = MagicMock(stdout="file list", returncode=0)

        with patch.object(orch._brain, "generate_code_digest") as mock_gen:
            orch._update_code_digest(orch._dir / "rounds" / "001")

            # Should have called subprocess.run at least twice (find + git diff)
            assert mock_subprocess.call_count >= 2
            find_call = mock_subprocess.call_args_list[0]
            assert "find" in find_call[0][0]
            diff_call = mock_subprocess.call_args_list[1]
            assert "git" in diff_call[0][0]
            mock_gen.assert_called_once()

    @patch("ai_loop.orchestrator.subprocess.run")
    def test_update_code_digest_diff_fallback_on_first_commit(self, mock_subprocess, orch: Orchestrator):
        """When HEAD~1 doesn't exist, should fallback to git log -1 --stat."""
        call_count = {"n": 0}

        def side_effect(cmd, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if cmd[0] == "find":
                result.stdout = "file1.py\nfile2.py"
                result.returncode = 0
            elif cmd[1:3] == ["diff", "HEAD~1"]:
                result.stdout = ""
                result.returncode = 128  # git error
            elif cmd[1:3] == ["log", "-1"]:
                result.stdout = "abc1234 initial commit\n file1.py | 10 +\n"
                result.returncode = 0
            else:
                result.stdout = ""
                result.returncode = 0
            return result

        mock_subprocess.side_effect = side_effect

        with patch.object(orch._brain, "generate_code_digest") as mock_gen:
            orch._update_code_digest(orch._dir / "rounds" / "001")

            mock_gen.assert_called_once()
            # diff_output should contain git log fallback content
            diff_arg = mock_gen.call_args[1]["diff_output"]
            assert "initial commit" in diff_arg

    @patch("ai_loop.orchestrator.subprocess.run")
    def test_update_code_digest_exception_fallback(self, mock_subprocess, orch: Orchestrator):
        """When subprocess raises, should fallback to error message strings."""
        mock_subprocess.side_effect = OSError("command not found")

        with patch.object(orch._brain, "generate_code_digest") as mock_gen:
            orch._update_code_digest(orch._dir / "rounds" / "001")

            mock_gen.assert_called_once()
            tree_arg = mock_gen.call_args[1]["tree_output"]
            diff_arg = mock_gen.call_args[1]["diff_output"]
            assert "unable" in tree_arg.lower()
            assert "unable" in diff_arg.lower()


class TestInteractionCallback:
    def test_high_mode_appends_collaboration_prompt(self, ai_loop_dir: Path, sample_config: dict):
        """high 模式下 _call_role 应在 prompt 中追加人工协作指令。"""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        config_path = ai_loop_dir / "config.yaml"
        config_path.write_text(yaml.dump(sample_config))

        callback = MagicMock(return_value="user answer")
        orch = Orchestrator(ai_loop_dir, interaction_callback=callback)

        with patch.object(orch._runners["product"], "call") as mock_call:
            orch._call_role("product:explore", 1, ai_loop_dir / "rounds" / "001", ["goal"])
            mock_call.assert_called_once()
            prompt_arg = mock_call.call_args[0][0]
            assert "人工协作模式" in prompt_arg
            # interaction_callback should be passed through
            assert mock_call.call_args[1].get("interaction_callback") is callback

    def test_low_mode_no_collaboration_prompt(self, ai_loop_dir: Path, sample_config: dict):
        """low 模式下 _call_role 不应追加协作指令，也不传回调。"""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        config_path = ai_loop_dir / "config.yaml"
        config_path.write_text(yaml.dump(sample_config))

        callback = MagicMock()
        orch = Orchestrator(ai_loop_dir, interaction_callback=callback)

        with patch.object(orch._runners["product"], "call") as mock_call:
            orch._call_role("product:explore", 1, ai_loop_dir / "rounds" / "001", ["goal"])
            mock_call.assert_called_once()
            prompt_arg = mock_call.call_args[0][0]
            assert "人工协作模式" not in prompt_arg
            assert mock_call.call_args[1].get("interaction_callback") is None

    def test_ask_brain_no_longer_calls_callback(self, ai_loop_dir: Path, sample_config: dict):
        """_ask_brain 不应再有回调逻辑。"""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        config_path = ai_loop_dir / "config.yaml"
        config_path.write_text(yaml.dump(sample_config))

        callback = MagicMock()
        orch = Orchestrator(ai_loop_dir, interaction_callback=callback)

        with patch.object(orch._brain, "decide") as mock_decide:
            mock_decide.return_value = BrainDecision(decision="PROCEED", reason="ok")
            result = orch._ask_brain("post_requirement", round_dir=ai_loop_dir / "rounds" / "001")
            assert result.decision == "PROCEED"
            callback.assert_not_called()


class TestOrchestratorCliProject:
    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    def test_server_not_started_for_cli_project(
        self, mock_brain, mock_role, mock_digest, cli_orch: Orchestrator
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
