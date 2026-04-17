# AI Loop

**AI 驱动的产品迭代闭环框架** -- 让 AI Agent 分别扮演产品经理和开发者，自动完成 需求 -> 设计 -> 实现 -> 验收 的完整迭代循环。

## 为什么做这个

用 AI 写代码的人都有这个体验：**你变成了循环里最慢的那个环节**。

AI 几分钟就能写完一个功能，但你得花时间去看它写的对不对、逻辑有没有偏、是不是真的满足了你要的东西。然后反馈修改意见，再看一遍，再反馈... 你本质上变成了一个人肉 CI -- 不断在 "AI 实现" 和 "人工验收" 之间循环。

AI Loop 把 "人工循环" 变成 "AI 循环"，让 AI Agent 各自扮演产品经理和开发者，自动完成需求->实现->验收的闭环。人类从循环的执行者变成监督者 -- 只在 AI 搞不定的时候介入。

## 核心思路

- **双角色制衡** -- Product（需求探索 + QA 验收）、Developer（设计 + TDD 实现），工具权限互相隔离
- **Brain 决策** -- 独立裁判在关键决策点（需求评审、开发评审、验收评审、轮次总结）判断产出质量，驱动流程走向
- **有限重试 + ESCALATE** -- 验收最多 2 轮，超限自动升级给人类
- **人工协作** -- `human_decision: high` 模式下角色遇到歧义时暂停提问，通过 `{"needs_input": true}` 标记收集人类输入后继续
- **需求确认卡点** -- 非 low 模式下，Product 提出需求后暂停供人类审阅（接受 / 裁剪 / 拒绝重写）
- **持久记忆** -- CLAUDE.md 累积记忆 + 滑动窗口压缩，跨轮次保持上下文连贯；Brain 为各角色生成差异化记忆；包版本升级时自动刷新模板正文并保留累积记忆
- **产品认知库** -- `.ai-loop/product-knowledge/` 由 Product 维护（索引 + 按业务域拆分的 Markdown），每轮探索和验收时自动注入上下文
- **结构化日志** -- `.ai-loop/logs/round-*.jsonl` 记录阶段切换、AI 调用与结果统计、Brain 决策及用户交互，便于复盘与排错
- **崩溃恢复** -- 每个阶段持久化 phase，异常后可从中断点恢复

## 架构总览

```
                    ┌─────────────────┐
                    │   Orchestrator  │  ← 编排器：驱动整个流程
                    └────────┬────────┘
                             │
                    ┌────────┼────────┐
                    │                 │
                    ▼                 ▼
          ┌──────────────┐   ┌──────────────┐
          │   Product    │   │  Developer   │
          │   Agent      │   │  Agent       │
          │              │   │              │
          │ 需求探索      │   │ 设计+TDD实现  │
          │ QA测试+验收   │   │ 审查修复      │
          └──────────────┘   └──────────────┘
                    │                 │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     Brain       │  ← 独立裁判
                    └─────────────────┘
```

一轮迭代：产品探索 → 需求确认 → 开发（设计+实现+自验） → QA 验收（≤2 轮） → 记忆更新

> 详细架构、数据流、各组件交互见 [docs/architecture.md](docs/architecture.md)

## 快速开始

### 安装

```bash
pip install -e .

# 浏览器自动化（web 项目的产品经理角色需要）
pip install -e ".[browser]"
playwright install chromium
```

