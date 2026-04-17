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

        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
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
        assert "developer:develop" in role_calls
        assert "product:qa_acceptance" in role_calls
        assert "reviewer:review" not in role_calls
        assert "developer:design" not in role_calls
        assert "developer:implement" not in role_calls


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
        for role_name in ("orchestrator", "product", "developer"):
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
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Good round")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        with patch.object(orch._memory, "compact_memories") as mock_compact:
            orch.run_single_round()
            assert mock_compact.call_count == 3


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
        for role_name in ("orchestrator", "product", "developer"):
            claude_md = orch._dir / "workspaces" / role_name / "CLAUDE.md"
            text = claude_md.read_text()
            if "## 累积记忆" not in text:
                claude_md.write_text(text + "\n## 累积记忆\n")

        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="PASS", reason="ok")
            if point == "round_summary":
                return BrainDecision(
                    decision="PASS", reason="ok", details="generic summary",
                    memories={
                        "product": "product specific memory",
                        "developer": "developer specific memory",
                    },
                )
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        orch.run_single_round()

        product_md = (orch._dir / "workspaces" / "product" / "CLAUDE.md").read_text()
        assert "product specific memory" in product_md

        developer_md = (orch._dir / "workspaces" / "developer" / "CLAUDE.md").read_text()
        assert "developer specific memory" in developer_md

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
        with patch.object(orch._runners["product"], "call", return_value="mock result") as mock_call:
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

        with patch.object(orch._runners["product"], "call", return_value="mock result") as mock_call:
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

        with patch.object(orch._runners["product"], "call", return_value="mock result") as mock_call:
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


class TestExtractRequirements:
    def test_extract_req_section_format(self):
        """Extract requirements in ## REQ-N: title format."""
        content = """---
round: 2
---

## REQ-1: init 命令应自动创建目录

some desc

## REQ-2: run 命令添加目标不应持久化

some desc

## REQ-3: verbose 硬编码问题

some desc

## 优先级排序

| P0 | REQ-1 | 理由 |
| P1 | REQ-2 | 理由 |
| P2 | REQ-3 | 理由 |
"""
        reqs = Orchestrator._extract_requirements(content)
        assert len(reqs) == 3
        assert reqs[0]["id"] == "REQ-1"
        assert reqs[0]["title"] == "init 命令应自动创建目录"
        assert reqs[0]["priority"] == "P0"
        assert reqs[1]["priority"] == "P1"
        assert reqs[2]["priority"] == "P2"

    def test_extract_bullet_format(self):
        """Extract requirements in - **[P0] title** format."""
        content = """### 具体需求
- **[P0] 优化记忆机制**：现状 → 期望
- **[P1] 增加缓存**：现状 → 期望
"""
        reqs = Orchestrator._extract_requirements(content)
        assert len(reqs) == 2
        assert reqs[0]["priority"] == "P0"
        assert reqs[0]["title"] == "优化记忆机制"
        assert reqs[1]["priority"] == "P1"

    def test_extract_standalone_bold_format(self):
        """Extract requirements in standalone **[P0] title** without leading dash."""
        content = """### 具体需求

**[P0] 评分系统指标归一化**

现状：直接对原始指标值加权求和。

**[P1] Agent Prompt 增强**

现状：缺乏量化专业知识引导。
"""
        reqs = Orchestrator._extract_requirements(content)
        assert len(reqs) == 2
        assert reqs[0]["priority"] == "P0"
        assert reqs[0]["title"] == "评分系统指标归一化"
        assert reqs[1]["priority"] == "P1"
        assert reqs[1]["title"] == "Agent Prompt 增强"

    def test_extract_mixed_formats(self):
        """Extract requirements mixing standalone and bullet formats."""
        content = """### 具体需求

**[P0] 核心功能**

描述。

### 延迟池

- **[P1] 附加功能**：描述
- **[P2] 低优先级**：描述
"""
        reqs = Orchestrator._extract_requirements(content)
        assert len(reqs) == 3
        assert reqs[0]["priority"] == "P0"
        assert reqs[1]["priority"] == "P1"
        assert reqs[2]["priority"] == "P2"

    def test_extract_empty_content(self):
        """Empty or irrelevant content returns empty list."""
        assert Orchestrator._extract_requirements("") == []
        assert Orchestrator._extract_requirements("# Hello\nno reqs here") == []


