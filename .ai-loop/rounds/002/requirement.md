---
round: 2
role: product
phase: requirement
result: null
timestamp: 2026-04-15T14:35:00+08:00
---

# Round 002 需求：交互体验提升与测试能力增强

## 背景

Round 001 完成了 5 项核心优化（上下文内联、记忆滑动窗口、角色专属记忆、代码摘要缓存等）。最近提交重写了 RoleRunner 为 stream-json 双向通信并新增 `--human-decision` 人机协作模式。

**当前状态**：96 个测试全部通过，15 个文件变更（+590/-131 行）。

**本轮目标**：提升交互体验 + 找到更全面更完善的测试手段。

---

## REQ-1: `init` 命令应自动创建不存在的项目目录

**现状**：`cli.py:33` 使用 `click.Path(exists=True)` 强制要求目录已存在。运行 `ai-loop init /tmp/new-project --name Foo --type cli --test-command 'echo ok' --no-detect` 时报错 `Path '/tmp/new-project' does not exist`，用户必须先手动 `mkdir`。这是新手首次体验时最先遇到的绊脚石。

**期望**：
1. 将 `click.Path(exists=True)` 改为 `click.Path()`
2. 目录不存在时自动递归创建（`Path.mkdir(parents=True, exist_ok=True)` 语义）
3. 创建失败（如权限不足）时报出有意义的错误：`目录创建失败: {path}: {错误原因}`
4. 已有 `.ai-loop` 的目录仍然拒绝重复初始化

**验收标准**：
- `ai-loop init /tmp/a/b/c --name Test --type cli --test-command 'echo ok' --no-detect` 在目录不存在时成功初始化
- 权限不足时报错包含路径和原因
- 新增至少 1 个测试

---

## REQ-2: `run` 命令 "添加目标" 操作不应持久化到 config.yaml

**现状**：`cli.py:224-234`（错误恢复路径）和 `cli.py:266-275`（轮次结束路径），用户选 `[g]` 添加目标时直接读写 `config.yaml`：

```python
config["goals"].append(new_goal)
config_path.write_text(yaml.dump(...))
```

但正常的 `--goal` 参数仅通过 `orch.add_goal(g)` 注入运行时，不持久化。两条路径的行为语义不一致，且持久化可能导致后续轮次携带临时性目标。

**期望**：错误恢复路径和轮次结束路径统一使用 `orch.add_goal(new_goal)`，不修改 `config.yaml`。

**验收标准**：
- 运行出错后选 `[g]` 添加目标，新目标生效但 `config.yaml` 的 goals 不变
- 轮次正常结束后选 `[g]` 添加目标，同样不持久化
- `--goal` 参数现有行为不受影响
- 新增至少 2 个测试

---

## REQ-3: `--verbose` 硬编码导致 quiet 模式语义失效

**现状**：`roles/base.py:48` 无条件添加 `--verbose` 到 claude 命令：
```python
cmd = [
    "claude",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "--verbose",  # 硬编码，不受 verbose 参数控制
    "--permission-prompt-tool", "stdio",
]
```
此前是 `if verbose: cmd.append("--verbose")` 的条件写法。虽然 `_render_event` 的调用仍受 verbose 参数控制（不影响终端可见输出），但底层 Claude CLI 在 `--verbose` 模式下会通过 stream-json 输出更多事件，增加 stdout 解析开销和 I/O 量。用户传 `-q/--quiet` 期望安静运行，底层却仍是 verbose 模式，语义不一致。

**期望**：将 `--verbose` 恢复为条件添加。`call()` 方法的 `verbose` 参数同时控制 Claude CLI 的 `--verbose` 标志和 `_render_event` 的调用。

**验收标准**：
- `ai-loop run -q` 时构造的 claude 命令不含 `--verbose`
- `ai-loop run`（默认 verbose）时构造的 claude 命令含 `--verbose`
- `result` 事件在两种模式下都能正常解析
- 新增至少 1 个测试验证命令构造差异

---

## REQ-4: detect.py 扩展支持 CLI/library 项目自动检测

**现状**：
1. `detect.py` 的 `DETECT_PROMPT` 只检测 web 项目字段（start_command, health_url, base_url），不包含 test_command 和 run_examples
2. `cli.py:54` 的 auto-detect 仅在 `project_type == "web"` 时触发
3. CLI/library 用户完全无法享受自动检测，必须手动提供所有参数

**期望**：
1. 扩展 `DETECT_PROMPT`，增加 `test_command` 和 `run_examples` 的检测指引（从 pyproject.toml pytest 配置、package.json scripts.test、Makefile test target 等推断）
2. `cli.py` 的 auto-detect 不再限于 web 类型，CLI/library 也可触发
3. 检测输出 JSON 新增 `test_command` 和 `run_examples` 字段

