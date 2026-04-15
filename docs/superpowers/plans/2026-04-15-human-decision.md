# Human Decision Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RoleRunner's one-shot `claude -p` execution with cc-connect style bidirectional stream-json communication, enabling roles to self-pause and ask the user questions in high human_decision mode.

**Architecture:** RoleRunner becomes a long-lived subprocess manager using `--input-format stream-json --output-format stream-json`. In high mode, role prompts get a "human collaboration" instruction appended, and a `needs_input` marker in the result triggers a callback loop that sends the user's answer back via stdin. Config, Orchestrator, and CLI are updated to plumb the `interaction_callback` through.

**Tech Stack:** Python 3.10+, subprocess (Popen with pipes), JSON (NDJSON protocol), click (CLI), pytest (testing)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `ai_loop/roles/base.py` | **Rewrite** | Stream-json RoleRunner: Popen lifecycle, NDJSON read loop, permission auto-approve, needs_input detection |
| `ai_loop/config.py` | **Modify** | Remove `HUMAN_DECISION_POINTS`, keep `HUMAN_DECISION_LEVELS` and `human_decision` field |
| `ai_loop/orchestrator.py` | **Modify** | Replace `human_decision_callback` with `interaction_callback`, pass it to `_call_role`, inject collaboration prompt in high mode, clean up `_ask_brain` |
| `ai_loop/cli.py` | **Modify** | Replace old decision-point callback with simple `_interaction_callback(question) -> answer`, clean up old code |
| `tests/test_roles.py` | **Modify** | Rewrite RoleRunner tests for stream-json protocol |
| `tests/test_orchestrator.py` | **Modify** | Replace `TestHumanDecisionCallback` with new interaction_callback tests |
| `tests/test_config.py` | **Modify** | Remove `HUMAN_DECISION_POINTS` test, keep the rest |

---

### Task 1: Clean up config.py — remove HUMAN_DECISION_POINTS

**Files:**
- Modify: `ai_loop/config.py:43-48`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Remove HUMAN_DECISION_POINTS from config.py**

In `ai_loop/config.py`, delete lines 45-48 (the `HUMAN_DECISION_POINTS` dict). Keep `HUMAN_DECISION_LEVELS` on line 43.

Before:
```python
HUMAN_DECISION_LEVELS = ("low", "high")

# high 模式下需要人工确认的决策点
HUMAN_DECISION_POINTS = {
    "high": ["post_requirement", "post_design"],
}
```

After:
```python
HUMAN_DECISION_LEVELS = ("low", "high")
```

- [ ] **Step 2: Update test_config.py — remove HUMAN_DECISION_POINTS tests**

In `tests/test_config.py`, remove the import of `HUMAN_DECISION_POINTS` and delete the two tests that reference it (`test_high_decision_points_include_requirement_and_design` and `test_low_has_no_decision_points`). Keep all other `TestHumanDecisionConfig` tests.

Change import line:
```python
from ai_loop.config import AiLoopConfig, load_config
```

Delete these two test methods from `TestHumanDecisionConfig`:
```python
    def test_high_decision_points_include_requirement_and_design(self):
        ...

    def test_low_has_no_decision_points(self):
        ...
```

- [ ] **Step 3: Run tests to verify**

Run: `python -m pytest tests/test_config.py -v`
Expected: All remaining tests PASS (9 tests), no import errors.

- [ ] **Step 4: Commit**

```bash
git add ai_loop/config.py tests/test_config.py
git commit -m "refactor: remove HUMAN_DECISION_POINTS from config"
```

---

### Task 2: Rewrite RoleRunner to stream-json bidirectional communication

**Files:**
- Rewrite: `ai_loop/roles/base.py:37-167`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests for new RoleRunner**