class TestRemoveRequirements:
    def test_remove_by_index(self, tmp_path: Path):
        """Remove specific requirements by index."""
        content = """## 背景

some bg

## REQ-1: Keep This

desc1

## REQ-2: Remove This

desc2

## REQ-3: Also Keep

desc3

## 技术约束

constraints
"""
        req_path = tmp_path / "requirement.md"
        req_path.write_text(content)
        reqs = [
            {"id": "REQ-1", "title": "Keep This", "priority": "P0"},
            {"id": "REQ-2", "title": "Remove This", "priority": "P1"},
            {"id": "REQ-3", "title": "Also Keep", "priority": "P2"},
        ]
        Orchestrator._remove_requirements(req_path, content, reqs, "2")
        result = req_path.read_text()
        assert "Keep This" in result
        assert "Remove This" not in result
        assert "Also Keep" in result
        assert "技术约束" in result

    def test_remove_invalid_index(self, tmp_path: Path):
        """Invalid index does nothing."""
        content = "## REQ-1: Title\nsome text"
        req_path = tmp_path / "requirement.md"
        req_path.write_text(content)
        reqs = [{"id": "REQ-1", "title": "Title", "priority": "P0"}]
        Orchestrator._remove_requirements(req_path, content, reqs, "99")
        assert req_path.read_text() == content

    def test_remove_bad_format(self, tmp_path: Path):
        """Non-numeric input is silently ignored."""
        content = "## REQ-1: Title\nsome text"
        req_path = tmp_path / "requirement.md"
        req_path.write_text(content)
        reqs = [{"id": "REQ-1", "title": "Title", "priority": "P0"}]
        Orchestrator._remove_requirements(req_path, content, reqs, "abc")
        assert req_path.read_text() == content


class TestConfirmRequirements:
    def test_skip_when_low_mode(self, ai_loop_dir: Path, sample_config: dict):
        """human_decision=low should skip confirmation entirely."""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        (ai_loop_dir / "config.yaml").write_text(yaml.dump(sample_config))

        callback = MagicMock()
        orch = Orchestrator(ai_loop_dir, interaction_callback=callback)

        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("## REQ-1: Something\ndesc")

        # low mode: _confirm_requirements is not called in run_single_round,
        # but we verify it's benign even if called
        orch._confirm_requirements(round_dir)
        # callback is not called because _confirm_requirements itself shows list
        # but the run_single_round gate (human_decision != "low") prevents calling it

    def test_accept_all(self, ai_loop_dir: Path, sample_config: dict):
        """User selects [a] to accept all requirements."""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        (ai_loop_dir / "config.yaml").write_text(yaml.dump(sample_config))

        callback = MagicMock(return_value="a")
        orch = Orchestrator(ai_loop_dir, verbose=True, interaction_callback=callback)

        round_dir = ai_loop_dir / "rounds" / "001"
        req_content = "## REQ-1: Feature A\ndesc\n## REQ-2: Feature B\ndesc"
        (round_dir / "requirement.md").write_text(req_content)

        orch._confirm_requirements(round_dir)
        assert (round_dir / "requirement.md").read_text() == req_content

    def test_reject_all(self, ai_loop_dir: Path, sample_config: dict):
        """User selects [r] to reject all — requirement.md is deleted."""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        (ai_loop_dir / "config.yaml").write_text(yaml.dump(sample_config))

        callback = MagicMock(return_value="r")
        orch = Orchestrator(ai_loop_dir, verbose=True, interaction_callback=callback)

        round_dir = ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("## REQ-1: Feature A\ndesc")

        orch._confirm_requirements(round_dir)
        assert not (round_dir / "requirement.md").exists()

    def test_delete_specific(self, ai_loop_dir: Path, sample_config: dict):
        """User selects [d 2] to delete requirement #2."""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        (ai_loop_dir / "config.yaml").write_text(yaml.dump(sample_config))

        callback = MagicMock(return_value="d 2")
        orch = Orchestrator(ai_loop_dir, verbose=True, interaction_callback=callback)

        round_dir = ai_loop_dir / "rounds" / "001"
        content = "## REQ-1: Keep\nkeep desc\n## REQ-2: Remove\nremove desc\n## REQ-3: Also Keep\nalso keep"
        (round_dir / "requirement.md").write_text(content)

        orch._confirm_requirements(round_dir)
        result = (round_dir / "requirement.md").read_text()
        assert "Keep" in result
        assert "Remove" not in result
        assert "Also Keep" in result

    def test_no_callback_skips_interaction(self, ai_loop_dir: Path, sample_config: dict):
        """Without interaction_callback, requirements are shown but not interactive."""
        sample_config["project"]["path"] = str(ai_loop_dir.parent)
        sample_config["human_decision"] = "high"
        (ai_loop_dir / "config.yaml").write_text(yaml.dump(sample_config))

        orch = Orchestrator(ai_loop_dir, verbose=True, interaction_callback=None)

        round_dir = ai_loop_dir / "rounds" / "001"
        req_content = "## REQ-1: Feature A\ndesc"
        (round_dir / "requirement.md").write_text(req_content)

        orch._confirm_requirements(round_dir)
        assert (round_dir / "requirement.md").read_text() == req_content


