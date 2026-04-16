# 系统架构

## 设计原则

1. **角色制衡优于单点万能** — 分离的角色互相挑战，比单个 Agent 自洽的输出更可靠
2. **有限自治优于完全自治** — 重试上限 + ESCALATE 机制，人类始终在循环中
3. **证据优于断言** — 贴命令输出，禁用"应该可以""看起来没问题"
4. **TDD 作为质量锚点** — RED → GREEN → REFACTOR，测试是前提而非补充
5. **记忆驱动连续性** — CLAUDE.md 累积记忆，多轮迭代保持上下文连贯

## 组件总览

```
                    ┌─────────────────┐
                    │   Orchestrator  │  ← 编排器：驱动整个流程
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌───────────┐    ┌──────────────┐   ┌───────────┐
    │  Product   │    │  Developer   │   │ Reviewer  │
    │  Agent     │    │  Agent       │   │ Agent     │
    │            │    │              │   │           │
    │ Playwright │    │ TDD + Code   │   │ 5维审查    │
    │ 浏览器体验  │    │ 编辑写测试    │   │ 只读分析   │
    └───────────┘    └──────────────┘   └───────────┘
            │                │                │
            └────────────────┼────────────────┘
                             │
                    ┌────────▼────────┐
                    │     Brain       │  ← 决策大脑：每个阶段做判断
                    │  (独立裁判)      │
                    └────────┬────────┘
                             │
                 PROCEED / REFINE / REDO
                 APPROVE / REWORK / ESCALATE
```

## 组件职责

| 组件 | 源文件 | 职责 | 详细文档 |
|------|--------|------|----------|
| **Orchestrator** | `orchestrator.py` | 驱动流程、管理 Server、调度角色和 Brain | [编排引擎](orchestration.md) |
| **Brain** | `brain.py` | 6 个决策点的独立裁判，代码摘要生成，记忆压缩 | [决策系统](brain.md) |
| **RoleRunner** | `roles/base.py` | Claude Code CLI 流式 JSON 双向通信封装 | [角色系统](roles.md) |
| **ProductRole** | `roles/product.py` | 需求探索、澄清、验收（区分 web/cli）；维护 `.ai-loop/product-knowledge/` 认知库 | [角色系统](roles.md) |
| **DeveloperRole** | `roles/developer.py` | 技术设计、TDD 实现、审查修复 | [角色系统](roles.md) |
| **ReviewerRole** | `roles/reviewer.py` | 5 维代码审查 | [角色系统](roles.md) |
| **MemoryManager** | `memory.py` | 累积记忆追加、滑动窗口压缩；包版本变化时刷新 CLAUDE.md 模板段（保留 `## 累积记忆` 之后） | [记忆与上下文](memory-context.md) |
| **ContextCollector** | `context.py` | 阶段间产物自动注入 | [记忆与上下文](memory-context.md) |
| **AiLoopConfig** | `config.py` | 配置加载校验，支持 web/cli/library | [配置参考](config-reference.md) |
| **LoopState** | `state.py` | 轮次/阶段/重试状态持久化；`ai_loop_version` 记录上次成功对齐模板时所用的包版本 | — |
| **DevServer** | `server.py` | Dev Server 启动/健康检查/停止 | — |
| **EventLogger** | `logger.py` | 每轮 JSONL 结构化事件（阶段、AI 调用/结果、Brain、用户交互、错误） | [编排引擎](orchestration.md) |
| **detect** | `detect.py` | 通过 Claude Code 自动检测项目配置 | — |

## 运行时依赖关系

```
CLI (cli.py)
 └→ Orchestrator
     ├→ AiLoopConfig + LoopState     ← 配置与状态
     ├→ EventLogger                   ← `.ai-loop/logs/round-*.jsonl` 事件流
     ├→ DevServer (可选)              ← web 项目才需要
     ├→ Brain                         ← 决策（内部有独立 RoleRunner）
     ├→ MemoryManager                 ← 记忆管理
     ├→ ContextCollector              ← 上下文注入
     ├→ ProductRole + RoleRunner      ← 产品经理
     ├→ DeveloperRole + RoleRunner    ← 开发者
     └→ ReviewerRole + RoleRunner     ← 审查者
```

每个 RoleRunner 通过 `claude --output-format stream-json --input-format stream-json` 与 Claude Code CLI 进行双向通信。角色对象（ProductRole 等）负责构建 prompt，RoleRunner 负责执行调用和解析输出。

