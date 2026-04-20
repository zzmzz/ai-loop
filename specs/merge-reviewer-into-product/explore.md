# Explore: 去掉 Reviewer 角色，Product 承担测试与验收

## Reviewer 角色的完整依赖图

### [事实] 代码中 Reviewer 的 6 个触点

1. **`ai_loop/roles/reviewer.py`** — `ReviewerRole` 类，唯一阶段 `review`，产出 `review.md`
2. **`ai_loop/orchestrator.py`**:
   - L17: `from ai_loop.roles.reviewer import ReviewerRole`
   - L47: `_ROLE_TEMPLATE_MAP` 含 `"reviewer": "reviewer_claude.md"`
   - L95: `self._reviewer = ReviewerRole()`
   - L100: `self._runners["reviewer"]` — 工具权限 `["Read", "Glob", "Grep", "Bash"]`
   - L181-194: **Review loop**（阶段 4）— 调用 `reviewer:review`、`developer:fix_review`、`developer:verify`
   - L245: `_call_role` 的 `role_map` 含 `"reviewer": self._reviewer`
   - L451: `_update_all_memories` 遍历 4 个角色含 `"reviewer"`
3. **`ai_loop/context.py`** — `PHASE_DEPS` 含两个 reviewer 相关条目：
   - `"reviewer:review": ["requirement.md", "design.md", "dev-log.md"]`
   - `"developer:fix_review": ["review.md"]`
4. **`ai_loop/brain.py`** — 3 个触点：
   - `DECISION_POINT_FILES["post_review"]`: `["requirement.md", "review.md"]`
   - `DECISION_POINT_INSTRUCTIONS["post_review"]`: APPROVE/REWORK/SKIP_MINOR/ESCALATE
   - `DECISION_POINT_INSTRUCTIONS["round_summary"]`: memories 含 `"reviewer"` 键
   - `DECISION_POINT_FILES["round_summary"]`: 含 `"review.md"`
5. **`ai_loop/templates/reviewer_claude.md`** — Reviewer 的 CLAUDE.md 模板
6. **`ai_loop/cli.py`** — L140-144: `role_template_map` 含 `"reviewer"`

### [事实] Developer 的 `fix_review` 阶段

`DeveloperRole._fix_review_prompt` 专门用于处理审查反馈。去掉 Reviewer 后：
- `fix_review` 阶段不再被 Orchestrator 调用（当前仅在 review loop 中调用）
- 但 **不应从 DeveloperRole 中删除**（spec 明确说"不修改 Developer 角色的任何行为"）
- `PHASE_DEPS["developer:fix_review"]` 可以保留也可删除，因为不再被调用

### [事实] State 中的 reviewer 引用

`ai_loop/state.py`:
- `LoopState.retry_counts` 默认值 `{"review": 0, "acceptance": 0}`
- `complete_round()` 重置 `retry_counts` 为相同值
- `increment_retry("review")` 在当前代码中**未被 orchestrator 直接调用**（orchestrator 用 for 循环计数而非 state.increment_retry）

## Product 当前 acceptance 实现分析

### [事实] ProductRole 的验收 prompt 结构

`ai_loop/roles/product.py` L227-307:
- `_acceptance_prompt` 分 web/cli 两种
- Web: Playwright 脚本逐条验证 → before/after 截图
- CLI: 运行测试 + 示例命令 → 保存输出为证据
- 结果判定：PASS / PARTIAL / FAIL（基于 P0/P1/P2 优先级）
- **不做主动探索**，仅被动验证需求条目

### [事实] Product 工具权限

`orchestrator.py` L98: `["Read", "Glob", "Grep", "Bash", "Write"]`
- Bash 足以执行 Playwright 脚本和运行测试命令
- Write 仅限写入 notes/ 目录和 product-knowledge/ 目录
- **无 Edit 权限**（不能修改源代码）

### [事实] product_claude.md 模板结构

模板中有占位符 `{project_path}`, `{project_description}`, `{goals}`, `{base_url}`。
但这些占位符**不在 `ProductRole.build_prompt()` 中渲染**，模板仅用作 CLAUDE.md 的初始内容，不作为 prompt 的一部分。实际 prompt 完全由 `_*_prompt` 方法生成。

## Brain 决策系统分析

### [事实] post_acceptance 决策点