Replace the two existing `TestRoleRunner` tests in `tests/test_roles.py` with these new tests. Keep `TestParseFrontmatter` and all role prompt tests unchanged.

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_roles.py::TestRoleRunner -v`
Expected: FAIL — current RoleRunner doesn't use Popen with stream-json.

- [ ] **Step 3: Implement new RoleRunner**

Replace the `RoleRunner` class in `ai_loop/roles/base.py` (lines 37-167). Keep `parse_frontmatter` and the ANSI color helpers unchanged.

```python
class RoleRunner:
    def __init__(self, role_name: str, allowed_tools: list[str]):
        self.role_name = role_name
        self.allowed_tools = allowed_tools

    def call(self, prompt: str, cwd: str, timeout: int = 600,
             verbose: bool = False,
             interaction_callback=None) -> str:
        cmd = [
            "claude",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--permission-prompt-tool", "stdio",
        ]
        if self.allowed_tools:
            cmd += ["--allowedTools", ",".join(self.allowed_tools)]
        if verbose:
            cmd.append("--verbose")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )

        # Send initial prompt
        self._send_message(proc, prompt)

        final_result = ""
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "control_request":
                    self._handle_control_request(proc, event)
                elif etype == "result":
                    result_text = event.get("result", "")
                    if interaction_callback and self._has_needs_input(result_text):
                        question = self._extract_question(result_text)
                        answer = interaction_callback(question)
                        self._send_message(proc, answer)
                        # Continue reading for next result
                    else:
                        final_result = result_text
                        break
                elif verbose:
                    self._render_event(event)

            proc.stdin.close()
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError(
                f"Claude CLI 调用超时 (role={self.role_name}, "
                f"timeout={timeout}s)"
            )

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(
                f"Claude CLI 调用失败 (role={self.role_name}, "
                f"exit={proc.returncode}): {stderr[:500]}"
            )
        return final_result

    def _send_message(self, proc, content: str) -> None:
        msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": content},
        })
        proc.stdin.write(msg + "\n")
        proc.stdin.flush()

    def _handle_control_request(self, proc, event: dict) -> None:
        request_id = event.get("request_id", "")
        request = event.get("request", {})
        input_data = request.get("input", {})
        response = json.dumps({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": {
                    "behavior": "allow",
                    "updatedInput": input_data,
                },
            },
        })
        proc.stdin.write(response + "\n")
        proc.stdin.flush()

    @staticmethod
    def _has_needs_input(text: str) -> bool:
        return '{"needs_input": true}' in text or '{"needs_input":true}' in text

    @staticmethod
    def _extract_question(text: str) -> str:
        for marker in ('{"needs_input": true}', '{"needs_input":true}'):
            if marker in text:
                return text[:text.rfind(marker)].strip()
        return text.strip()

    def _render_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    desc = inp.get("description", inp.get("command", inp.get("pattern", "")))
                    if isinstance(desc, str) and len(desc) > 120:
                        desc = desc[:120] + "..."
                    print(f"  {_c('cyan', '⚡')} {_c('bold', name)} {_c('dim', str(desc))}", flush=True)
                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        lines = text.strip().split("\n")
                        for ln in lines[:3]:
                            print(f"  {_c('dim', '│')} {ln}", flush=True)
                        if len(lines) > 3:
                            print(f"  {_c('dim', '│ ... (' + str(len(lines) - 3) + ' more lines)')}", flush=True)

        elif etype == "result":
            cost = event.get("total_cost_usd", 0)
            turns = event.get("num_turns", 0)
            duration = event.get("duration_ms", 0)
            print(
                f"  {_c('green', '✓')} "
                f"{_c('dim', f'{turns} turns, {duration/1000:.1f}s, ${cost:.4f}')}",
                flush=True,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_roles.py -v`
Expected: All tests PASS (including TestParseFrontmatter and all role prompt tests).

- [ ] **Step 5: Commit**

```bash
git add ai_loop/roles/base.py tests/test_roles.py
git commit -m "feat: rewrite RoleRunner to stream-json bidirectional communication"
```

---

### Task 3: Update Orchestrator — interaction_callback and collaboration prompt

**Files:**
- Modify: `ai_loop/orchestrator.py:1-10,26-36,179-208`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for new interaction_callback behavior**

In `tests/test_orchestrator.py`, replace the entire `TestHumanDecisionCallback` class (lines 296-410) with:

```python
HUMAN_COLLABORATION_INSTRUCTION = "## 人工协作模式"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py::TestInteractionCallback -v`
Expected: FAIL — current Orchestrator uses `human_decision_callback` not `interaction_callback`.

- [ ] **Step 3: Implement Orchestrator changes**

In `ai_loop/orchestrator.py`:

**3a.** Fix import — remove `HUMAN_DECISION_POINTS`:

Change line 6 from:
```python
from ai_loop.config import AiLoopConfig, HUMAN_DECISION_POINTS, load_config
```
to:
```python
from ai_loop.config import AiLoopConfig, load_config
```

**3b.** Add the collaboration instruction constant after the imports (after line 16):

```python
HUMAN_COLLABORATION_INSTRUCTION = """

## 人工协作模式

你在协作模式下工作。当遇到以下情况时，暂停并向调度者提问：
- 需求存在歧义或多种理解
- 有 2 个以上可行方案且各有取舍
- 涉及影响范围大的架构决策
- 你不确定产品意图或优先级

提问规则：
- 一次只问一个问题
- 优先提供 2-3 个选项 + 你的推荐 + 理由
- 开放式问题也可以，但尽量给出方向性建议
- 信息足够后立即继续执行，不要过度确认

提问时在输出末尾附加标记：
{"needs_input": true}

收到回答后继续工作。不再有疑问时正常完成任务，不附加标记。
"""
```

**3c.** Change constructor — rename `human_decision_callback` to `interaction_callback`:

```python
    def __init__(self, ai_loop_dir: Path, verbose: bool = False,
                 interaction_callback: Optional[Callable] = None):
        ...
        self._interaction_callback = interaction_callback
```

**3d.** Update `_call_role` — append collaboration prompt and pass callback in high mode:

```python
    def _call_role(self, role_phase: str, rnd: int, round_dir: Path, goals: list[str]) -> None:
        role_name, phase = role_phase.split(":", 1)
        role_map = {
            "product": self._product,
            "developer": self._developer,
            "reviewer": self._reviewer,
        }
        role = role_map[role_name]
        self._log(f"\n\033[1m▶ [{role_name.upper()}] {phase}\033[0m")
        context = self._context_collector.collect(role_phase, round_dir)
        if role_phase == "product:explore":
            digest_path = self._dir / "code-digest.md"
            if digest_path.exists():
                digest = digest_path.read_text()
                context += f"\n\n## code-digest.md\n\n{digest}"
        prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)

        if self._config.human_decision == "high":
            prompt += HUMAN_COLLABORATION_INSTRUCTION
            callback = self._interaction_callback
        else:
            callback = None

        workspace = str(self._dir / "workspaces" / role_name)
        self._runners[role_name].call(
            prompt, cwd=workspace, verbose=self._verbose,
            interaction_callback=callback,
        )
