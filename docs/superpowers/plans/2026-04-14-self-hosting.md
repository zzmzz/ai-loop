# AI Loop Self-Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let ai-loop dogfood itself by supporting CLI project verification and injecting inter-phase context automatically.

**Architecture:** Two orthogonal changes: (1) a `VerificationConfig` that replaces hard-coded Playwright assumptions, making `server` and `browser` optional; (2) a `ContextCollector` that reads prior-phase artifacts and injects them into each role's prompt. A dogfooding `.ai-loop/config.yaml` wires it all together.

**Tech Stack:** Python 3.12, dataclasses, PyYAML, Click, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `ai_loop/config.py` | Modify | Add `VerificationConfig`; make `ServerConfig`/`BrowserConfig` optional; backward-compat `load_config` |
| `ai_loop/context.py` | Create | `ContextCollector` with `PHASE_DEPS` and `collect()` |
| `ai_loop/roles/product.py` | Modify | Accept `VerificationConfig`; branch prompts by type |
| `ai_loop/roles/developer.py` | Modify | Add `context` parameter to `build_prompt` |
| `ai_loop/roles/reviewer.py` | Modify | Add `context` parameter to `build_prompt` |
| `ai_loop/orchestrator.py` | Modify | Integrate `ContextCollector`; conditional server; pass verification to `ProductRole` |
| `ai_loop/cli.py` | Modify | Make `--start-command`/`--health-url`/`--base-url` optional for CLI projects; add `--type` flag |
| `.ai-loop/config.yaml` | Create | Dogfooding config for ai-loop itself |
| `tests/conftest.py` | Modify | Add `cli_sample_config` and `cli_ai_loop_dir` fixtures |
| `tests/test_config.py` | Modify | Tests for new config parsing, backward compat, optional server |
| `tests/test_context.py` | Create | Tests for `ContextCollector` |
| `tests/test_roles.py` | Modify | Tests for new `ProductRole` init, CLI prompts, context param |
| `tests/test_orchestrator.py` | Modify | Tests for server-skip and context injection |

---

### Task 1: Add `VerificationConfig` and make `ServerConfig`/`BrowserConfig` optional

**Files:**
- Modify: `ai_loop/config.py`
- Modify: `tests/test_config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing test — parse config with `verification` field (no `browser`/`server`)**

Add to `tests/test_config.py`:

```python
def test_loads_cli_verification_config(self, tmp_path: Path):
    config = {
        "project": {"name": "my-cli", "path": "/tmp/cli", "description": "A CLI tool"},
        "goals": ["Add feature"],
        "verification": {
            "type": "cli",
            "test_command": "pytest tests/ -v",
            "run_examples": ["my-cli --help"],
        },
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))

    cfg = load_config(config_file)

    assert cfg.verification.type == "cli"
    assert cfg.verification.test_command == "pytest tests/ -v"
    assert cfg.verification.run_examples == ["my-cli --help"]
    assert cfg.verification.base_url == ""
    assert cfg.server is None
    assert cfg.browser is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py::TestLoadConfig::test_loads_cli_verification_config -v`
Expected: FAIL — `VerificationConfig` does not exist yet.

- [ ] **Step 3: Write failing test — backward compat (old config with `browser` but no `verification`)**

Add to `tests/test_config.py`:

```python
def test_backward_compat_browser_becomes_web_verification(self, tmp_path: Path, sample_config: dict):
    # sample_config has browser.base_url but no verification
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(sample_config))

    cfg = load_config(config_file)

    assert cfg.verification.type == "web"
    assert cfg.verification.base_url == "http://localhost:3000"
    assert cfg.server is not None
    assert cfg.server.start_command == "npm start"
```

- [ ] **Step 4: Write failing test — missing both `verification` and `browser` raises error**

Add to `tests/test_config.py`:

```python
def test_missing_verification_and_browser_raises(self, tmp_path: Path):
    config = {
        "project": {"name": "x", "path": "/tmp/x"},
        "goals": [],
        "server": {"start_command": "npm start", "health_url": "http://localhost:3000"},
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(config))

    with pytest.raises(ValueError, match="verification"):
        load_config(config_file)