`brain.py` L36-40:
- 输入文件: `["requirement.md", "acceptance.md"]`
- 可选决策: PASS / PARTIAL_OK / FAIL_IMPL / FAIL_REQ / ESCALATE
- **不需要修改**，但 instruction 可增强以识别健康评分

### [事实] post_review 决策点

`brain.py` L29-33:
- 输入文件: `["requirement.md", "review.md"]`
- 可选决策: APPROVE / REWORK / SKIP_MINOR / ESCALATE
- **需要完全删除**

### [事实] round_summary 中的 reviewer 引用

`brain.py` L42-51:
- `DECISION_POINT_FILES["round_summary"]` 含 `"review.md"`（需删除）
- `DECISION_POINT_INSTRUCTIONS["round_summary"]` 的 memories 模板含 `"reviewer"` 键（需删除）

## Orchestrator 流程变更分析

### [事实] Review loop（L181-194）需要整体删除

```
# 当前阶段 4
self._server_start()
for attempt in range(max_review + 1):
    self._call_role("reviewer:review", ...)
    decision = self._ask_brain("post_review", ...)
    if decision in ("APPROVE", "SKIP_MINOR"): break
    if decision == "ESCALATE": return self._escalate(...)
    if attempt < max_review:
        self._call_role("developer:fix_review", ...)
        self._call_role("developer:verify", ...)
```

删除后，server 的启动时机需调整：当前 review loop 开头 `_server_start()`，acceptance loop 直接紧跟其后不重新启动。新流程中 server 应在新阶段 4（测试与验收）开始前启动。

### [事实] Acceptance loop（L197-215）需要改造

当前调用 `product:acceptance`，改为调用 `product:qa_acceptance`。其他逻辑（FAIL_IMPL/FAIL_REQ 分支）保持不变。

### [推断] Server 生命周期简化

当前：阶段 1 启动→停止，阶段 4 启动→阶段 5 结束后停止。
新流程：阶段 1 启动→停止，阶段 4（新）启动→结束后停止。逻辑更简洁。

## 测试代码影响面

### [事实] 需要修改的测试文件

1. **`tests/conftest.py`**: fixture 中创建 `reviewer` workspace、`retry_counts` 含 `"review"`
2. **`tests/test_orchestrator.py`**: `brain_side_effect` 含 `post_review` 分支、断言 `reviewer:review`、`test_review_rework_loop` 测试类
3. **`tests/test_roles.py`**: `TestReviewerRole`、`TestReviewerRoleContext` 两个测试类、import `ReviewerRole`
4. **`tests/test_context.py`**: `reviewer:review` 依赖测试
5. **`tests/test_brain.py`**: `post_review` 决策测试、`round_summary` 中 reviewer 记忆
6. **`tests/test_state.py`**: `retry_counts` 含 `"review"`、`increment_retry("review")`
7. **`tests/test_cli.py`**: `init` 后断言 reviewer workspace 存在
8. **`tests/test_integration.py`**: 完整流程中的 reviewer 相关逻辑
9. **`tests/test_config.py`**: `max_review_retries` 相关断言

## 新 qa_acceptance prompt 设计要点

### [推断] 参考 gstack QA 的核心要素

基于 gstack QA skill 分析，新 prompt 需要融入以下要素：
1. **系统化探索**：不仅验证需求，还要主动探索产品各页面/功能
2. **证据驱动**：每个发现必须有截图或命令输出
3. **问题分级**：Critical / High / Medium / Low
4. **健康评分**：0-100 分制，综合需求满足度和探索发现
5. **结构化输出**：需求验证表 + 额外发现列表 + 健康评分 + 总判定

### [推断] 不需要的 gstack 要素

- Browse daemon（用 Playwright 代替）
- Baseline.json 跨轮次对比
- 自动 atomic commit fix（由 Developer 负责）
- WTF-likelihood 评估（简化为严重级别）

## config.yaml 兼容性

### [事实] `max_review_retries` 字段处理

`ai_loop/config.py` L30: `LimitsConfig.max_review_retries: int = 3`
- 已有默认值，旧配置即使包含此字段也不会报错
- 新代码不再读取此字段即可，不需要删除
- Spec 允许保留但不使用，为最小改动方案

### [待确认] 是否需要废弃警告

旧项目升级时，config 中 `max_review_retries` 是否需要打印 deprecation warning？基于 spec "旧配置不报错" 的要求，可以不加。
