---
round: 2
role: developer
phase: design
result: null
timestamp: 2026-04-15T15:10:00+08:00
---

# Round 002 实现计划

## 涉及文件清单

| 操作 | 文件路径 | 需求 |
|------|----------|------|
| 修改 | `ai_loop/cli.py` | REQ-1, REQ-2, REQ-4, REQ-5 |
| 修改 | `ai_loop/roles/base.py` | REQ-3 |
| 修改 | `ai_loop/detect.py` | REQ-4 |
| 修改 | `pyproject.toml` | REQ-7 |
| 修改 | `ai_loop/roles/developer.py` | REQ-7 |
| 修改 | `ai_loop/roles/reviewer.py` | REQ-7 |
| 修改 | `tests/test_cli.py` | REQ-1, REQ-2, REQ-4, REQ-5 |
| 修改 | `tests/test_roles.py` | REQ-3 |
| 新建 | `tests/test_detect.py` | REQ-6 |

---

## 分步计划

### Step 1: REQ-6 — 新建 `tests/test_detect.py`（P0）

**做什么**：为 `detect.py` 补充单元测试，覆盖所有分支。

**改哪个文件**：新建 `tests/test_detect.py`

**测试用例**：

1. `test_detect_normal_json` — `subprocess.run` 返回合法 JSON，验证解析正确
2. `test_detect_markdown_wrapped_json` — 输出被 ` ```json ... ``` ` 包裹，验证剥离后解析正确
3. `test_detect_json_with_extra_text` — JSON 前后有多余文本（走 `raw.find("{")` 路径），验证提取正确
4. `test_detect_timeout` — `subprocess.run` 抛出 `TimeoutExpired`，验证 `RuntimeError("项目检测超时")`
5. `test_detect_nonzero_exit` — `returncode != 0`，验证 `RuntimeError` 含 stderr 内容
6. `test_detect_unparseable_output` — 输出完全无 JSON，验证抛出 `RuntimeError("无法解析检测结果")`

**实现要点**：
- 所有测试 mock `subprocess.run`，不调用真实 CLI
- 用 `unittest.mock.patch("ai_loop.detect.subprocess.run")` 注入

**预期结果**：6 个新测试全部通过

---

### Step 2: REQ-7 — 添加 `pytest-cov` 配置（P0）

**做什么**：在 `pyproject.toml` 中添加 pytest-cov 依赖和配置。

**改哪个文件**：`pyproject.toml`

**具体改动**：

1. `[project.optional-dependencies].dev` 增加 `"pytest-cov>=4.0"`
2. `[tool.pytest.ini_options]` 增加 `addopts = "--cov=ai_loop --cov-report=term-missing --cov-fail-under=80"`

**预期结果**：`pytest` 运行后自动输出每文件行覆盖率和未覆盖行号；覆盖率低于 80% 时返回非零退出码

---

### Step 3: REQ-7 续 — 角色 prompt 引用覆盖率数据

**做什么**：在 developer 和 reviewer 的 prompt 中添加覆盖率相关指引。

**改哪个文件**：
- `ai_loop/roles/developer.py` — `_implement_prompt` 和 `_verify_prompt` 中自验证步骤加入"检查覆盖率报告"
- `ai_loop/roles/reviewer.py` — `_review_prompt` 第 4 条"测试覆盖"维度加入"引用覆盖率报告"

**具体改动**：

`developer.py:_implement_prompt` 自验证清单追加一条：
```
5. 检查 pytest 覆盖率报告，确认无关键路径遗漏
```

`developer.py:_verify_prompt` 验证清单追加一条：
```
5. 检查 pytest 覆盖率报告（term-missing），确认新增代码已覆盖
```

`reviewer.py:_review_prompt` 第 4 条改为：
```
4. 测试覆盖：关键路径是否有测试，引用 pytest 覆盖率报告（term-missing）确认行覆盖
```

