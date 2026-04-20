# Tasks: 去掉 Reviewer 角色，Product 承担测试与验收

**Workspace**: `merge-reviewer-into-product` | **Date**: 2026-04-16
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Explore**: [explore.md](explore.md)

---

## Phase 1: 删除 Reviewer 角色 [US-1]

### 实现

- [X] T001 [US1] 删除 `ai_loop/roles/reviewer.py` 文件
  - files: [删除] ai_loop/roles/reviewer.py
  - symbols: ReviewerRole
  - tests: [删除] tests/test_roles.py 中的 TestReviewerRole, TestReviewerRoleContext 类；[删除] import ReviewerRole
  - integrates: 被 orchestrator.py 导入和实例化

- [X] T002 [US1] 删除 `ai_loop/templates/reviewer_claude.md` 模板文件
  - files: [删除] ai_loop/templates/reviewer_claude.md
  - symbols: N/A
  - tests: N/A
  - integrates: 被 _ROLE_TEMPLATE_MAP 和 cli.py role_template_map 引用

- [X] T003 [US1] 从 Orchestrator 中移除 Reviewer 相关代码
  - files: [修改] ai_loop/orchestrator.py
  - symbols: Orchestrator.__init__(), _ROLE_TEMPLATE_MAP, _call_role() 中的 role_map, _update_all_memories()
  - tests: [修改] tests/test_orchestrator.py — 删除 test_review_rework_loop 测试类（L62-86），修改所有 brain_side_effect 函数删除 `post_review` 分支，修改 test_single_round_happy_path 删除 `reviewer:review` 断言改为 `product:qa_acceptance`，修改 TestOrchestratorMemoryCompact 中角色列表删除 "reviewer"（compact_memories 调用次数从 4 改为 3），修改 TestOrchestratorRoleSpecificMemories 删除 reviewer 相关断言和 memories 键，修改 TestOrchestratorCodeDigest 和 TestOrchestratorCliProject 中 brain_side_effect 删除 post_review 分支
  - integrates: import 删除 `from ai_loop.roles.reviewer import ReviewerRole`；__init__ 删除 `self._reviewer`、`self._runners["reviewer"]`；_ROLE_TEMPLATE_MAP 删除 "reviewer" 条目；_call_role.role_map 删除 "reviewer"；_update_all_memories 遍历列表从 4 角色改为 3 角色

- [X] T004 [US1] 从 Brain 中移除 post_review 决策点和 reviewer 记忆
  - files: [修改] ai_loop/brain.py
  - symbols: DECISION_POINT_FILES, DECISION_POINT_INSTRUCTIONS
  - tests: [修改] tests/test_brain.py — 删除 test_decide_post_review_approve 测试，修改 round_summary 相关测试：DECISION_POINT_FILES["round_summary"] 不含 "review.md"，memories 不含 "reviewer" 键
  - integrates: 被 Brain.decide() 使用

- [X] T005 [US1] 从 ContextCollector 中移除 reviewer:review 依赖并新增 product:qa_acceptance
  - files: [修改] ai_loop/context.py
  - symbols: ContextCollector.PHASE_DEPS
  - tests: [修改] tests/test_context.py — 删除 reviewer:review 相关测试（test_reviewer_review_includes_dev_log 等），新增 product:qa_acceptance 依赖测试
  - integrates: 被 Orchestrator._call_role() 调用

- [X] T006 [US1] 从 CLI init 命令中移除 reviewer workspace 创建
  - files: [修改] ai_loop/cli.py
  - symbols: init 函数中的 role_template_map
  - tests: [修改] tests/test_cli.py — 修改 test_init_creates_structure 中断言列表，删除 "reviewer"
  - integrates: `ai-loop init` 命令

- [X] T007 [US1] 修改测试 fixtures 移除 reviewer workspace
  - files: [修改] tests/conftest.py
  - symbols: ai_loop_dir fixture, cli_ai_loop_dir fixture
  - tests: N/A（自身是测试基础设施）
  - integrates: 被所有测试使用的 fixture

