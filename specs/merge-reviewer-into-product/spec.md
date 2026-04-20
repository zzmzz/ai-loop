# Spec: 去掉 Reviewer 角色，Product 承担测试与验收

## 问题描述

当前 AI Loop 的 5 阶段流程中，Reviewer（阶段 4）和 Product 验收（阶段 5）职责分离：Reviewer 做代码审查，Product 做功能验收。实际运行中，Reviewer 的代码审查（代码风格、安全、测试覆盖等静态分析）增加了流程复杂度和 AI 调用成本，但对最终产品质量的贡献有限——真正有价值的是"功能是否正确"和"产品是否符合预期"。

参考 gstack 的 QA skill，Product 应该像 QA 工程师一样**主动测试、发现问题、分级处理、推动修复**，而不是仅仅被动验收。将 Reviewer 去掉，把"代码审查"+"产品验收"合并为一个更强大的「测试与验收」阶段，由 Product 角色统一负责。

## 目标用户

使用 AI Loop 自动化产品迭代的开发者和团队。他们期望更简洁的流程、更少的 AI 调用轮次、同时不损失质量保障。

---

## User Stories

### US-1: 去掉 Reviewer 角色

**As** AI Loop 使用者
**I want** 系统不再有独立的 Reviewer 角色
**So that** 流程更简洁，减少不必要的审查循环和 AI 调用成本

**Acceptance Scenarios:**

1. Orchestrator 初始化时不再创建 Reviewer 实例和 RoleRunner
2. `ai-loop init` 不再创建 `workspaces/reviewer/` 目录和模板
3. Brain 不再有 `post_review` 决策点
4. ContextCollector 不再有 `reviewer:review` 和 `developer:fix_review` 依赖
5. 编排流程中不再有独立的审查循环（原阶段 4）
6. 记忆更新不再包含 reviewer 角色
7. `review.md` 不再是流程产出物

**Edge Cases:**
- 已有 `.ai-loop/workspaces/reviewer/` 目录的旧项目升级时不应报错（向后兼容）
- 旧轮次中的 `review.md` 文件不影响新流程运行

### US-2: Product 新增「测试与验收」阶段（参考 gstack QA）

**As** AI Loop 使用者
**I want** Product 角色能像 gstack QA 一样主动测试产品
**So that** 测试更全面，问题发现更及时，最终产品质量更高

**Acceptance Scenarios:**

1. Product 新增 `qa_acceptance` 阶段，取代原来的 `acceptance` 阶段
2. 该阶段的工作流借鉴 gstack QA 的核心理念：
   - **系统化探索**：不仅验证需求条目，还主动探索产品寻找问题
   - **证据驱动**：每个发现都有截图/命令输出作为证据
   - **分级分类**：问题按严重级别（Critical/High/Medium/Low）分类
   - **健康评分**：产出整体健康评分（0-100）
3. 该阶段产出文件为 `acceptance.md`（保持原文件名，便于 Brain 兼容）
4. 产出文件包含：逐条需求验证结果 + 探索中发现的额外问题 + 健康评分 + 总判定

**Edge Cases:**
- Web 项目通过 Playwright 脚本测试，CLI 项目通过运行命令+测试套件测试
- 健康评分为 0 不自动判定 FAIL，仍以需求满足情况为准
- 探索中发现的非需求范围问题记录为"延迟池"，不影响本轮判定

### US-3: Product 发现 Critical 问题时自动推动修复

**As** AI Loop 使用者  
**I want** Product 发现 Critical 级别问题时，能自动把问题交给 Developer 修复并重新验证  
**So that** 严重问题不需要等到下一轮才修复

**Acceptance Scenarios:**

1. Product 完成测试后，Brain 基于 acceptance.md 做 `post_acceptance` 决策
2. 如果存在 Critical 问题，Brain 决策 `FAIL_IMPL`，触发 Developer 修复 → Product 重新测试的循环
3. 循环次数由 `limits.max_acceptance_retries` 控制（原字段复用，默认值保持 2）
4. 每次重新测试时，Product 只需验证上次失败的条目 + 受修复影响的区域，不用全量重测

**Edge Cases:**
- 如果 Developer 修复导致新的 Critical 问题（回归），也算一次 retry
- 连续 max_acceptance_retries 次仍未解决，ESCALATE 给人类
- 修复循环中，Product 需要运行完整测试套件确认无回归

### US-4: 给 Product 角色新增必要的工具权限

**As** AI Loop 使用者  
**I want** Product 角色拥有执行 QA 测试所需的全部工具  
**So that** Product 能独立完成测试、截图、运行命令、记录证据

**Acceptance Scenarios:**

1. Product 的 `allowed_tools` 从 `["Read", "Glob", "Grep", "Bash", "Write"]` 保持不变（Bash 已足够执行 Playwright 脚本和运行测试命令）
2. 若 Product 需要额外工具（如 Edit），在新阶段的 prompt 中明确指导使用 Bash 替代
3. Product 的 `qa_acceptance` prompt 中提供清晰的工具使用指导

**Edge Cases:**
- Product 在测试中不应修改源代码，修复由 Developer 负责
- Product 可以创建测试脚本文件（写入 notes/ 目录），但不修改项目代码

### US-5: 编排流程简化为 4 阶段

**As** AI Loop 使用者  
**I want** 编排流程从 5 阶段简化为 4 阶段  
**So that** 流程更清晰，执行更快

**Acceptance Scenarios:**

1. 新流程为：
   - 阶段 1：需求探索（product:explore）——不变
   - 阶段 2：技术设计（developer:design）——不变
   - 阶段 3：TDD 实现（developer:implement）——不变
   - 阶段 4：测试与验收（product:qa_acceptance）——**新**，替代原阶段 4+5
2. 轮次收尾（记忆更新、code-digest）——不变，但不再包含 reviewer
3. Brain 决策点调整：去掉 `post_review`，`post_acceptance` 保持但输入更丰富（包含健康评分信息）

**Edge Cases:**
- `limits.max_review_retries` 配置字段可以保留但不再使用，或直接废弃
- 旧 `config.yaml` 中包含 `max_review_retries` 字段时不报错

---

## 不做的事情

- **不引入浏览器自动化框架（gstack browse）**：继续使用 Playwright Python 脚本，不引入新的 browse 二进制
- **不做 Product 自动修复代码**：发现问题后 Product 只报告，由 Developer 修复
- **不做回归基线文件管理**：不引入 gstack 的 `baseline.json` 跨轮次回归对比机制
- **不修改 Developer 角色的任何行为**：Developer 的 design/implement/verify/fix_review 流程保持不变
- **不修改 Brain 的 round_summary 逻辑**：只是不再为 reviewer 角色生成记忆

---

## Business Metrics（可选）

- 单轮执行时间减少 20-30%（去掉了独立的审查循环）
- AI 调用次数减少（至少少 1-2 次 Claude 调用/轮）
- 问题发现率不低于原流程（通过更全面的功能测试弥补）
