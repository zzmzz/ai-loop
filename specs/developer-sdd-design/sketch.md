## 目标

将 Developer 角色的 design 阶段改为强制调用 SDD 插件（`/sdd:sketch` 或 `/sdd:specify`），由 Developer 子进程根据需求规模自行选择，替换当前手写的设计 prompt。

## 推荐方案

1. 给 Developer 的 `allowedTools` 增加 `Skill` 和 `Agent` 权限，使其子进程能调用 `/sdd:sketch` 和 `/sdd:specify`
2. 重写 `_design_prompt()` — 指导 Developer 先判断需求规模，再调用对应 SDD skill，最后将产出写入 `{round_dir}/design.md`
3. 更新 `developer_claude.md` 模板中"阶段 1 - 设计"章节，保持 CLAUDE.md 与 prompt 一致
4. sketch/specify 有交互式提问能力（`AskUserQuestion`），与 ai-loop 的 `interaction_callback` 协作机制天然兼容 — Developer 子进程遇到不确定问题时通过 `{"needs_input": true}` 标记暂停，Orchestrator 将问题转发给人工

## 改动点

### 1. `ai_loop/orchestrator.py` — 增加工具权限

- **第 87 行** `self._runners["developer"]` 的 `allowed_tools` 从 `["Read", "Glob", "Grep", "Edit", "Write", "Bash"]` 改为 `["Read", "Glob", "Grep", "Edit", "Write", "Bash", "Skill", "Agent"]`

### 2. `ai_loop/roles/developer.py::_design_prompt()` — 重写设计 prompt

将当前的自由格式设计 prompt 替换为 SDD 流程引导：

```
你是开发者。当前阶段：技术设计。

需求文档已附在下方，无需再次读取。

请按以下步骤完成设计：

1. 评估需求规模：
   - 涉及 ≤3 个文件、改动意图清晰 → 中小需求
   - 涉及多模块、架构调整、不确定点多 → 大需求

2. 根据规模调用 SDD 工具：
   - 中小需求 → 调用 /sdd:sketch，传入需求摘要
   - 大需求 → 调用 /sdd:specify，传入需求摘要

3. SDD 工具会引导你完成探索和方案收敛。如果遇到需要产品决策的问题，
   在输出末尾附加 {"needs_input": true} 标记，等待回答后继续。

4. SDD 产出完成后，将最终方案整理写入：{round_dir}/design.md
   格式要求：目标 + 推荐方案 + 改动点（含文件路径） + 验证方式

文件头部：
---
round: {round_num}
role: developer
phase: design
result: null
timestamp: （当前时间 ISO 格式）
---
```

### 3. `ai_loop/templates/developer_claude.md` — 更新阶段 1 描述

将"阶段 1 - 设计（writing-plans 方法论）"章节改为"阶段 1 - 设计（SDD 方法论）"，内容对齐新 prompt：先评估规模 → 调用 `/sdd:sketch` 或 `/sdd:specify` → 产出 `design.md`

### 4. `ai_loop/context.py` — 无需改动

`PHASE_DEPS` 中 `developer:design` 依赖 `requirement.md` 不变，SDD skill 的探索由其自身在 Developer 子进程的工作目录内完成。sketch/specify 产生的中间文件（`specs/*/sketch.md` 等）留在 Developer workspace 里，最终方案写入 `design.md` 供后续阶段消费。

## 验证方式

- 单元测试：验证 `DeveloperRole._design_prompt()` 输出包含 `/sdd:sketch` 和 `/sdd:specify` 关键词
- 集成验证：在一个测试项目上跑 `ai-loop run`，确认 Developer design 阶段实际调用了 Skill 工具（可通过 verbose 日志中出现 `⚡ Skill` 事件确认）
- 回归检查：implement / verify / fix_review 阶段不受影响