- [X] T008 [US1] 修改集成测试移除 reviewer 相关逻辑
  - files: [修改] tests/test_integration.py
  - symbols: full_project fixture, TestIntegration.test_full_round_completes
  - tests: N/A（自身是测试）
  - integrates: full_project fixture 中 workspace 创建、brain mock 中 post_review 分支、memory 断言中 reviewer 角色

### 门禁

- [ ] G1-1 编译/导入检查通过：`python -c "from ai_loop.orchestrator import Orchestrator"` 无报错
- [ ] G1-2 单元测试全部通过：`python -m pytest tests/ -v`，确认无 reviewer 相关的 import 或引用错误
- [ ] G1-3 验收检查：确认以下条件全部满足：
  - `ai_loop/roles/reviewer.py` 已删除
  - `ai_loop/templates/reviewer_claude.md` 已删除
  - `rg -i "reviewer" ai_loop/` 无匹配（排除注释和 fix_review）
  - `rg "post_review" ai_loop/` 无匹配
  - `rg "reviewer" tests/` 无匹配（排除 conftest 中可能保留的兼容键）

---

## Phase 2: Product 新增 qa_acceptance 阶段 [US-2, US-4]

### 实现

- [X] T009 [US2] 在 ProductRole 中实现 qa_acceptance phase（Web 版）
  - files: [修改] ai_loop/roles/product.py
  - symbols: ProductRole.build_prompt(), 新增 _qa_acceptance_prompt(), _qa_acceptance_prompt_web()
  - tests: [新增] tests/test_roles.py 中新增 TestProductQaAcceptance 类，测试 qa_acceptance prompt 包含系统化探索指导、问题分级、健康评分模板
  - integrates: 被 Orchestrator._call_role("product:qa_acceptance", ...) 调用

- [X] T010 [US2] 在 ProductRole 中实现 qa_acceptance phase（CLI 版）
  - files: [修改] ai_loop/roles/product.py
  - symbols: 新增 _qa_acceptance_prompt_cli()
  - tests: [修改] tests/test_roles.py 中 TestProductQaAcceptance 类增加 CLI 版 prompt 测试
  - integrates: 同 T009

- [X] T011 [P] [US2] 从 ProductRole 中移除旧 acceptance 方法
  - files: [修改] ai_loop/roles/product.py
  - symbols: 删除 _acceptance_prompt(), _acceptance_prompt_web(), _acceptance_prompt_cli()；build_prompt phase map 删除 "acceptance"
  - tests: [修改] tests/test_roles.py — 删除旧 acceptance 相关测试（如有）
  - integrates: Orchestrator 不再调用 "product:acceptance"

- [X] T012 [P] [US2] 更新 product_claude.md 模板反映 QA 职责
  - files: [修改] ai_loop/templates/product_claude.md
  - symbols: N/A
  - tests: N/A
  - integrates: 初始化时写入 workspaces/product/CLAUDE.md

- [X] T013 [US4] 在 ContextCollector 中删除旧 product:acceptance 依赖
  - files: [修改] ai_loop/context.py
  - symbols: ContextCollector.PHASE_DEPS — 删除 "product:acceptance" 条目（T005 已新增 "product:qa_acceptance"）
  - tests: [修改] tests/test_context.py — 删除旧 product:acceptance 测试（如有）
  - integrates: 被 Orchestrator._call_role() 调用

### 门禁

- [ ] G2-1 编译/导入检查通过：`python -c "from ai_loop.roles.product import ProductRole"`
- [ ] G2-2 单元测试全部通过：`python -m pytest tests/test_roles.py tests/test_context.py -v`
- [ ] G2-3 验收检查：
  - ProductRole 支持 `build_prompt("qa_acceptance", ...)` 并返回包含"系统化探索"、"健康评分"、"Critical/High/Medium/Low" 的 prompt
  - ProductRole 调用 `build_prompt("acceptance", ...)` 抛出 ValueError
  - Web 和 CLI 两种类型都有对应 prompt

---

## Phase 3: 编排流程重构为 4 阶段 [US-3, US-5]

### 实现

