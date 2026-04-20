---
round: 2
role: developer
phase: dev-log
result: null
timestamp: 2026-04-15T16:30:00+08:00
---

# 开发日志：Round 002 代码改进

## 基线

- 测试：96 passed（python -m pytest tests/ -v）
- 无覆盖率配置

## Step 1: REQ-6 — 新建 tests/test_detect.py

**做什么**：为 `detect.py` 补充单元测试，覆盖所有分支。

**新建文件**：`tests/test_detect.py`

**6 个测试用例**：
1. `test_detect_normal_json` — 合法 JSON 输出解析
2. `test_detect_markdown_wrapped_json` — markdown 代码块包裹的 JSON 剥离
3. `test_detect_json_with_extra_text` — JSON 前后多余文本提取
4. `test_detect_timeout` — TimeoutExpired 异常处理
5. `test_detect_nonzero_exit` — 非零退出码错误处理
6. `test_detect_unparseable_output` — 无法解析输出的错误处理

**测试结果**：6 passed

## Step 2: REQ-7 — 添加 pytest-cov 配置

**改动文件**：`pyproject.toml`

**具体改动**：
- `[project.optional-dependencies].dev` 增加 `"pytest-cov>=4.0"`
- `[tool.pytest.ini_options]` 增加 `addopts = "--cov=ai_loop --cov-report=term-missing --cov-fail-under=80"`

**测试结果**：102 passed，覆盖率 83.14% > 80%

## Step 3: REQ-7 续 — 角色 prompt 引用覆盖率数据

**改动文件**：
- `ai_loop/roles/developer.py` — `_implement_prompt` 追加"检查 pytest 覆盖率报告"
- `ai_loop/roles/developer.py` — `_verify_prompt` 追加"检查 pytest 覆盖率报告（term-missing）"
- `ai_loop/roles/reviewer.py` — `_review_prompt` 第 4 条改为引用覆盖率报告

**新增测试**：
- `test_implement_prompt_mentions_coverage`
- `test_verify_prompt_mentions_coverage`
- `test_review_prompt_mentions_coverage`

**TDD**：RED → 3 failed → GREEN → 3 passed → 全量 105 passed

## Step 4: REQ-1 — init 命令自动创建不存在的目录

**改动文件**：`ai_loop/cli.py`

**具体改动**：
- init 命令 `click.Path(exists=True)` → `click.Path()`
- 在 `project = Path(project_path).resolve()` 后添加 `project.mkdir(parents=True, exist_ok=True)`

**新增测试**：`test_init_creates_nonexistent_directory`

**TDD**：RED → exit_code=2 → GREEN → 全量 106 passed

## Step 5: REQ-2 — 添加目标不持久化到 config.yaml

**改动文件**：`ai_loop/cli.py`

**具体改动**：
- 错误恢复路径（`action == "g"`）：移除 config.yaml 读写，只调用 `orch.add_goal()`
- 轮次结束路径（`action == "g"`）：同上

**新增测试**：
- `test_run_error_add_goal_no_persist`
- `test_run_complete_add_goal_no_persist`

**TDD**：RED → goals 被持久化 → GREEN → 全量 108 passed，覆盖率 86.22%

## Step 6: REQ-3 — --verbose 恢复为条件添加

**改动文件**：`ai_loop/roles/base.py`

**具体改动**：
- 移除硬编码的 `"--verbose"`，改为 `if verbose: cmd.append("--verbose")`

**新增测试**：`test_verbose_flag_conditional`

**TDD**：RED → `--verbose` in cmd_false → GREEN → 全量 109 passed

## Step 7: REQ-4 — detect.py 扩展支持 CLI/library

**改动文件**：
- `ai_loop/detect.py` — DETECT_PROMPT 新增 `test_command`、`run_examples` 字段和检测规则 7-10
- `ai_loop/cli.py` — auto-detect 逻辑去除 `project_type == "web"` 限制，CLI 分支使用 `detected.get("test_command")`

**新增测试**：`test_init_cli_auto_detect`

**TDD**：RED → CLI 不 auto-detect → GREEN → 全量 110 passed

## Step 8: REQ-5 — init 命令增加 --run-example 参数

**改动文件**：`ai_loop/cli.py`

**具体改动**：
- 新增 `@click.option("--run-example", multiple=True)`
- CLI 分支 auto-detect fallback：`detected.get("run_examples", [])`
- config 写入使用 `list(run_example)` 替代硬编码 `[]`

**新增测试**：`test_init_cli_with_run_examples`

**TDD**：RED → No such option → GREEN → 全量 111 passed

## 最终验证

### 测试结果

```
============================= 111 passed in 3.15s ==============================
```

111 个测试全部通过（基线 96 + 新增 15）。

### 覆盖率报告

```
Name                            Stmts   Miss  Cover   Missing
-------------------------------------------------------------
ai_loop/__init__.py                 1      0   100%
ai_loop/brain.py                   60      4    93%   84-85, 143, 146
ai_loop/cli.py                    170     29    83%   18-23, 52-53, 74-76, 111-118, 138-139, 197, 208, 212, 236-237, 253-255, 279
ai_loop/config.py                  75      0   100%
ai_loop/context.py                 14      0   100%
ai_loop/detect.py                  31      0   100%
ai_loop/memory.py                  58      6    90%   47, 81-95
ai_loop/orchestrator.py           191     31    84%   99-103, 110, 113, 126, 133-134, 136, 142, 153, 158, 167-179, 199, 242, 252-253, 256
ai_loop/roles/__init__.py           0      0   100%
ai_loop/roles/base.py             110     39    65%   18, 26, 30, 32-33, 72, 75-76, 93, 97-100, 148, 151-177
ai_loop/roles/developer.py         19      1    95%   13
ai_loop/roles/product.py           34      1    97%   18
ai_loop/roles/reviewer.py          11      1    91%   5
ai_loop/server.py                  51      4    92%   30, 67-69
ai_loop/state.py                   32      0   100%
ai_loop/templates/__init__.py       0      0   100%
-------------------------------------------------------------
TOTAL                             857    116    86%
Required test coverage of 80% reached. Total coverage: 86.46%
```

### 需求-测试覆盖矩阵

| 需求 | 测试 | 状态 |
|------|------|------|
| REQ-1 init 自动创建目录 | `test_init_creates_nonexistent_directory` | PASS |
| REQ-2 目标不持久化 | `test_run_error_add_goal_no_persist`, `test_run_complete_add_goal_no_persist` | PASS |
| REQ-3 --verbose 条件添加 | `test_verbose_flag_conditional` | PASS |
| REQ-4 detect CLI/library | `test_init_cli_auto_detect` | PASS |
| REQ-5 --run-example 参数 | `test_init_cli_with_run_examples` | PASS |
| REQ-6 detect.py 单测 | 6 个测试覆盖全部分支 | PASS |
| REQ-7 pytest-cov 配置 | `test_implement_prompt_mentions_coverage`, `test_verify_prompt_mentions_coverage`, `test_review_prompt_mentions_coverage` | PASS |

### 调试代码检查

git diff 检查完成，无调试代码、临时注释或遗留 TODO。

### 变更文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `ai_loop/cli.py` |
| 修改 | `ai_loop/detect.py` |
| 修改 | `ai_loop/roles/base.py` |
| 修改 | `ai_loop/roles/developer.py` |
| 修改 | `ai_loop/roles/reviewer.py` |
| 修改 | `pyproject.toml` |
| 修改 | `tests/test_cli.py` |
| 修改 | `tests/test_roles.py` |
| 新建 | `tests/test_detect.py` |