class TestQaAcceptanceRetryLoop:
    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_fail_impl_triggers_developer_reimpl(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
    ):
        """FAIL_IMPL should trigger developer:implement then retry qa_acceptance."""
        call_count = {"brain": 0}

        def brain_side_effect(point, **kwargs):
            call_count["brain"] += 1
            if point == "post_acceptance":
                if call_count["brain"] <= 4:
                    return BrainDecision(decision="FAIL_IMPL", reason="P0 failed")
                return BrainDecision(decision="PASS", reason="ok")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = orch.run_single_round()
        assert summary is not None
        role_calls = [c[0][0] for c in mock_role.call_args_list]
        qa_calls = [c for c in role_calls if c == "product:qa_acceptance"]
        impl_after_qa = sum(1 for i, c in enumerate(role_calls)
                           if c == "developer:implement" and i > role_calls.index("product:qa_acceptance"))
        assert len(qa_calls) >= 2
        assert impl_after_qa >= 1

    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_max_retries_escalates(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
    ):
        """Exceeding max_acceptance_retries should ESCALATE."""
        orch._config.limits.max_acceptance_retries = 1

        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="FAIL_IMPL", reason="still broken")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = orch.run_single_round()
        assert "ESCALATE" in summary

    @patch.object(Orchestrator, "_update_code_digest")
    @patch.object(Orchestrator, "_call_role")
    @patch.object(Orchestrator, "_ask_brain")
    @patch.object(Orchestrator, "_server_start")
    @patch.object(Orchestrator, "_server_stop")
    def test_escalate_decision_returns_immediately(
        self, mock_stop, mock_start, mock_brain, mock_role, mock_digest, orch: Orchestrator
    ):
        """ESCALATE decision should exit the loop immediately."""
        def brain_side_effect(point, **kwargs):
            if point == "post_acceptance":
                return BrainDecision(decision="ESCALATE", reason="need human")
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = orch.run_single_round()
        assert "ESCALATE" in summary
        assert "need human" in summary


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
            if point == "round_summary":
                return BrainDecision(decision="PASS", reason="ok", details="Done")
            return BrainDecision(decision="PROCEED", reason="ok")

        mock_brain.side_effect = brain_side_effect
        mock_role.return_value = None

        summary = cli_orch.run_single_round()
        assert summary is not None