**预期结果**：角色在执行时会主动查看覆盖率数据作为验证依据

---

### Step 4: REQ-1 — `init` 命令自动创建不存在的目录

**做什么**：移除 `exists=True` 限制，目录不存在时自动递归创建。

**改哪个文件**：`ai_loop/cli.py`

**具体改动**：

1. 第 33 行：`click.Path(exists=True)` → `click.Path()`
2. 第 46 行后（`project = Path(project_path).resolve()` 之后）插入：
   ```python
   if not project.exists():
       try:
           project.mkdir(parents=True, exist_ok=True)
       except OSError as e:
           raise click.ClickException(f"目录创建失败: {project}: {e}")
   ```
3. 已有 `.ai-loop` 的目录仍然拒绝（第 49-50 行逻辑不变）

**改哪个测试文件**：`tests/test_cli.py`

**新增测试**：
- `test_init_creates_nonexistent_directory` — 传入不存在的嵌套路径（如 `tmp/a/b/c`），验证初始化成功且 `.ai-loop` 创建

**预期结果**：现有 3 个 init 测试不受影响；新增 1 个测试通过

---

### Step 5: REQ-2 — 添加目标不持久化到 config.yaml

**做什么**：错误恢复路径和轮次结束路径的 `[g]` 操作统一用 `orch.add_goal()`，移除 config.yaml 读写。

**改哪个文件**：`ai_loop/cli.py`

**具体改动**：

1. 第 224-233 行（错误恢复路径）替换为：
   ```python
   elif action == "g":
       new_goal = click.prompt("输入新目标")
       orch.add_goal(new_goal)
       click.echo(f"已添加目标: {new_goal}")
   ```
2. 第 265-275 行（轮次结束路径）替换为：
   ```python
   elif action == "g":
       new_goal = click.prompt("输入新目标")
       orch.add_goal(new_goal)
       click.echo(f"已添加目标: {new_goal}")
   ```

**改哪个测试文件**：`tests/test_cli.py`

**新增测试**：
- `test_run_error_add_goal_no_persist` — mock Orchestrator 使 `run_single_round` 抛异常，输入 `g\n新目标\ns\n`，验证 `config.yaml` 的 goals 不变
- `test_run_complete_add_goal_no_persist` — mock Orchestrator 正常返回，输入 `g\n新目标\ns\n`，验证 `config.yaml` 的 goals 不变

**预期结果**：2 个新测试通过；`--goal` 参数行为不受影响

---

### Step 6: REQ-3 — `--verbose` 恢复为条件添加

**做什么**：将 `base.py` 中硬编码的 `--verbose` 恢复为仅在 `verbose=True` 时添加。

**改哪个文件**：`ai_loop/roles/base.py`

**具体改动**：

第 44-50 行改为：
```python
cmd = [
    "claude",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "--permission-prompt-tool", "stdio",
]
if verbose:
    cmd.append("--verbose")
```

**改哪个测试文件**：`tests/test_roles.py`（追加）

**新增测试**：
- `test_rolerunner_verbose_flag_conditional` — mock `subprocess.Popen`，分别以 `verbose=True` 和 `verbose=False` 调用 `RoleRunner.call()`，断言 `--verbose` 只在 True 时出现在 cmd 中

**实现要点**：需要捕获 `Popen` 的调用参数。可以通过 `mock_popen.call_args[0][0]` 获取 cmd 列表。mock 需要模拟 stdout 返回一个 `result` 事件行，stdin/stderr 也需要 mock。

**预期结果**：1 个新测试通过

---

### Step 7: REQ-4 — detect.py 扩展支持 CLI/library

**做什么**：扩展检测 prompt 和 CLI 调用逻辑，使 CLI/library 项目也能享受自动检测。

**改哪个文件**：

1. `ai_loop/detect.py` — 扩展 `DETECT_PROMPT`
2. `ai_loop/cli.py` — 去除 `project_type == "web"` 限制