- [X] T014 [US5] 重构 Orchestrator.run_single_round() 为 4 阶段流程
  - files: [修改] ai_loop/orchestrator.py
  - symbols: Orchestrator.run_single_round()
  - tests: [修改] tests/test_orchestrator.py — 修改 test_single_round_happy_path 验证新 4 阶段流程（product:explore → developer:design → developer:implement → product:qa_acceptance），新增测试验证 review loop 不再存在
  - integrates: 删除 review loop（原 L181-194），将 `product:acceptance` 调用改为 `product:qa_acceptance`，调整 _server_start()/_server_stop() 位置

- [X] T015 [US3] 新增 qa_acceptance 失败重试循环测试
  - files: [修改] tests/test_orchestrator.py
  - symbols: 新增 TestQaAcceptanceRetryLoop 类
  - tests: 新增测试验证：acceptance FAIL_IMPL → developer:implement → product:qa_acceptance 重试循环；验证 max_acceptance_retries 控制循环次数；验证超过次数后 ESCALATE
  - integrates: 复用现有 Orchestrator fixture

- [X] T016 [US5] 修改集成测试适配新 4 阶段流程
  - files: [修改] tests/test_integration.py
  - symbols: full_project fixture, TestIntegration.test_full_round_completes
  - tests: N/A（自身是测试）
  - integrates: fixture 中删除 reviewer workspace；brain mock 删除 post_review；memory 断言删除 reviewer；验证新流程能完整执行

- [X] T017 [P] [US5] 调整 test_state.py 兼容 retry_counts 变更
  - files: [修改] tests/test_state.py
  - symbols: test_increment_retry 等
  - tests: N/A（自身是测试）
  - integrates: 保留 "review" 键的兼容性断言，但不再要求新代码使用

### 门禁

- [ ] G3-1 编译/导入检查通过：`python -c "from ai_loop.orchestrator import Orchestrator"`
- [ ] G3-2 全量单元测试通过：`python -m pytest tests/ -v`，零失败
- [ ] G3-3 覆盖率检查：`python -m pytest tests/ --cov=ai_loop --cov-report=term-missing`，新增代码无关键路径遗漏
- [ ] G3-4 验收检查：
  - 运行 `rg "reviewer:review" ai_loop/` 无匹配
  - 运行 `rg "post_review" ai_loop/` 无匹配
  - 集成测试 `python -m pytest tests/test_integration.py -v` 通过

---

## Phase 4: 文档更新

### 实现

- [X] T018 [P] 更新 docs/roles.md 删除 ReviewerRole 章节，更新 ProductRole 验收说明
  - files: [修改] docs/roles.md
  - symbols: N/A
  - tests: N/A
  - integrates: 项目文档

- [X] T019 [P] 更新 docs/orchestration.md 为 4 阶段流程描述
  - files: [修改] docs/orchestration.md
  - symbols: N/A
  - tests: N/A
  - integrates: 项目文档

- [X] T020 [P] 更新 docs/index.md（如有 reviewer 引用）
  - files: [修改] docs/index.md
  - symbols: N/A
  - tests: N/A
  - integrates: 项目文档

### 门禁

- [ ] G4-1 文档内容检查：`rg -i "reviewer" docs/` 无残留引用（审查修复相关说明可保留）
- [ ] G4-2 全量测试回归：`python -m pytest tests/ -v`，确认文档更新未影响代码

---

## 统计

| 指标 | 值 |
|------|-----|
| 总任务数 | 20（含门禁） |
| 实现任务数 | 20 |
| US-1 任务数 | 8 |
| US-2 + US-4 任务数 | 5 |
| US-3 + US-5 任务数 | 4 |
| 文档任务数 | 3 |
| 可并行 [P] 任务数 | 5 |

## 建议 MVP 范围

Phase 1（删除 Reviewer）+ Phase 2（新增 qa_acceptance）为最小可交付单元。Phase 1 和 Phase 2 有依赖关系（Phase 2 的 T005 新增 qa_acceptance 依赖，Phase 3 的 T014 依赖 Phase 1 删除 review loop 和 Phase 2 新增 qa_acceptance phase）。

## 建议下一步

可先运行 `analyze` 做产物一致性检查（可选），再运行 `implement` 按 Phase 顺序执行实现。
