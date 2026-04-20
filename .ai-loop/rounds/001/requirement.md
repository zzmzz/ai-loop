---
round: 1
role: product
phase: requirement
result: null
timestamp: 2026-04-14T20:45:00+08:00
---

# 需求：优化记忆与上下文存储机制

## 背景

ai-loop 在一个迭代轮次（round）中需要多个角色（Product、Developer、Reviewer）和 Brain 协作。每个阶段调用 Claude Code 子进程时，都通过两个途径向 AI 注入前序产出的上下文：

1. **ContextCollector**（`context.py`）在 Python 层读取文件内容，拼接进 prompt 字符串
2. **角色 prompt 模板**（`roles/*.py`）显式指示 Claude "阅读 xxx 文件"，Claude 再通过 Read 工具读一遍

两条路径读取的是同一批文件。此外 Brain 在每个决策点还会独立再读一遍相同文件。累积记忆（`## 累积记忆`）则只是往 CLAUDE.md 末尾追加文本，没有摘要、去重或分级机制，随着轮次增长会无限膨胀。

## 问题分析

| # | 问题 | 现状 | 影响 |
|---|------|------|------|
| 1 | 同一文件在单轮中被多次重复读取 | requirement.md 在一轮中至少被读取 10+ 次（ContextCollector 读、Claude Read 工具读、Brain 读） | token 浪费、延迟增加、API 成本放大 |
| 2 | ContextCollector 与 prompt 模板双重注入 | ContextCollector 把文件内容拼进 prompt，同时 prompt 还指示 Claude 用 Read 工具再读同一文件 | 上下文窗口中出现两份相同内容，浪费 token |
| 3 | 累积记忆无限膨胀 | `MemoryManager.append_memory()` 只追加不摘要，每轮追加的内容无字数限制 | 多轮后 CLAUDE.md 文件膨胀，system prompt 变长，可能超出上下文窗口 |
| 4 | 累积记忆内容粒度粗 | 所有角色收到的累积记忆是同一段 summary 文本（`_update_all_memories` 广播同一内容） | Developer 不需要产品体验细节，Product 不需要代码实现细节 |
| 5 | 项目代码每轮都要重新阅读 | Product:explore 阶段每轮都从零开始"阅读项目代码，理解当前功能和架构" | 重复消耗大量 token 去理解已知信息 |
| 6 | Brain 无缓存、重复读取 | Brain 在 6 个决策点分别独立调用 Claude，每次都指示从头读取 round 产出文件 | 同一 round 内产出文件被 Brain 累计读取 15+ 次 |

## 需求列表

### REQ-1: 消除 ContextCollector 与 prompt 模板的双重注入

**现状：** `ContextCollector.collect()` 把 `requirement.md` 等文件的完整内容拼入 prompt，同时角色 prompt 模板中还写着 `阅读需求文档：{round_dir}/requirement.md`，导致 Claude 子进程通过 Read 工具再读一遍同一个文件。最终 prompt + Claude 对话中出现两份相同文件内容。

**期望：** 选择 **一种** 注入策略并统一执行：
- **方案 A（推荐）**：ContextCollector 注入内容到 prompt，角色 prompt 模板中移除"阅读 xxx 文件"的指示，改为"以下前序产出已附在下方，无需再次读取"
- **方案 B**：废弃 ContextCollector，只在 prompt 模板中指示 Claude 按需读取文件

推荐方案 A，因为把内容直接放在 prompt 中省去一次 Read 工具调用的交互开销。

**验收标准：**
- 单个阶段中，同一产出文件只出现一次（在 prompt 中或通过 Read 工具，不可两者兼有）
- 现有 61 个测试全部通过

### REQ-2: Brain 决策上下文内联注入，减少重复 Read 调用

**现状：** `Brain.decide()` 只在 prompt 中列出文件路径（`- {fpath}`），然后让 Claude 通过 Read 工具读取。一个 round 中 Brain 被调用 6 次，每次都独立读取部分或全部 round 产出文件（requirement.md 出现在 5 个决策点中，被 Brain 读取 5 次）。

**期望：** Brain 调用时，直接在 prompt 中注入相关文件的内容（与 ContextCollector 类似），而非让 Claude 自行读取。这样 Brain 可以使用更少的工具权限（甚至不需要 Read 工具），并减少交互轮次。