**具体改动**：

**detect.py**：`DETECT_PROMPT` JSON 模板新增两个字段：
```json
"test_command": "测试命令（如 pytest, npm test, cargo test，从 pyproject.toml/package.json/Makefile 推断）",
"run_examples": ["示例运行命令（CLI 项目从 entry_points/bin 推断）"]
```
检测规则追加：
```
7. 检查 pyproject.toml 的 [tool.pytest.ini_options] 或 scripts 段推断 test_command
8. 检查 package.json 的 scripts.test 推断 test_command
9. 检查 Makefile 的 test target 推断 test_command
10. 从 pyproject.toml 的 [project.scripts] 或 package.json 的 bin 推断 run_examples
```

**cli.py**：第 52-66 行重写 auto-detect 逻辑，去除 `project_type == "web"` 限制：

```python
# Auto-detect missing config via Claude Code
detected = {}
if not no_detect:
    if project_type == "web":
        needs_detect = any(
            v is None for v in [name, start_command, health_url, base_url]
        )
    else:
        needs_detect = any(v is None for v in [name, test_command])
    if needs_detect:
        click.echo("正在分析项目，自动检测配置...")
        try:
            detected = detect_project_config(str(project))
            click.echo("检测完成。")
        except Exception as e:
            click.echo(f"自动检测失败: {e}")
            click.echo("将使用手动输入。")
```

第 76-77 行（CLI/library fallback）加入 detected 值：
```python
test_command = test_command or detected.get("test_command") or click.prompt("测试命令")
```

**改哪个测试文件**：`tests/test_cli.py`

**新增测试**：
- `test_init_cli_auto_detect` — mock `detect_project_config` 返回含 `test_command` 的结果，`--type cli` 不带 `--no-detect`，验证 config.yaml 的 test_command 从 detected 获取

**预期结果**：CLI/library 项目可自动检测；web 项目现有逻辑不变；1 个新测试通过

---

### Step 8: REQ-5 — init 命令增加 `--run-example` 参数

**做什么**：为 init 添加 `--run-example` 选项（multiple=True），写入 verification.run_examples。

**改哪个文件**：`ai_loop/cli.py`

**具体改动**：

1. init 命令装饰器增加：
   ```python
   @click.option("--run-example", multiple=True, help="CLI run examples (repeatable)")
   ```
2. init 函数签名增加 `run_example` 参数
3. CLI/library 配置写入时使用参数值：
   ```python
   config["verification"] = {
       "type": project_type,
       "test_command": test_command,
       "run_examples": list(run_example),
   }
   ```
4. web 类型忽略此参数（web 分支不使用 `run_example`，现有逻辑不变）
5. auto-detect 上下文中，如果 detected 有 `run_examples` 且用户未传 `--run-example`，使用 detected 值：
   ```python
   if not run_example and project_type != "web":
       detected_examples = detected.get("run_examples", [])
       run_example = tuple(detected_examples) if detected_examples else ()
   ```

**改哪个测试文件**：`tests/test_cli.py`

**新增测试**：
- `test_init_cli_with_run_examples` — 传入两条 `--run-example`，验证 config.yaml 的 `run_examples` 含两条记录

**预期结果**：1 个新测试通过

---

### Step 9: 全量验证

**做什么**：运行完整测试套件 + 覆盖率检查。

**命令**：
```bash
cd /Users/StevenZhu/code/ai-loop && python -m pytest tests/ -v
```

**预期结果**：
- 现有 96 个测试 + 新增约 12 个测试 ≈ 108 个测试全部通过
- 覆盖率 >= 80%
- `git diff` 检查无调试代码遗留

---

## 待确认问题

无。已自行决定：
- `run_examples` auto-detect 失败时直接设为空列表，不交互 prompt（非必填项，REQ-5 提供了显式入口）
- 覆盖率阈值 80% 先不排除任何文件，跑一次看数据再调整
