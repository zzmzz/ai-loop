# 配置参考

> 源文件：`ai_loop/config.py`

所有配置存储在 `.ai-loop/config.yaml`，由 `ai-loop init` 生成，运行时由 `load_config()` 加载校验。

## 运行时状态（state.json）

与 `config.yaml` 并列，由 `ai_loop.state` 读写，**不由用户手工编辑**（调试时可查看）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `current_round` | int | 当前轮次编号 |
| `phase` | str | 当前阶段标识（如 `idle`） |
| `retry_counts` | object | 审查/验收等重试计数 |
| `history` | array | 已完成轮次的摘要历史 |
| `ai_loop_version` | str | 上次与工作区模板对齐时所记录的 `ai_loop` 包版本；与当前安装版本不一致时，下一轮 `Orchestrator` 初始化会刷新各角色 `CLAUDE.md` 的模板段并更新此字段 |

`ai-loop init` 创建的初始 `state.json` 会将 `ai_loop_version` 设为当前包版本。

## 完整字段说明

```yaml
project:
  name: MyApp                        # 必填。项目名称
  path: .                            # 必填。项目路径（相对于 .ai-loop 的父目录解析）
  description: 一个 Web 应用          # 可选，默认 ""

goals:                               # 可选。迭代目标列表
  - 添加暗色模式
  - 优化移动端体验

verification:                        # 必填（或提供 browser.base_url 向后兼容）
  type: web                          # "web" | "cli" | "library"
  base_url: http://localhost:3000    # web 必填。浏览器访问地址
  test_command: python -m pytest     # cli/library 必填。测试命令
  run_examples:                      # cli 可选。验收时运行的示例命令
    - my-tool --help
    - my-tool run example.txt

server:                              # 可选。web 项目建议配置，cli/library 不需要
  start_command: npm run dev         # 必填。Dev server 启动命令
  health_url: http://localhost:3000  # 必填。健康检查 URL（HTTP GET 返回 200 表示就绪）
  start_cwd: .                       # 可选，默认 "."。启动命令的工作目录
  health_timeout: 30                 # 可选，默认 30。健康检查超时（秒）
  stop_signal: SIGTERM               # 可选，默认 "SIGTERM"。停止信号

browser:                             # 可选。向后兼容字段
  base_url: http://localhost:3000    # 如果没有 verification 字段，此值自动映射为 verification.type=web

limits:
  max_review_retries: 3              # 可选，默认 3。审查最多重试次数
  max_acceptance_retries: 2          # 可选，默认 2。验收最多重试次数
  memory_window: 5                   # 可选，默认 5。保留最近 N 轮完整记忆，更早的压缩为摘要

human_decision: low                  # 可选，默认 "low"。"low" = 全自动 | "high" = 关键点暂停请求人类输入
```

## 三种项目类型

### Web 项目

适用于有 UI 的 Web 应用。Product 通过 Playwright 浏览器体验产品。

```yaml
project:
  name: my-webapp
  path: .

verification:
  type: web
  base_url: http://localhost:3000

server:
  start_command: npm run dev
  health_url: http://localhost:3000

goals:
  - 添加暗色模式支持
```

### CLI 项目

适用于命令行工具。Product 通过运行示例命令体验。

```yaml
project:
  name: my-tool
  path: .

verification:
  type: cli
  test_command: python -m pytest
  run_examples:
    - my-tool --help
    - my-tool run example.txt

goals:
  - 添加 --verbose 选项
```

### Library 项目

适用于 SDK、库、框架。Product 通过运行测试套件验收。

```yaml
project:
  name: my-lib
  path: .

verification:
  type: library
  test_command: python -m pytest

goals:
  - 增加批量处理 API
```

## human_decision 等级

| 等级 | 行为 |
|------|------|
| `low`（默认） | 全自动运行，角色不会暂停请求输入，需求确认卡点跳过 |
| `high` | 角色在遇到歧义/多方案/架构决策时暂停，通过 `{"needs_input": true}` 请求人类输入；需求探索后触发人工确认卡点 |

> **需求确认卡点**：当 `human_decision` 不为 `low` 时，Product 写完 requirement.md 后，Orchestrator 会展示需求列表并等待用户操作（全部接受 / 按编号删除 / 手动编辑 / 全部拒绝）。详见 [编排引擎 — 阶段 1](orchestration.md#阶段-1需求探索)。

运行时可通过 CLI 参数覆盖配置值：

```bash
ai-loop run . --human-decision high
```

## 向后兼容

如果配置中只有 `browser.base_url` 而没有 `verification` 字段：
- 自动视为 `verification.type: web`
- `verification.base_url` = `browser.base_url`

如果两者都没有，加载时抛出 `ValueError`。

## CLI 命令参考

### ai-loop init

```bash
ai-loop init [PROJECT_PATH] [OPTIONS]

选项：
  --name TEXT                 项目名称（省略则自动检测）
  --type [web|cli|library]    项目类型，默认 web
  --start-command TEXT        Dev server 启动命令
  --health-url TEXT           健康检查 URL
  --base-url TEXT             浏览器访问 URL
  --test-command TEXT         测试命令（CLI/library 项目）
  --run-example TEXT          CLI 示例命令（可重复）
  --goal TEXT                 初始目标（可重复）
  --description TEXT          项目描述
  --no-detect                 跳过自动检测
```

未提供的配置项会通过 Claude Code 自动检测（分析 package.json、pyproject.toml、Makefile 等）。检测失败时回退到交互式提问。

### ai-loop run

```bash
ai-loop run [PROJECT_PATH] [OPTIONS]

选项：
  --goal TEXT                      追加目标（可重复，仅运行时生效不持久化）
  -v, --verbose                    显示 Agent 执行详情（默认开启）
  -q, --quiet                      隐藏 Agent 执行详情
  --human-decision [low|high]      人类决策等级（覆盖 config.yaml）
```

每轮结束后提示：
- **c** — 继续下一轮
- **g** — 添加新目标后继续
- **s** — 停止

出错时额外选项：
- **r** — 重试本轮