**验收标准**：
- 含 pyproject.toml（配了 pytest）的目录，`init --type cli` 不带 `--no-detect` 可推断 test_command
- 推断失败时 fallback 到手动输入
- web 类型现有逻辑不受影响
- 新增至少 1 个测试

---

## REQ-5: init 命令增加 `--run-example` 参数

**现状**：`init --type cli` 生成的 config.yaml 中 `run_examples: []` 始终为空列表。ProductRole 的 CLI explore 和 acceptance prompt 依赖 `run_examples` 展示示例命令（`product.py:67-68`），空列表导致产品角色无具体命令可运行、验证流程空转。

**期望**：
1. init 命令新增 `--run-example` 选项（`multiple=True`）
2. CLI/library 类型初始化时将值写入 `verification.run_examples`
3. web 类型忽略此参数

**验收标准**：
- `ai-loop init /tmp/t --type cli --test-command 'pytest' --run-example 'myapp --help' --run-example 'myapp run demo' --no-detect --name T` 后 config.yaml 的 `run_examples` 含两条记录
- 不传 `--run-example` 时为空列表，不报错
- 新增至少 1 个测试

---

## REQ-6: 为 detect.py 补充单元测试

**现状**：`tests/` 目录中没有 `test_detect.py`。`detect.py` 是唯一没有对应测试文件的源文件。其中包含 JSON 解析、markdown 代码块剥离、超时处理、错误回退等逻辑，全部零覆盖。如果有人修改了 JSON 提取逻辑（如 `cli.py:52-62` 的 markdown 剥离），没有任何测试能捕获回归。

**期望**：新建 `tests/test_detect.py`，至少覆盖以下场景：
1. `detect_project_config()` 正常返回 JSON 时的解析
2. Claude CLI 输出被 markdown 代码块包裹时的剥离逻辑
3. Claude CLI 输出中 JSON 前后有多余文本时的提取（`raw.find("{")` 路径）
4. Claude CLI 超时时抛出 `RuntimeError("项目检测超时")`
5. Claude CLI 返回非零退出码时的错误处理
6. 输出完全无法解析为 JSON 时的错误处理

**验收标准**：
- 新增 `tests/test_detect.py`，至少 6 个测试用例覆盖上述场景
- 所有测试通过 mock `subprocess.run`，不调用真实 Claude CLI
- 覆盖 `detect.py` 中所有 `except` 和 `if/else` 分支

---

## REQ-7: 增加测试覆盖率度量和 CI 门禁

**现状**：项目使用 pytest 运行 96 个测试，但没有配置覆盖率收集。`pyproject.toml` 中未配置 `pytest-cov`，也没有覆盖率阈值。开发者（包括 AI 开发者）无法知道哪些代码路径缺少测试，只能凭经验判断。

**期望**：
1. 添加 `pytest-cov` 依赖
2. `pyproject.toml` 中配置 pytest 默认使用 `--cov=ai_loop --cov-report=term-missing`
3. 设置覆盖率失败阈值 `--cov-fail-under=80`（当前测试量足够达到）
4. developer 和 reviewer 角色的 prompt 中引用覆盖率数据作为验证依据

**验收标准**：
- `pytest` 运行时自动输出覆盖率报告，显示每个文件的行覆盖率和未覆盖行号
- 覆盖率低于 80% 时 pytest 返回非零退出码
- `pyproject.toml` 中新增 `[tool.pytest.ini_options]` 的 `addopts` 配置
- 现有 96 个测试 + REQ-6 新增测试后覆盖率 >= 80%

---

## 优先级排序

| 优先级 | 需求 | 理由 |
|--------|------|------|
| P0 | REQ-6 | 测试基础设施：detect.py 零测试覆盖，是唯一的测试盲区 |
| P0 | REQ-7 | 测试基础设施：无覆盖率度量则改进无从量化 |
| P1 | REQ-1 | 首次体验：新用户遇到的第一个错误 |
| P1 | REQ-2 | 数据正确性：运行时/持久化语义不一致 |
| P1 | REQ-3 | 语义一致性：quiet 模式名不副实 |
| P2 | REQ-4 | 功能扩展：CLI/library 用户缺少自动检测支持 |
| P2 | REQ-5 | 功能完善：init 缺少 run-example 参数 |

## 技术约束

- 所有改动不得破坏现有 96 个测试
- `config.yaml` 新增字段需有合理默认值，旧配置文件无新字段时行为等同当前版本
- `detect.py` 的测试全部 mock `subprocess.run`，不调用真实 Claude CLI
- 覆盖率配置仅影响 `ai_loop/` 目录，不含 `tests/` 自身