```

**3e.** Clean up `_ask_brain` — remove the callback logic:

```python
    def _ask_brain(self, decision_point: str, round_dir: Path) -> BrainDecision:
        self._log(f"\n\033[2m🧠 Brain: {decision_point}\033[0m")
        decision = self._brain.decide(decision_point, round_dir=round_dir)
        self._log(f"\033[2m   → {decision.decision}: {decision.reason}\033[0m")
        return decision
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: All tests PASS. The old `TestHumanDecisionCallback` tests are replaced by `TestInteractionCallback`.

- [ ] **Step 5: Commit**

```bash
git add ai_loop/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator uses interaction_callback with collaboration prompt"
```

---

### Task 4: Update CLI — simple interaction callback and cleanup

**Files:**
- Modify: `ai_loop/cli.py:1-87,233-263`

- [ ] **Step 1: Rewrite cli.py**

Replace the imports and the old callback code (lines 1-87) with:

```python
# ai_loop/cli.py
from importlib import resources
from pathlib import Path
import shutil

import click
import yaml

from ai_loop.config import HUMAN_DECISION_LEVELS
from ai_loop.detect import detect_project_config
from ai_loop.orchestrator import Orchestrator
from ai_loop.state import LoopState, save_state
import ai_loop.templates


def _interaction_callback(question_text: str) -> str:
    """展示角色的提问并收集用户回答。"""
    click.echo(f"\n{'─' * 40}")
    click.echo(f"  🤚 需要你的输入")
    click.echo(f"{'─' * 40}")
    click.echo(question_text)
    click.echo()
    return click.prompt("你的回答")
```

