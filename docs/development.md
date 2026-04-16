# 开发指南

## 环境搭建

### 前置条件

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)（确保 `claude` 命令可用）

### 安装

```bash
git clone https://github.com/zmzhu/ai-loop.git
cd ai-loop

pip install -e ".[dev]"

# 如果需要浏览器自动化（产品经理角色需要）
pip install -e ".[browser]"
playwright install chromium
```

## 测试

### 运行测试

```bash
# 完整测试（含覆盖率报告）
python -m pytest tests/ -v

# 单个模块
python -m pytest tests/test_brain.py -v

# 匹配测试名
python -m pytest tests/ -k "test_decide" -v
```

### 覆盖率要求

`pyproject.toml` 中配置了 `--cov-fail-under=80`，覆盖率低于 80% 会导致测试失败。

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=ai_loop --cov-report=term-missing --cov-fail-under=80"
```

### 测试结构

测试与模块一一对应：

| 源文件 | 测试文件 |
|--------|----------|
| `brain.py` | `test_brain.py` |
| `cli.py` | `test_cli.py` |
| `config.py` | `test_config.py` |
| `context.py` | `test_context.py` |
| `detect.py` | `test_detect.py` |
| `logger.py` | `test_logger.py` |
| `memory.py` | `test_memory.py` |
| `orchestrator.py` | `test_orchestrator.py` |
| `roles/*.py` | `test_roles.py` |
| `server.py` | `test_server.py` |
| `state.py` | `test_state.py` |
| （集成） | `test_integration.py` |

### conftest.py

`tests/conftest.py` 提供共享 fixture，新增测试时优先复用已有 fixture。

### 写测试的原则

- 所有 Claude Code 调用都应 mock — 测试不应实际调用 Claude CLI
- 使用 `pytest-tmp-files` 创建临时目录结构
- 测试应验证行为而非实现细节

## 模块改动注意事项

### orchestrator.py

编排器是核心流程控制器，改动前需理解完整流程（见 [编排引擎](orchestration.md)）。

注意点：
- `run_single_round()` 的阶段顺序和 Brain 决策分支必须与设计文档一致
- Server 启停有严格的时机要求（Product 探索/验收前启动，不需要时停止）
- `_ensure_workspaces()` 负责工作区、`product-knowledge/` 目录、按包版本刷新 `CLAUDE.md` 模板（见 `MemoryManager.refresh_template`）并回写 `LoopState.ai_loop_version`
- Product 探索上下文注入（`index.md`、`code-digest.md`）与 `ProductRole` 的 `knowledge_dir` 需保持一致
- 修改流程后同步更新 `test_orchestrator.py` 和 `test_integration.py`

### brain.py

决策大脑影响整个流程走向。

注意点：
- `DECISION_POINT_FILES` 定义每个决策点读取哪些文件
- `DECISION_POINT_INSTRUCTIONS` 定义每个决策点的判断指令和可选决策
- 新增决策点需同步更新这两个映射
- `BrainDecision.from_claude_output()` 的 JSON 解析有三层兜底策略，改动需谨慎

### roles/base.py

RoleRunner 是所有角色调用的底层，改动影响面最大。

注意点：
- 事件流处理（control_request 自动批准、result 解析）是核心路径
- `_has_needs_input` / `_extract_question` 的标记格式 `{"needs_input": true}` 被角色 prompt 和 Orchestrator 共同依赖
- 超时/错误处理要确保进程被正确清理

### roles/product.py, developer.py, reviewer.py

角色行为由 prompt 模板驱动。改动 prompt 本质上是在改变 Agent 行为。

注意点：
- Prompt 修改应同步更新对应的测试
- Product 的 web/cli 分支逻辑需要同时维护；`ProductRole` 构造需传入 `knowledge_dir`，prompt 中的产品认知维护说明与 Orchestrator 注入路径一致
- YAML frontmatter 格式（round, role, phase, result, timestamp）是 Brain 和 ContextCollector 的隐式契约

### memory.py

记忆管理影响跨轮次连续性。

注意点：
- `MEMORY_SECTION_HEADER = "## 累积记忆"` 是与 CLAUDE.md 模板的隐式契约
- `refresh_template` 与 Orchestrator 版本对齐逻辑共用该标记；改动标记或模板边界行为时需同步测 `test_memory.py` / `test_orchestrator.py`
- `compact_memories` 的压缩逻辑依赖正则匹配 `### Round \d{3}`，不要改动轮次命名格式
- 压缩后的 `### 历史摘要` 段落会在下次压缩时被再次输入给 summarizer

### context.py

上下文注入的依赖关系直接影响角色接收到的信息。

注意点：
- `PHASE_DEPS` 字典定义了每个阶段的依赖文件
- 新增阶段必须在此注册依赖
- 缺失的依赖文件会被静默跳过（设计如此，因为 clarification.md 不一定存在）

### config.py

配置变更影响所有下游模块。

注意点：
- 新增配置字段需更新 `load_config()` 的解析逻辑和对应 dataclass
- 向后兼容：旧配置（只有 browser.base_url）仍需正常工作
- `human_decision` 的合法值在 `HUMAN_DECISION_LEVELS` 元组中定义

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

| 前缀 | 含义 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | Bug 修复 |
| `docs:` | 文档变更 |
| `refactor:` | 重构（不影响功能） |
| `test:` | 测试相关 |
| `chore:` | 构建/工具链/辅助变更 |

示例：
```
feat: add --type and --test-command options to init command
fix: use Optional[] syntax in server.py for Python 3.9 compat
```

## 发版流程

1. 更新 `pyproject.toml` 中的 `version`
2. 更新 `CHANGELOG.md`：将 `[Unreleased]` 的内容移到新版本号下
3. 提交：`git commit -m "chore: release vX.Y.Z"`
4. 打 tag：`git tag vX.Y.Z`
5. 推送：`git push && git push --tags`

## 项目依赖

### 运行时

| 包 | 用途 |
|----|------|
| `click>=8.0` | CLI 框架 |
| `pyyaml>=6.0` | 配置文件解析 |
| `requests>=2.28` | Dev Server 健康检查 |

### 可选

| 包 | 用途 |
|----|------|
| `playwright>=1.40` | 浏览器自动化（Product 角色 web 验收） |

### 开发

| 包 | 用途 |
|----|------|
| `pytest>=7.0` | 测试框架 |
| `pytest-tmp-files>=0.0.2` | 临时文件 fixture |
| `pytest-cov>=4.0` | 覆盖率报告 |
