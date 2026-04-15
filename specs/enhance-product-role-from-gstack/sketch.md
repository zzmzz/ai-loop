## 目标

从 gstack 的设计中提炼可吸收的模式，增强 ai-loop 产品角色的结构化程度和实际效果。

## 分析：gstack vs ai-loop 产品角色对比

### 当前 ai-loop 产品角色的特点
- 单一 ProductRole，覆盖 explore / clarify / acceptance 三个阶段
- prompt 偏自由——给了"你是产品经理"的身份，但缺乏具体方法论
- 需求探索靠 LLM 自由发挥，质量波动大
- 验收只有 PASS/FAIL 二元结果，缺乏分级

### gstack 的核心差异（值得吸收的）
gstack 没有单独"产品角色"，而是把产品工作拆成多个专家，每个专家有**结构化方法论**。

---

## 可吸收的 6 个模式

### 1. 结构化需求探索（来自 /office-hours 的 Forcing Questions）

**现状**：ai-loop 的 `product:explore` prompt 只说"找出值得改进的点"，LLM 容易泛泛而谈。

**gstack 做法**：`/office-hours` 用 6 个强制问题逼出需求本质：
- 谁是目标用户？他们现在怎么解决这个问题？
- 现状方案有什么痛点？
- 最窄的切入点是什么？
- 什么证据表明这个需求存在？
- 验收标准是什么？

**建议吸收方式**：在 `_explore_prompt_web/cli` 中加入 3-4 个强制问题框架，要求产品角色在输出 requirement.md 前先回答这些问题。不是增加新阶段，而是增强现有 explore 的 prompt。

**改动点**：
- `ai_loop/roles/product.py::_explore_prompt_web` — prompt 中增加强制问题框架
- `ai_loop/roles/product.py::_explore_prompt_cli` — 同上
- `ai_loop/templates/product_claude.md` — 需求阶段增加方法论说明

### 2. 需求分级与验收分级（来自 /qa 的 Severity Tiers）

**现状**：验收只有 PASS/FAIL，没有 bug 严重性分级。Brain 需要自己判断"部分通过"怎么处理。

**gstack 做法**：`/qa` 将问题分为 Critical / High / Medium / Cosmetic，三个测试档位（Quick/Standard/Exhaustive）。

**建议吸收方式**：
- requirement.md 中每条需求增加优先级标签（P0/P1/P2）
- acceptance.md 中对每条需求给出 PASS/FAIL + 严重性分级
- result 增加 PARTIAL 状态（P0 全过 + P1 有未过 = PARTIAL）
- Brain 的 post_acceptance 决策可以利用分级信息

**改动点**：
- `ai_loop/roles/product.py::_explore_prompt_web/cli` — 要求需求带优先级
- `ai_loop/roles/product.py::_acceptance_prompt_web/cli` — 要求逐条给严重性
- `ai_loop/templates/product_claude.md` — 输出格式说明增加优先级和严重性字段
- `ai_loop/brain.py` (post_acceptance 相关) — 可能需要适配 PARTIAL 状态

### 3. Learnings 持久化（来自 /learn）

**现状**：ai-loop 有 CLAUDE.md 累积记忆（memory.py 管理），但是记忆是自然语言堆积，没有结构化的"教训"记录，也无法跨轮快速检索"之前遇到过类似问题吗"。

**gstack 做法**：每个 skill 结束后自动反思失败点，写入 `learnings.jsonl`。下次启动时 surface 相关教训。

**建议吸收方式**：这个可以作为 memory.py 的增强——在每轮结束时，让 Brain 在生成 round_summary 的同时，提取 structured learnings 写入 `learnings.jsonl`。产品角色在 explore 阶段可以检索相关 learnings。

**改动点**：
- 新增 `ai_loop/learnings.py` — JSONL 读写 + 相似性检索
- `ai_loop/brain.py::round_summary` — 生成 summary 时同时输出 learnings
- `ai_loop/roles/product.py::_explore_prompt_*` — prompt 中注入相关 learnings（如有）
- `ai_loop/orchestrator.py` — 轮结束时调用 learnings 记录

### 4. 设计文档作为共享契约（来自 /office-hours → design doc → 全链路使用）

**现状**：ai-loop 的 requirement.md 是产品→开发的主要契约，但格式自由，缺乏结构。开发者和审查者对需求理解可能不一致。