Then update the `run` command (lines 233-263 area). Replace from `@main.command()` for `run` through the Orchestrator creation:

```python
@main.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
@click.option("--goal", multiple=True, help="Additional goals for this run")
@click.option("-v", "--verbose", is_flag=True, default=True, help="Show Claude Code processing details (default: on)")
@click.option("-q", "--quiet", is_flag=True, help="Hide Claude Code processing details")
@click.option("--human-decision", type=click.Choice(list(HUMAN_DECISION_LEVELS)),
              default=None, help="Human decision level: low (auto) / high (roles can pause to ask)")
def run(project_path, goal, verbose, quiet, human_decision):
    """Run the AI Loop iteration cycle."""
    project = Path(project_path).resolve()
    ai_dir = project / ".ai-loop"

    if not ai_dir.exists():
        raise click.ClickException(
            f"未找到 .ai-loop 目录，请先运行: ai-loop init {project_path}"
        )

    show_details = verbose and not quiet

    callback = _interaction_callback
    orch = Orchestrator(ai_dir, verbose=show_details, interaction_callback=callback)

    # CLI 参数覆盖配置（仅运行时，不持久化）
    if human_decision:
        orch._config.human_decision = human_decision

    # Inject additional goals into runtime only (not persisted to config)
    for g in goal:
        orch.add_goal(g)
```

The rest of the `run` function (the `while True` loop) stays unchanged.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS. No import errors from removed symbols.

- [ ] **Step 3: Commit**

```bash
git add ai_loop/cli.py
git commit -m "feat: CLI uses simple interaction_callback, removes old decision-point UI"
```

---

### Task 5: Fix existing tests that depend on old RoleRunner signature

**Files:**
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_roles.py`

- [ ] **Step 1: Update orchestrator tests that mock RoleRunner.call**

The `test_explore_includes_digest_context` test in `TestOrchestratorCodeDigest` calls `orch._call_role()` and mocks `RoleRunner.call`. Since `_call_role` now passes `interaction_callback` as a keyword argument, verify the mock still works. The mock's `call_args[0][0]` should still capture the prompt.

Run: `python -m pytest tests/test_orchestrator.py::TestOrchestratorCodeDigest::test_explore_includes_digest_context -v`

If it fails because `call()` receives unexpected kwargs, update the mock:
```python
with patch.object(orch._runners["product"], "call") as mock_call:
    orch._call_role(
        "product:explore", 1,
        orch._dir / "rounds" / "001",
        ["test goal"],
    )
    mock_call.assert_called_once()
    prompt_arg = mock_call.call_args[0][0]
```

This should already work because MagicMock accepts any arguments. Verify.

- [ ] **Step 2: Run the full test suite to find any remaining failures**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Fix any failures found**

Address each failure by updating the test to match the new RoleRunner/Orchestrator interface. Common fixes:
- Tests mocking `subprocess.run` need to mock `subprocess.Popen` instead
- Tests checking for `-p` in cmd need to check for `--input-format` instead
- Tests referencing `human_decision_callback` need to reference `interaction_callback`

- [ ] **Step 4: Run tests again to confirm all pass**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "fix: update tests for new RoleRunner and Orchestrator interface"
```

---

### Task 6: Final verification — full test suite and integration check

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS, 0 failures, 0 errors.

- [ ] **Step 2: Verify no stale imports**

Run: `python -c "from ai_loop.config import HUMAN_DECISION_LEVELS; from ai_loop.orchestrator import Orchestrator, HUMAN_COLLABORATION_INSTRUCTION; from ai_loop.roles.base import RoleRunner; print('All imports OK')"`
Expected: "All imports OK"

Run: `python -c "from ai_loop.config import HUMAN_DECISION_POINTS" 2>&1`
Expected: ImportError (confirming it's removed)

- [ ] **Step 3: Verify CLI --human-decision option exists**

Run: `python -m ai_loop.cli run --help`
Expected: Output includes `--human-decision [low|high]`

- [ ] **Step 4: Commit any remaining fixes**

If any fixes were needed:
```bash
git add -A
git commit -m "fix: final cleanup for human decision feature"
```