```

- [ ] **Step 5: Implement `VerificationConfig` and update `load_config`**

In `ai_loop/config.py`, add after `LimitsConfig`:

```python
@dataclass
class VerificationConfig:
    type: str                        # "web" | "cli" | "library"
    base_url: str = ""               # web only
    test_command: str = ""           # cli/library
    run_examples: list[str] = field(default_factory=list)  # cli
```

Change `AiLoopConfig` to:

```python
@dataclass
class AiLoopConfig:
    project: ProjectConfig
    goals: list[str]
    verification: VerificationConfig
    server: ServerConfig | None = None
    browser: BrowserConfig | None = None
    limits: LimitsConfig = field(default_factory=LimitsConfig)
```

Replace the body of `load_config` (after loading `proj`) with:

```python
def load_config(path: Path) -> AiLoopConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    proj = raw.get("project", {})
    _require(proj, "name", "path", context="project")

    # Parse server (optional)
    srv_raw = raw.get("server")
    server = None
    if srv_raw:
        _require(srv_raw, "start_command", "health_url", context="server")
        server = ServerConfig(
            start_command=srv_raw["start_command"],
            health_url=srv_raw["health_url"],
            start_cwd=srv_raw.get("start_cwd", "."),
            health_timeout=srv_raw.get("health_timeout", 30),
            stop_signal=srv_raw.get("stop_signal", "SIGTERM"),
        )

    # Parse verification (new) or fallback to browser (backward compat)
    ver_raw = raw.get("verification")
    brw_raw = raw.get("browser")
    browser = None

    if ver_raw:
        verification = VerificationConfig(
            type=ver_raw["type"],
            base_url=ver_raw.get("base_url", ""),
            test_command=ver_raw.get("test_command", ""),
            run_examples=ver_raw.get("run_examples", []),
        )
    elif brw_raw and brw_raw.get("base_url"):
        browser = BrowserConfig(base_url=brw_raw["base_url"])
        verification = VerificationConfig(type="web", base_url=brw_raw["base_url"])
    else:
        raise ValueError("Missing required config: either 'verification' or 'browser.base_url' must be provided")

    lim = raw.get("limits", {})

    return AiLoopConfig(
        project=ProjectConfig(
            name=proj["name"],
            path=proj["path"],
            description=proj.get("description", ""),
        ),
        goals=raw.get("goals", []),
        verification=verification,
        server=server,
        browser=browser,
        limits=LimitsConfig(
            max_review_retries=lim.get("max_review_retries", 3),
            max_acceptance_retries=lim.get("max_acceptance_retries", 2),
        ),
    )
```

- [ ] **Step 6: Update `sample_config` fixture for backward compat**

In `tests/conftest.py`, the existing `sample_config` fixture stays the same (it uses `browser`/`server`, testing backward compat path). Add a new fixture:

```python
@pytest.fixture
def cli_sample_config() -> dict:
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
```

- [ ] **Step 7: Run all config tests**

Run: `python -m pytest tests/test_config.py -v`
Expected: All pass, including the 3 new tests and the original 4.

- [ ] **Step 8: Commit**

```bash
git add ai_loop/config.py tests/test_config.py tests/conftest.py
git commit -m "feat: add VerificationConfig, make server/browser optional with backward compat"
```

---

### Task 2: Create `ContextCollector`

**Files:**
- Create: `ai_loop/context.py`
- Create: `tests/test_context.py`

- [ ] **Step 1: Write failing test — collect returns formatted context for known phase**

Create `tests/test_context.py`:

```python
from pathlib import Path
from ai_loop.context import ContextCollector