## 数据流：一轮完整迭代

```
Round N 开始
│
├─ 1. Product 探索  ─→ requirement.md  ─→ 人工确认卡点*  ─→ Brain: post_requirement
│      (启动 Server)   (每轮最多3条需求)    (* human_decision   ├─ PROCEED → 继续
│                                            != "low" 时触发)  └─ REFINE  → Product 重写 → 再确认
│
├─ 2. Developer 设计 ─→ design.md      ─→ Brain: post_design
│      (注入 requirement.md)                ├─ PROCEED → 继续
│                                           ├─ CLARIFY → Product 回答 → 重新设计
│                                           └─ REDO    → 重新设计
│
├─ 3. Developer 实现 ─→ dev-log.md     ─→ Brain: post_implementation
│      (注入 design.md)                     ├─ PROCEED → 继续
│                                           └─ RETRY   → 补完
│
├─ 4. Reviewer 审查  ─→ review.md      ─→ Brain: post_review
│      (注入 requirement + design + dev-log) ├─ APPROVE    → 继续
│      (最多 3 轮)                           ├─ SKIP_MINOR → 继续
│                                           ├─ REWORK     → Developer 修复 → 重新审查
│                                           └─ ESCALATE   → 人类介入
│
├─ 5. Product 验收   ─→ acceptance.md  ─→ Brain: post_acceptance
│      (注入 requirement + dev-log)          ├─ PASS       → 完成
│      (最多 2 轮)                           ├─ PARTIAL_OK → 完成（下轮处理）
│                                           ├─ FAIL_IMPL  → Developer 修复 → 重新验收
│                                           ├─ FAIL_REQ   → Product 重探索 → 重新实现
│                                           └─ ESCALATE   → 人类介入
│
├─ 6. Brain 总结     ─→ 角色专属记忆写入 CLAUDE.md
│                    ─→ code-digest.md 更新
│
└─ 状态推进 → Round N+1
```

## 文件系统布局（运行时）

```
.ai-loop/
├── config.yaml                 # 项目配置
├── state.json                  # 迭代状态（当前轮次、重试计数、历史、ai_loop_version）
├── server.log                  # Dev Server 日志
├── code-digest.md              # 代码结构摘要（Brain 生成，每轮更新）
├── product-knowledge/          # Product 维护的产品认知（index.md + 业务域子文档）
├── logs/                       # 结构化事件日志（每轮 round-NNN.jsonl）
├── rounds/
│   ├── 001/
│   │   ├── requirement.md      # 需求文档（Product 输出）
│   │   ├── design.md           # 技术设计（Developer 输出）
│   │   ├── clarification.md    # 澄清回答（Product 输出，可选）
│   │   ├── dev-log.md          # 开发日志（Developer 输出）
│   │   ├── review.md           # 审查报告（Reviewer 输出）
│   │   └── acceptance.md       # 验收结果（Product 输出）
│   └── 002/
│       └── ...
└── workspaces/
    ├── orchestrator/CLAUDE.md  # 编排器上下文 + 累积记忆
    ├── product/
    │   ├── CLAUDE.md           # 产品经理上下文 + 累积记忆
    │   └── notes/              # 截图、证据等
    ├── developer/
    │   ├── CLAUDE.md
    │   └── notes/
    └── reviewer/
        ├── CLAUDE.md
        └── notes/
```

## Claude Code 集成方式

AI Loop 不自己调用 LLM API，而是把 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 当运行时：

```python
# 每个角色 = 一次受控的 Claude Code 双向会话
cmd = [
    "claude",
    "--output-format", "stream-json",   # 流式 JSON 输出
    "--input-format", "stream-json",    # 流式 JSON 输入（支持多轮）
    "--permission-prompt-tool", "stdio", # 权限请求走 stdin
    "--allowedTools", "Read,Glob,...",  # 角色专属工具权限
]
proc = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, cwd=workspace)
```

**隔离机制**：
- **工具隔离** — Product：`Read`/`Glob`/`Grep`/`Bash`/`Write`（`Write` 仅用于写入 `product-knowledge/`）；Developer 能 `Edit`+`Write`+`Bash` 等；Reviewer 只读
- **上下文隔离** — 每个角色有独立的 CLAUDE.md 工作空间
- **双向通信** — 通过 stream-json 格式实现 prompt → result → follow-up 的多轮对话