前置条件：[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 可用。

### 初始化

```bash
# Web 项目（自动检测配置）
ai-loop init /path/to/your/project

# CLI 项目
ai-loop init . --type cli --test-command "python -m pytest"

# Library 项目
ai-loop init . --type library --test-command "python -m pytest"
```

初始化会自动通过 Claude Code 分析项目结构，检测启动命令、健康检查 URL、测试命令等配置项，并在 `.ai-loop/` 下创建完整的工作目录。

### 运行

```bash
ai-loop run .                              # verbose 模式（默认）
ai-loop run . --quiet                      # 安静模式
ai-loop run . --goal "优化首屏加载速度"     # 追加目标
ai-loop run . --human-decision high        # 人工协作模式
```

运行后进入循环：每轮结束后可选择 `[c]` 继续下一轮、`[g]` 添加目标后继续、`[s]` 停止。遇到 ESCALATE 时暂停等待人类决策。

## 一轮迭代详细流程

```
Round N 开始
│
├─ 1. Product 探索  ─→ requirement.md  ─→ 人工确认卡点*  ─→ Brain: post_requirement
│      (启动 Server)   (每轮最多3条需求)    (* human_decision   ├─ PROCEED → 继续
│                                            != "low" 时触发)  └─ REFINE  → 重写
│
├─ 2. Developer 开发 ─→ design.md      ─→ Brain: post_development
│      (SDD sketch/   + dev-log.md         ├─ PROCEED → 继续
│       specify)                            └─ RETRY   → 补完
│
├─ 3. Product QA 验收 ─→ acceptance.md ─→ Brain: post_acceptance
│      (系统化测试)      (最多 2 轮)        ├─ PASS       → 完成
│                                          ├─ PARTIAL_OK → 完成（遗留下轮）
│                                          ├─ FAIL_IMPL  → Developer 修复 → 重新验收
│                                          ├─ FAIL_REQ   → Product 重探索 → 重新实现
│                                          └─ ESCALATE   → 人类介入
│
├─ 4. Brain 总结     ─→ 角色专属记忆写入 CLAUDE.md
│                    ─→ code-digest.md 更新
│
└─ 状态推进 → Round N+1
```

## 组件说明

| 组件 | 源文件 | 职责 |
|------|--------|------|
| **Orchestrator** | `orchestrator.py` | 驱动整体流程、管理 Server 生命周期、调度角色和 Brain、崩溃恢复 |
| **Brain** | `brain.py` | 决策点的独立裁判，代码摘要生成，记忆压缩 |
| **RoleRunner** | `roles/base.py` | Claude Code CLI 双向流式 JSON 通信封装 |
| **ProductRole** | `roles/product.py` | 需求探索、澄清、QA 测试+验收（区分 web/cli）；维护产品认知库 |
| **DeveloperRole** | `roles/developer.py` | 技术设计（SDD sketch/specify）、TDD 实现、审查修复 |
| **MemoryManager** | `memory.py` | 累积记忆追加、滑动窗口压缩、模板刷新 |
| **ContextCollector** | `context.py` | 阶段间产物自动注入（如将 requirement.md 注入 developer:develop） |
| **EventLogger** | `logger.py` | 每轮 JSONL 结构化事件日志 |
| **DevServer** | `server.py` | Dev Server 启动/健康检查/端口占用清理/停止 |
| **AiLoopConfig** | `config.py` | 配置加载校验，支持 web/cli/library 三种项目类型 |
| **LoopState** | `state.py` | 轮次/阶段状态持久化，版本追踪 |

## Claude Code 集成方式

AI Loop 不直接调用 LLM API，而是把 Claude Code CLI 当运行时：

```python
cmd = [
    "claude",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "--permission-prompt-tool", "stdio",
    "--allowedTools", "Read,Glob,...",  # 角色专属工具权限
]
proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, cwd=workspace)
```

**隔离机制**：
- **工具隔离** -- Product：`Read`/`Glob`/`Grep`/`Bash`/`Write`；Developer：`Read`/`Glob`/`Grep`/`Edit`/`Write`/`Bash`/`Skill`/`Agent`
- **上下文隔离** -- 每个角色有独立的 CLAUDE.md 工作空间
- **双向通信** -- stream-json 格式实现 prompt → result → follow-up 多轮对话

## 运行时文件结构

```
.ai-loop/
├── config.yaml                 # 项目配置
├── state.json                  # 迭代状态（轮次、阶段、版本）
├── server.log                  # Dev Server 日志
├── code-digest.md              # 代码结构摘要（Brain 生成，每轮更新）
├── product-knowledge/          # 产品认知库（index.md + 业务域子文档）
├── logs/                       # 结构化事件日志（round-NNN.jsonl）
├── rounds/
│   ├── 001/
│   │   ├── requirement.md      # 需求文档
│   │   ├── design.md           # 技术设计
│   │   ├── dev-log.md          # 开发日志
│   │   └── acceptance.md       # QA 测试 + 验收结果
│   └── 002/ ...
└── workspaces/
    ├── orchestrator/CLAUDE.md  # 编排器上下文 + 累积记忆
    ├── product/
    │   ├── CLAUDE.md           # 产品经理上下文 + 累积记忆
    │   └── notes/              # 截图、证据
    └── developer/
        ├── CLAUDE.md           # 开发者上下文 + 累积记忆
        └── notes/
```

## 文档

| 文档 | 说明 |
|------|------|
| [docs/architecture.md](docs/architecture.md) | 系统架构、组件关系、数据流 |
| [docs/orchestration.md](docs/orchestration.md) | 编排引擎完整流程、重试/升级/协作机制 |
| [docs/brain.md](docs/brain.md) | Brain 决策点、JSON schema |
| [docs/roles.md](docs/roles.md) | RoleRunner + 双角色详解 |
| [docs/memory-context.md](docs/memory-context.md) | 累积记忆、滑动窗口压缩、ContextCollector |
| [docs/development.md](docs/development.md) | 开发环境、测试规范 |

## 技术栈

- **Python 3.10+** / **Claude Code CLI** / **Click** / **PyYAML** / **Requests** / **Playwright** (可选)

## License

MIT