**验收标准：**
- Brain prompt 中直接包含文件内容，不再依赖 Read 工具调用
- Brain 的 `allowed_tools` 可以减少为 `[]`（空列表）或只保留 `["Grep"]`
- 所有 Brain 相关测试通过

### REQ-3: 累积记忆增加滑动窗口和摘要机制

**现状：** `MemoryManager.append_memory()` 每轮在 CLAUDE.md 末尾追加一段 `### Round NNN` 文本，没有字数限制、没有过期机制。假设每轮 summary 平均 200 字，10 轮后累积记忆约 2000 字，50 轮后约 10000 字。

**期望：** 引入滑动窗口机制：
- 保留最近 N 轮（建议 N=5）的完整记忆
- 超出窗口的旧轮次合并为一段"历史摘要"（概括性描述，而非逐轮罗列）
- 在 `config.yaml` 的 `limits` 中新增配置项 `memory_window: 5`（默认值 5）

**验收标准：**
- 当轮次数 > memory_window 时，旧轮次自动合并为摘要段落
- CLAUDE.md 中累积记忆部分的总字数不超过合理上限（如 3000 字）
- 新增配置项 `memory_window` 可被正常加载
- 新增至少 2 个测试覆盖滑动窗口和摘要逻辑

### REQ-4: 角色专属记忆，替代广播式记忆

**现状：** `Orchestrator._update_all_memories()` 将 Brain 生成的同一段 summary 广播追加到所有 4 个角色的 CLAUDE.md 中。Product 收到的记忆可能包含"重构了 xyz 模块"这类细节，Developer 收到的记忆可能包含"用户体验不流畅"这类体验描述。

**期望：** 在 round_summary 阶段让 Brain 为不同角色生成差异化的记忆内容：
- **Product**：侧重需求变更、用户反馈、验收结果
- **Developer**：侧重技术决策、架构变更、代码模式
- **Reviewer**：侧重审查发现的模式、反复出现的问题

**验收标准：**
- Brain round_summary 输出包含按角色区分的记忆内容（如 JSON 中增加 `memories: {product: "...", developer: "...", reviewer: "..."}` 字段）
- 各角色 CLAUDE.md 只追加属于自己的记忆内容
- 新增测试验证角色记忆差异化

### REQ-5: 项目代码理解缓存——避免每轮从零阅读代码

**现状：** Product:explore 阶段的 prompt 指示 `阅读项目代码，理解当前功能和架构`。每轮迭代都从头阅读整个项目代码库，即使两轮之间项目代码变化很小。这导致大量 token 浪费在重复理解已知代码上。

**期望：** 在每轮结束时生成一份"项目代码摘要"（architecture digest），存储在 `.ai-loop/code-digest.md` 中，内容包括：
- 项目目录结构概要
- 关键模块/文件的功能描述
- 最近一轮修改涉及的文件列表

下一轮 Product:explore 阶段的 prompt 改为：
1. 先读取 `code-digest.md` 了解已知项目状态
2. 通过 `git diff` 查看自上轮以来的代码变更
3. 只针对变更部分深入阅读
4. 更新 `code-digest.md`

**验收标准：**
- 每轮结束时自动生成/更新 `code-digest.md`
- Product:explore prompt 优先引用 digest 而非指示全量阅读
- 第 2 轮及以后的 explore 阶段不再出现"阅读项目代码"的全量指示
- 新增测试覆盖 digest 生成和更新逻辑

## 优先级建议

| 优先级 | 需求 | 理由 |
|--------|------|------|
| P0 | REQ-1: 消除双重注入 | 改动最小、收益最直接，消除明确的 token 浪费 |
| P0 | REQ-2: Brain 内联注入 | 与 REQ-1 同类问题，可一并解决 |
| P1 | REQ-3: 记忆滑动窗口 | 防止多轮后系统退化，是可持续运行的基础 |
| P1 | REQ-5: 代码理解缓存 | 单轮节省的 token 量最大（项目代码 > 产出文件） |
| P2 | REQ-4: 角色专属记忆 | 提升记忆质量，但优先级低于解决量的问题 |

## 技术约束

- 所有改动不得破坏现有 61 个测试
- Python 3.9+ 兼容
- 不引入新的外部依赖（摘要可以通过 Brain/Claude 调用实现，不需要额外的 NLP 库）
