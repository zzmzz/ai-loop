# 记忆与上下文管理

> 源文件：`ai_loop/memory.py`, `ai_loop/context.py`

AI Loop 通过两套机制解决跨轮次连续性问题：**累积记忆**（MemoryManager）保留历史认知，**上下文注入**（ContextCollector）传递当前轮次的阶段间产物。

## 累积记忆（MemoryManager）

每个角色的 `CLAUDE.md` 文件既是角色指南，也是累积记忆的载体。

### 数据结构

```markdown
# Role: product

（角色指南内容...）

## 累积记忆

### 历史摘要
（旧轮次的压缩摘要，由 Brain 生成）

### Round 003
- 添加了暗色模式 CSS 变量方案，验收通过

### Round 004
- 优化移动端导航栏，修复溢出问题

### Round 005
- 首屏加载优化，图片懒加载 + 代码分割
```

### 核心方法

#### append_memory(claude_md, round_num, content)

在 `## 累积记忆` 下追加指定轮次的记忆：
- 如果 `### Round NNN` 已存在，在该段末尾追加
- 如果不存在，新建段落

#### count_rounds(claude_md) → int

统计 CLAUDE.md 中 `### Round \d{3}` 的数量。

#### compact_memories(claude_md, window, summarizer)

当轮次数超过 `window`（默认 5）时执行压缩：

```
压缩前：
  ### 历史摘要（已有的旧摘要）
  ### Round 001  ←┐
  ### Round 002  ←┤ 这些被压缩
  ### Round 003  ←┘
  ### Round 004  ←┐
  ### Round 005  ←┤ 这些保留（最近 window 轮）
  ### Round 006  ←┘

压缩后：
  ### 历史摘要（旧摘要 + Round 001-003 的内容 → Brain 压缩为 ≤500 字）
  ### Round 004
  ### Round 005
  ### Round 006
```

`summarizer` 参数接收 `Brain.summarize_memories` 方法。

### 角色专属记忆

每轮结束时，Brain 的 `round_summary` 决策会在 `memories` 字段中为三个角色生成差异化的记忆：

| 角色 | 记忆侧重 |
|------|----------|
| product | 需求变更、用户反馈、验收结果 |
| developer | 技术决策、架构变更、代码模式 |
| reviewer | 审查发现的模式、反复出现的问题 |

Orchestrator 在 `_update_all_memories()` 中将专属记忆写入对应角色的 CLAUDE.md。如果 Brain 没有返回某角色的专属记忆，则使用通用 summary 兜底。

## 上下文注入（ContextCollector）

ContextCollector 在每个阶段自动将前序产物注入到角色的 prompt 中，避免角色手动读取文件。

### 依赖关系图

```
product:explore      → （无依赖，第一个阶段）
developer:design     → requirement.md
product:clarify      → design.md
developer:implement  → design.md, clarification.md
developer:verify     → requirement.md
reviewer:review      → requirement.md, design.md, dev-log.md
product:acceptance   → requirement.md, dev-log.md
developer:fix_review → review.md
```

### 注入格式

```markdown
---以下是前序阶段的关键产出，供你参考---

## requirement.md

（requirement.md 的完整内容）

## design.md

（design.md 的完整内容）
```

文件不存在时跳过（如 clarification.md 只在 CLARIFY 流程时产生）。

### 额外注入：code-digest.md

`product:explore` 阶段有一个特殊处理：Orchestrator 会额外检查 `code-digest.md` 是否存在，如果存在则追加到上下文中。这使得 Product 不需要每轮重新读取全量代码，只需关注增量变更。

## 代码摘要（code-digest.md）

每轮结束后，Orchestrator 收集两类信息交给 Brain 生成/更新摘要：

1. **目录树**：`find` 命令获取项目文件列表（排除 .git、.ai-loop、node_modules）
2. **Git diff**：`git diff HEAD~1 --stat` 获取最近变更统计

Brain 根据是否已有摘要选择不同策略：
- **首次**：生成完整的项目架构、主要模块、关键文件概述（≤1000 字）
- **更新**：只修改变更涉及的部分，保持其余不变

## 数据流总结

```
Round N-1 结束
  └→ Brain 生成角色专属记忆 → 写入各 CLAUDE.md
  └→ Brain 生成/更新 code-digest.md
  └→ 旧记忆超 window → compact_memories() 压缩

Round N 开始
  └→ Product 探索
      ├─ 读取 CLAUDE.md（含累积记忆）  ← Claude Code 自动读取
      └─ 注入 code-digest.md            ← ContextCollector + Orchestrator
  └→ Developer 设计
      ├─ 读取 CLAUDE.md
      └─ 注入 requirement.md            ← ContextCollector
  └→ Developer 实现
      ├─ 读取 CLAUDE.md
      └─ 注入 design.md + clarification.md  ← ContextCollector
  └→ ...
```