**gstack 做法**：`/office-hours` 输出标准化的 design doc，包含 Problem / Solution / Non-goals / Success Metrics / Technical Approach，全链路共享。

**建议吸收方式**：为 requirement.md 定义一个轻量模板结构：
```markdown
## 问题描述
## 目标用户
## 解决方案概要
## 具体需求（带优先级）
## 不做的事情（Non-goals）
## 验收标准
```

**改动点**：
- `ai_loop/roles/product.py::_explore_prompt_web/cli` — 要求按模板输出 requirement.md
- `ai_loop/templates/product_claude.md` — 新增需求模板说明

### 5. 多视角 Plan Review（来自 /plan-ceo-review + /plan-eng-review 的 review gauntlet）

**现状**：ai-loop 的 design.md 由 developer 独自产出，Brain 只做 PROCEED/CLARIFY/REDO 的粗粒度决策，缺乏多视角审视。

**gstack 做法**：design doc 经过 CEO（战略）、Eng Manager（架构）、Designer（设计）、DX Lead（开发体验）多角度审视，每个角度用不同评估框架。

**建议吸收方式**：这个不适合直接搬（ai-loop 的循环已经有 product+developer+reviewer+brain 四角色），但可以增强 Brain 的 post_design 决策——让 Brain 不只是判断"通过不通过"，而是从产品、技术、风险三个维度各打分并给出建议。

**改动点**：
- `ai_loop/brain.py` (post_design 决策逻辑) — 增加多维度评估 prompt
- 这是 Brain prompt 的增强，不需要新增角色

### 6. 验证驱动的证据链（来自 /qa 的 before/after screenshots + evidence）

**现状**：ai-loop 产品角色的截图是 prompt 中提到但没有强制的，验收报告是纯文字。

**gstack 做法**：`/qa` 每个 bug 修复都有 before/after 截图作为证据，验收报告附带可验证的证据链。

**建议吸收方式**：在 acceptance prompt 中强制要求截图命名规则和对比格式：
- `notes/accept-{需求编号}-before.png`
- `notes/accept-{需求编号}-after.png`
- acceptance.md 中每条验收结果附截图路径

**改动点**：
- `ai_loop/roles/product.py::_acceptance_prompt_web` — 强制截图命名和引用规则
- `ai_loop/templates/product_claude.md` — 验收阶段增加证据格式说明

---

## 推荐实施优先级

| 优先级 | 模式 | 复杂度 | 价值 |
|--------|------|--------|------|
| P0 | 1. 结构化需求探索（Forcing Questions） | 低（改 prompt） | 高 |
| P0 | 4. 需求模板结构化 | 低（改 prompt） | 高 |
| P1 | 2. 需求/验收分级 | 中（改 prompt + Brain 适配） | 高 |
| P1 | 6. 验证证据链 | 低（改 prompt） | 中 |
| P2 | 5. Brain 多维度 review | 中（改 Brain prompt） | 中 |
| P2 | 3. Learnings 持久化 | 高（新模块） | 中 |

## 验证方式

- P0 改动（prompt 增强）：跑一轮 ai-loop，对比改前改后的 requirement.md 质量——是否更具体、更结构化、更可执行
- P1 改动（分级）：验证 acceptance.md 包含优先级和严重性字段，Brain 能正确解析 PARTIAL 状态
- P2 改动（learnings）：验证 learnings.jsonl 能正确写入和检索

## 不做的事情

- **不引入新角色**：gstack 的多专家模式适合它的架构（Claude Code skills），但 ai-loop 的四角色制衡已经够用，增加角色会增加 token 消耗和调度复杂度
- **不引入浏览器守护进程**：gstack 的 browse 服务器（persistent Chromium daemon）适合高频 QA 场景，ai-loop 用 Playwright 脚本够了
- **不引入 /autoplan 自动审查流水线**：ai-loop 已有 Brain 做决策枢纽，不需要另一套
- **不搬 design system（DESIGN.md）**：ai-loop 不专注 UI 设计，不需要字体/颜色/间距系统

## 技术风险

1. prompt 增强可能导致产品角色输出变长、token 消耗增加——需要控制模板长度
2. PARTIAL 状态引入需要 Brain 和 Orchestrator 联动修改——需要确认 Brain 的 post_acceptance 决策逻辑兼容
3. Learnings 持久化是最大改动，建议放最后，先验证 prompt 增强效果