class TestContextCollector:
    def test_collect_returns_content_for_known_deps(self, tmp_path: Path):
        (tmp_path / "requirement.md").write_text("# Requirement\nFix the login bug")

        collector = ContextCollector()
        result = collector.collect("developer:design", tmp_path)

        assert "requirement.md" in result
        assert "Fix the login bug" in result
        assert "---" in result  # separator present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_context.py::TestContextCollector::test_collect_returns_content_for_known_deps -v`
Expected: FAIL — `ai_loop.context` does not exist.

- [ ] **Step 3: Write failing test — collect skips missing files**

Add to `tests/test_context.py`:

```python
    def test_collect_skips_missing_files(self, tmp_path: Path):
        # developer:implement depends on design.md and clarification.md
        (tmp_path / "design.md").write_text("# Design\nThe plan")
        # clarification.md does NOT exist

        collector = ContextCollector()
        result = collector.collect("developer:implement", tmp_path)

        assert "design.md" in result
        assert "The plan" in result
        assert "clarification.md" not in result
```

- [ ] **Step 4: Write failing test — collect returns empty string for phase with no deps**

Add to `tests/test_context.py`:

```python
    def test_collect_returns_empty_for_no_deps(self, tmp_path: Path):
        collector = ContextCollector()
        result = collector.collect("product:explore", tmp_path)

        assert result == ""
```

- [ ] **Step 5: Write failing test — collect returns empty string for unknown phase**

Add to `tests/test_context.py`:

```python
    def test_collect_returns_empty_for_unknown_phase(self, tmp_path: Path):
        collector = ContextCollector()
        result = collector.collect("unknown:phase", tmp_path)

        assert result == ""
```

- [ ] **Step 6: Write failing test — collect includes multiple deps**

Add to `tests/test_context.py`:

```python
    def test_collect_includes_multiple_deps(self, tmp_path: Path):
        (tmp_path / "requirement.md").write_text("req content")
        (tmp_path / "design.md").write_text("design content")

        collector = ContextCollector()
        result = collector.collect("reviewer:review", tmp_path)

        assert "requirement.md" in result
        assert "req content" in result
        assert "design.md" in result
        assert "design content" in result
```

- [ ] **Step 7: Implement `ContextCollector`**

Create `ai_loop/context.py`:

```python
from pathlib import Path


class ContextCollector:
    """Collects prior-phase artifacts and formats them for prompt injection."""

    PHASE_DEPS = {
        "product:explore": [],
        "developer:design": ["requirement.md"],
        "product:clarify": ["design.md"],
        "developer:implement": ["design.md", "clarification.md"],
        "developer:verify": ["requirement.md"],
        "reviewer:review": ["requirement.md", "design.md"],
        "product:acceptance": ["requirement.md", "dev-log.md"],
        "developer:fix_review": ["review.md"],
    }

    def collect(self, role_phase: str, round_dir: Path) -> str:
        """Read dependency files and return formatted context text.

        Returns empty string if no dependencies or no files found.
        """
        deps = self.PHASE_DEPS.get(role_phase, [])
        sections = []
        for fname in deps:
            fpath = round_dir / fname
            if fpath.exists():
                content = fpath.read_text()
                sections.append(f"## {fname}\n\n{content}")
        if not sections:
            return ""
        return "\n---以下是前序阶段的关键产出，供你参考---\n\n" + "\n\n".join(sections)
```

- [ ] **Step 8: Run all context tests**

Run: `python -m pytest tests/test_context.py -v`
Expected: All 5 tests pass.

- [ ] **Step 9: Commit**

```bash
git add ai_loop/context.py tests/test_context.py
git commit -m "feat: add ContextCollector for inter-phase context injection"
```

---

### Task 3: Update `ProductRole` to accept `VerificationConfig` and branch prompts

**Files:**
- Modify: `ai_loop/roles/product.py`
- Modify: `tests/test_roles.py`

- [ ] **Step 1: Write failing test — ProductRole with CLI verification, explore prompt**

Add to `tests/test_roles.py`:

```python
from ai_loop.config import VerificationConfig


class TestProductRoleCli:
    def test_explore_prompt_cli_uses_run_examples(self):
        verification = VerificationConfig(
            type="cli",
            test_command="pytest tests/ -v",
            run_examples=["my-cli --help", "my-cli init /tmp/test"],
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Add feature"])

        assert "my-cli --help" in prompt
        assert "pytest tests/ -v" in prompt
        assert "Playwright" not in prompt
        assert "requirement.md" in prompt

    def test_acceptance_prompt_cli_uses_test_command(self):
        verification = VerificationConfig(
            type="cli",
            test_command="pytest tests/ -v",
            run_examples=["my-cli --help"],
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Add feature"])

        assert "pytest tests/ -v" in prompt
        assert "my-cli --help" in prompt
        assert "Playwright" not in prompt
        assert "PASS" in prompt and "FAIL" in prompt
```

- [ ] **Step 2: Write failing test — ProductRole with web verification preserves existing behavior**

Add to `tests/test_roles.py`:

```python
class TestProductRoleWeb:
    def test_explore_prompt_web_uses_playwright(self):
        verification = VerificationConfig(
            type="web",
            base_url="http://localhost:3000",
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Fix login"])

        assert "http://localhost:3000" in prompt
        assert "Playwright" in prompt
        assert "requirement.md" in prompt

    def test_acceptance_prompt_web_uses_playwright(self):
        verification = VerificationConfig(
            type="web",
            base_url="http://localhost:3000",
        )
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Fix login"])

        assert "http://localhost:3000" in prompt
        assert "Playwright" in prompt
        assert "PASS" in prompt and "FAIL" in prompt
```

- [ ] **Step 3: Write failing test — ProductRole context parameter is appended**

Add to `tests/test_roles.py`:

```python
    def test_context_appended_to_prompt(self):
        verification = VerificationConfig(type="cli", test_command="pytest")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt(
            "explore", round_num=1, round_dir="/r/001",
            goals=["Add feature"], context="## Extra context\nSome info",
        )

        assert "## Extra context" in prompt
        assert "Some info" in prompt
```

- [ ] **Step 4: Run tests to confirm they fail**

Run: `python -m pytest tests/test_roles.py::TestProductRoleCli tests/test_roles.py::TestProductRoleWeb -v`
Expected: FAIL — `ProductRole` still expects `base_url: str`.

- [ ] **Step 5: Implement updated `ProductRole`**

Replace `ai_loop/roles/product.py` entirely:

```python
from ai_loop.config import VerificationConfig


class ProductRole:
    def __init__(self, verification: VerificationConfig):
        self.verification = verification

    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
            "explore": self._explore_prompt,
            "clarify": self._clarify_prompt,
            "acceptance": self._acceptance_prompt,
        }
        builder = builders.get(phase)
        if builder is None:
            raise ValueError(f"Unknown product phase: {phase}")
        prompt = builder(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt

    def _explore_prompt(self, round_num, round_dir, goals_text):
        if self.verification.type == "web":
            return self._explore_prompt_web(round_num, round_dir, goals_text)
        return self._explore_prompt_cli(round_num, round_dir, goals_text)

    def _explore_prompt_web(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。你的任务是体验当前产品并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读项目代码，理解当前功能和架构
2. 编写 Playwright Python 脚本访问 {self.verification.base_url}，像真实用户一样走完主要流程
3. 截图保存到当前工作区的 notes/ 目录
4. 结合代码理解和实际体验，输出需求文档

输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

需求要具体可执行，避免模糊描述。每条需求说清楚"现状是什么"和"期望是什么"。"""

    def _explore_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        return f"""你是产品经理。你的任务是体验当前 CLI 工具并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读项目代码，理解当前功能和架构
2. 运行以下示例命令，像真实用户一样体验 CLI 行为：
{examples}
3. 运行测试命令了解现有测试覆盖：`{self.verification.test_command}`
4. 结合代码理解和实际体验，输出需求文档

输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

需求要具体可执行，避免模糊描述。每条需求说清楚"现状是什么"和"期望是什么"。"""

    def _clarify_prompt(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。开发者在设计文档中提出了待确认问题，请你回答。

请阅读：{round_dir}/design.md，找到"待确认问题"章节。

基于你对产品和用户的理解，逐一回答每个问题。
如果某个问题涉及产品方向性决策且你不确定，标注为 NEEDS_HUMAN。

输出文件：{round_dir}/clarification.md

文件头部：
---
round: {round_num}
role: product
phase: clarification
result: null
timestamp: （当前时间 ISO 格式）
---"""

    def _acceptance_prompt(self, round_num, round_dir, goals_text):
        if self.verification.type == "web":
            return self._acceptance_prompt_web(round_num, round_dir, goals_text)
        return self._acceptance_prompt_cli(round_num, round_dir, goals_text)

    def _acceptance_prompt_web(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。你的任务是验收本轮开发成果。

1. 阅读本轮需求：{round_dir}/requirement.md
2. 编写 Playwright Python 脚本访问 {self.verification.base_url}，逐条验证需求是否被满足
3. 截图保存到 notes/ 目录，用于对比
4. 输出验收结果

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS 或 FAIL
timestamp: （当前时间 ISO 格式）
---

result 必须是 PASS 或 FAIL。如果 FAIL，逐条列出未通过的需求和原因。"""

    def _acceptance_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        return f"""你是产品经理。你的任务是验收本轮开发成果。

1. 阅读本轮需求：{round_dir}/requirement.md
2. 运行测试命令确认全部通过：`{self.verification.test_command}`
3. 执行以下示例命令，验证 CLI 行为符合预期：
{examples}
4. 检查命令输出和生成的文件是否正确
5. 逐条对照需求，判定是否满足

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS 或 FAIL
timestamp: （当前时间 ISO 格式）
---

result 必须是 PASS 或 FAIL。如果 FAIL，逐条列出未通过的需求和原因。"""
```

- [ ] **Step 6: Update old `TestProductRole` tests to use `VerificationConfig`**

In `tests/test_roles.py`, update the existing `TestProductRole` class:

```python
class TestProductRole:
    def test_explore_prompt_includes_base_url(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("explore", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "http://localhost:3000" in prompt
        assert "requirement.md" in prompt
        assert "Fix login" in prompt

    def test_acceptance_prompt_includes_requirement(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("acceptance", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "requirement.md" in prompt
        assert "acceptance.md" in prompt
        assert "PASS" in prompt and "FAIL" in prompt

    def test_clarify_prompt(self):
        verification = VerificationConfig(type="web", base_url="http://localhost:3000")
        role = ProductRole(verification=verification)
        prompt = role.build_prompt("clarify", round_num=1, round_dir="/r/001", goals=["Fix login"])
        assert "design.md" in prompt
        assert "clarification.md" in prompt
```

- [ ] **Step 7: Run all role tests**

Run: `python -m pytest tests/test_roles.py -v`
Expected: All pass (old tests updated + new CLI/web/context tests).

- [ ] **Step 8: Commit**

```bash
git add ai_loop/roles/product.py tests/test_roles.py
git commit -m "feat: ProductRole accepts VerificationConfig, branches prompts by type"
```

---

### Task 4: Add `context` parameter to `DeveloperRole` and `ReviewerRole`

**Files:**
- Modify: `ai_loop/roles/developer.py`
- Modify: `ai_loop/roles/reviewer.py`
- Modify: `tests/test_roles.py`

- [ ] **Step 1: Write failing test — DeveloperRole context parameter**

Add to `tests/test_roles.py`:

```python
class TestDeveloperRoleContext:
    def test_context_appended_to_design_prompt(self):
        role = DeveloperRole()
        prompt = role.build_prompt(
            "design", round_num=1, round_dir="/r/001",
            goals=["Fix login"], context="## requirement.md\nFix the bug",
        )
        assert "## requirement.md" in prompt
        assert "Fix the bug" in prompt
        assert "design.md" in prompt  # original content still present
```

- [ ] **Step 2: Write failing test — ReviewerRole context parameter**

Add to `tests/test_roles.py`:

```python
class TestReviewerRoleContext:
    def test_context_appended_to_review_prompt(self):
        role = ReviewerRole()
        prompt = role.build_prompt(
            "review", round_num=1, round_dir="/r/001",
            goals=["Fix login"], context="## requirement.md\nThe requirement",
        )
        assert "## requirement.md" in prompt
        assert "The requirement" in prompt
        assert "git diff" in prompt  # original content still present
```

- [ ] **Step 3: Run tests to confirm they fail**

Run: `python -m pytest tests/test_roles.py::TestDeveloperRoleContext tests/test_roles.py::TestReviewerRoleContext -v`
Expected: FAIL — `build_prompt` does not accept `context` parameter.

- [ ] **Step 4: Update `DeveloperRole.build_prompt` to accept `context`**

In `ai_loop/roles/developer.py`, change the `build_prompt` signature and append context:

```python
class DeveloperRole:
    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
            "design": self._design_prompt,
            "implement": self._implement_prompt,
            "verify": self._verify_prompt,
            "fix_review": self._fix_review_prompt,
        }
        builder = builders.get(phase)
        if builder is None:
            raise ValueError(f"Unknown developer phase: {phase}")
        prompt = builder(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt
```

No changes to the individual prompt methods.

- [ ] **Step 5: Update `ReviewerRole.build_prompt` to accept `context`**

In `ai_loop/roles/reviewer.py`:

```python
class ReviewerRole:
    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        if phase != "review":
            raise ValueError(f"Unknown reviewer phase: {phase}")
        goals_text = "\n".join(f"- {g}" for g in goals)
        prompt = self._review_prompt(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt
```

- [ ] **Step 6: Run all role tests**

Run: `python -m pytest tests/test_roles.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add ai_loop/roles/developer.py ai_loop/roles/reviewer.py tests/test_roles.py
git commit -m "feat: add context parameter to DeveloperRole and ReviewerRole build_prompt"
```

---

### Task 5: Integrate `ContextCollector` and conditional server into `Orchestrator`

**Files:**
- Modify: `ai_loop/orchestrator.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing test — orchestrator skips server for CLI config**

Add a new fixture to `tests/conftest.py`:

```python
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
    for role in ("orchestrator", "product", "developer", "reviewer"):
        ws = workspaces / role
        ws.mkdir(parents=True)
        (ws / "CLAUDE.md").write_text(f"# Role: {role}\n")
        if role != "orchestrator":
            (ws / "notes").mkdir()
    return ai_dir
```

Add test in `tests/test_orchestrator.py`:

```python
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

        # Should NOT raise even though there's no server config
        summary = cli_orch.run_single_round()
        assert summary is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator.py::TestOrchestratorCliProject::test_server_not_started_for_cli_project -v`
Expected: FAIL — Orchestrator constructor requires `server` config fields.

- [ ] **Step 3: Write failing test — context is passed to `_call_role`**

Add to `tests/test_orchestrator.py`:

```python
class TestOrchestratorContext:
    @patch.object(Orchestrator, "_ask_brain")
    @patch("ai_loop.orchestrator.RoleRunner")
    def test_call_role_injects_context(
        self, mock_runner_cls, mock_brain, cli_ai_loop_dir: Path
    ):
        # Create a requirement.md in round dir so context collector finds it
        round_dir = cli_ai_loop_dir / "rounds" / "001"
        (round_dir / "requirement.md").write_text("# Req\nDo something")

        mock_runner = MagicMock()
        mock_runner.call.return_value = ""
        mock_runner_cls.return_value = mock_runner

        orch = Orchestrator(cli_ai_loop_dir)

        # Call developer:design which depends on requirement.md
        orch._call_role("developer:design", 1, round_dir, ["goal"])

        # The prompt passed to runner.call should contain requirement content
        call_args = mock_runner.call.call_args
        prompt = call_args[0][0]
        assert "Do something" in prompt
```

- [ ] **Step 4: Update `Orchestrator` to use `VerificationConfig` and `ContextCollector`**

In `ai_loop/orchestrator.py`, update imports:

```python
from ai_loop.config import AiLoopConfig, load_config, VerificationConfig
from ai_loop.context import ContextCollector
```

Update `__init__`:

```python
def __init__(self, ai_loop_dir: Path, verbose: bool = False):
    self._dir = ai_loop_dir
    self._config = load_config(ai_loop_dir / "config.yaml")
    self._state_file = ai_loop_dir / "state.json"
    self._state = load_state(self._state_file)
    self._memory = MemoryManager()
    self._verbose = verbose
    self._context_collector = ContextCollector()

    project_path = self._config.project.path

    # Server is optional (CLI/library projects don't need one)
    if self._config.server:
        self._server = DevServer(
            start_command=self._config.server.start_command,
            cwd=project_path,
            health_url=self._config.server.health_url,
            health_timeout=self._config.server.health_timeout,
            stop_signal=self._config.server.stop_signal,
            log_path=ai_loop_dir / "server.log",
        )
    else:
        self._server = None

    self._brain = Brain(
        orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator")
    )

    self._product = ProductRole(verification=self._config.verification)
    self._developer = DeveloperRole()
    self._reviewer = ReviewerRole()

    self._runners = {
        "product": RoleRunner("product", ["Read", "Glob", "Grep", "Bash"]),
        "developer": RoleRunner("developer", ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]),
        "reviewer": RoleRunner("reviewer", ["Read", "Glob", "Grep", "Bash"]),
    }
```

Update `_server_start` and `_server_stop`:

```python
def _server_start(self) -> None:
    if self._server is None:
        return
    self._log("\033[2m🖥  Dev server 启动中...\033[0m")
    self._server.start()
    self._log("\033[2m🖥  Dev server 已就绪\033[0m")

def _server_stop(self) -> None:
    if self._server is None:
        return
    self._server.stop()
    self._log("\033[2m🖥  Dev server 已停止\033[0m")
```

Update `_call_role` to inject context:

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
    prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)
    workspace = str(self._dir / "workspaces" / role_name)
    self._runners[role_name].call(prompt, cwd=workspace, verbose=self._verbose)
```

- [ ] **Step 5: Run all orchestrator tests**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: All pass (old + new tests).

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add ai_loop/orchestrator.py tests/test_orchestrator.py tests/conftest.py
git commit -m "feat: integrate ContextCollector and conditional server into Orchestrator"
```

---

### Task 6: Update CLI `init` command for optional server/browser

**Files:**
- Modify: `ai_loop/cli.py`

- [ ] **Step 1: Add `--type` option to `init` command**

In `ai_loop/cli.py`, add to the `init` command:

```python
@click.option("--type", "project_type", type=click.Choice(["web", "cli", "library"]),
              default="web", help="Project type (determines verification strategy)")
@click.option("--test-command", default=None, help="Test command for CLI/library projects")
```

- [ ] **Step 2: Update `init` body to conditionally include server/browser**

Replace the config-building section in `init` (the `config = { ... }` dict and write) with:

```python
    config = {
        "project": {
            "name": name,
            "path": str(project),
            "description": description,
        },
        "goals": list(goal) if goal else [],
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }

    if project_type == "web":
        config["server"] = {
            "start_command": start_command,
            "start_cwd": ".",
            "health_url": health_url,
            "health_timeout": 30,
            "stop_signal": "SIGTERM",
        }
        config["verification"] = {
            "type": "web",
            "base_url": base_url,
        }
    else:
        config["verification"] = {
            "type": project_type,
            "test_command": test_command or "",
            "run_examples": [],
        }
```

- [ ] **Step 3: Make `--start-command`, `--health-url`, `--base-url` prompting conditional on web type**

Update the auto-detect and prompt section so these fields are only required/prompted for `--type web`. For CLI/library, skip server-related prompts and instead prompt for `--test-command` if not provided.

The key change: wrap the `start_command`, `health_url`, `base_url` resolution in `if project_type == "web":`, and add `elif project_type in ("cli", "library"):` for test_command.

- [ ] **Step 4: Test manually — init a CLI project**

Run: `python -m ai_loop.cli init /tmp/test-cli-init --name TestCLI --type cli --test-command "pytest" --no-detect --goal "Add help output"`

Check: `/tmp/test-cli-init/.ai-loop/config.yaml` should have `verification.type: cli`, no `server` block.

Clean up: `rm -rf /tmp/test-cli-init`

- [ ] **Step 5: Test manually — init a web project (backward compat)**

Run: `python -m ai_loop.cli init /tmp/test-web-init --name TestWeb --type web --start-command "npm start" --health-url http://localhost:3000 --base-url http://localhost:3000 --no-detect --goal "Add dark mode"`

Check: `/tmp/test-web-init/.ai-loop/config.yaml` should have `verification.type: web`, `server` block present.

Clean up: `rm -rf /tmp/test-web-init`

- [ ] **Step 6: Commit**

```bash
git add ai_loop/cli.py
git commit -m "feat: cli init supports --type cli/library, makes server optional"
```

---

### Task 7: Create dogfooding config

**Files:**
- Create: `.ai-loop/config.yaml`

- [ ] **Step 1: Create `.ai-loop/` directory structure**

```bash
mkdir -p .ai-loop
```

- [ ] **Step 2: Write the dogfooding config**

Create `.ai-loop/config.yaml`:

```yaml
project:
  name: ai-loop
  path: .
  description: AI-driven product iteration loop framework

goals: []

verification:
  type: cli
  test_command: "python -m pytest tests/ -v"
  run_examples:
    - "python -m ai_loop.cli init /tmp/ai-loop-test --name TestApp --type web --start-command 'echo ok' --health-url http://localhost:3000 --base-url http://localhost:3000 --no-detect"

limits:
  max_review_retries: 3
  max_acceptance_retries: 2
```

- [ ] **Step 3: Verify config loads correctly**

Run: `python -c "from ai_loop.config import load_config; from pathlib import Path; c = load_config(Path('.ai-loop/config.yaml')); print(f'type={c.verification.type}, server={c.server}')"`

Expected output: `type=cli, server=None`

- [ ] **Step 4: Commit**

```bash
git add .ai-loop/config.yaml
git commit -m "feat: add dogfooding config for ai-loop self-iteration"
```

---

### Task 8: Final integration test — full test suite passes

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Run lint (if configured)**

Run: `python -m ruff check ai_loop/ tests/` (or whichever linter is configured)
Expected: No errors.

- [ ] **Step 3: Verify backward compatibility — existing web config still works**

Run: `python -c "
from ai_loop.config import load_config
from pathlib import Path
import yaml, tempfile

cfg = {
    'project': {'name': 'web-app', 'path': '/tmp/web'},
    'goals': ['test'],
    'server': {'start_command': 'npm start', 'health_url': 'http://localhost:3000'},
    'browser': {'base_url': 'http://localhost:3000'},
}
p = Path(tempfile.mktemp(suffix='.yaml'))
p.write_text(yaml.dump(cfg))
c = load_config(p)
print(f'type={c.verification.type}, base_url={c.verification.base_url}, server={c.server is not None}')
p.unlink()
"`

Expected: `type=web, base_url=http://localhost:3000, server=True`

- [ ] **Step 4: Final commit if any fixups needed**

Only if steps above revealed issues.
