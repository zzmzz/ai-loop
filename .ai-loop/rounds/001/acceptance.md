---
round: 1
role: product
phase: acceptance
result: PASS
timestamp: 2026-04-14T23:45:00+08:00
---

# 验收报告：优化记忆与上下文存储机制

## 测试套件

```
python -m pytest tests/ -v
87 passed in 148.63s (0:02:28)
0 failed, 0 skipped, 0 errors
```

原始基线 61 个测试全部保留并通过，新增 26 个测试覆盖本轮 5 个需求。

## CLI 验证

```
python -m ai_loop.cli init /tmp/ai-loop-test --name TestApp --type web \
  --start-command 'echo ok' --health-url http://localhost:3000 \
  --base-url http://localhost:3000 --no-detect

→ AI Loop 初始化完成: /private/tmp/ai-loop-test/.ai-loop
```

生成文件结构正确：config.yaml、state.json、4 个角色 workspace（各含 CLAUDE.md）、rounds 目录。

## 逐条需求验收

### REQ-1: 消除 ContextCollector 与 prompt 模板的双重注入 — PASS

| 验收标准 | 验证方式 | 结果 |
|----------|----------|------|
| 同一产出文件只出现一次（prompt 中或 Read 工具，不可两者兼有） | Grep 搜索 roles/ 目录，旧模式（"阅读需求文档"、"阅读设计文档"、"阅读本轮需求"、"请阅读："、"1. 需求："）返回 0 匹配；所有 prompt 改为"已附在下方，无需再次读取"或"直接引用即可" | PASS |
| 现有 61 个测试全部通过 | 87 passed（61 原始 + 26 新增） | PASS |

**实现方式：** 采用推荐方案 A——ContextCollector 注入内容到 prompt，角色 prompt 模板中移除文件读取指示。

### REQ-2: Brain 决策上下文内联注入 — PASS

| 验收标准 | 验证方式 | 结果 |
|----------|----------|------|
| Brain prompt 中直接包含文件内容 | `brain.py:111` — `fpath.read_text()` 内联，`file_refs.append(f"### {fname}\n\n{content}")` | PASS |
| Brain 的 allowed_tools 为空 | `brain.py:99` — `allowed_tools=[]` | PASS |
| 所有 Brain 相关测试通过 | 14 个 Brain 测试全部 PASSED | PASS |

### REQ-3: 累积记忆滑动窗口和摘要机制 — PASS

| 验收标准 | 验证方式 | 结果 |
|----------|----------|------|
| 旧轮次自动合并为摘要段落 | `memory.py:40-78` — `compact_memories()` 实现滑动窗口，超出 window 的旧轮次通过 `brain.summarize_memories()` 压缩为"### 历史摘要" | PASS |
| CLAUDE.md 累积记忆总字数不超过合理上限 | `compact_memories` 只保留最近 N 轮完整记忆 + 一段历史摘要（≤500 字） | PASS |
| 新增 memory_window 配置项可加载 | `config.py:32` — `memory_window: int = 5`；`config.py:124` — `lim.get("memory_window", 5)` | PASS |
| 新增至少 2 个测试覆盖滑动窗口和摘要逻辑 | 7 个测试：`test_compact_memories_within_window_no_op`、`test_compact_memories_exceeding_window`、`test_compact_memories_preserves_recent`、`test_compact_memories_with_existing_summary`、`test_compact_memories_no_header_returns_safely`、`test_get_all_round_sections_skips_history_summary`、`test_summarize_memories` | PASS |

### REQ-4: 角色专属记忆 — PASS

| 验收标准 | 验证方式 | 结果 |
|----------|----------|------|
| round_summary 输出包含按角色区分的 memories 字段 | `brain.py:40-48` — round_summary instruction 要求输出 `memories: {product, developer, reviewer}`；`brain.py:57` — `BrainDecision.memories: dict` 字段 | PASS |
| 各角色 CLAUDE.md 只追加属于自己的记忆内容 | `orchestrator.py:253-268` — `_update_all_memories()` 接收 `memories` 参数，按 `role_name` 分发 | PASS |
| 新增测试验证角色记忆差异化 | 4 个测试：`test_brain_decision_with_memories`、`test_brain_decision_without_memories_defaults_empty`、`test_round_summary_instruction_requests_memories`、`test_role_specific_memories` | PASS |

### REQ-5: 项目代码理解缓存 — PASS

| 验收标准 | 验证方式 | 结果 |
|----------|----------|------|
| 每轮结束时自动生成/更新 code-digest.md | `orchestrator.py:165` — `run_single_round()` 结束时调用 `_update_code_digest()`；`orchestrator.py:217-251` — 实现目录树 + git diff 收集，调用 `brain.generate_code_digest()` | PASS |
| Product:explore prompt 优先引用 digest | `orchestrator.py:186-190` — `_call_role()` 对 `product:explore` 注入 code-digest.md 内容；`product.py:36,64` — prompt 第 1 步为"阅读项目代码摘要（code-digest.md 已附在下方）" | PASS |
| 第 2 轮及以后不再出现全量阅读指示 | explore prompt 采用增量阅读：第 2-3 步为 git diff + 变更部分深入阅读 | PASS |
| 新增测试覆盖 digest 生成和更新逻辑 | 6 个测试：`test_generate_code_digest`、`test_code_digest_generated_after_round`、`test_explore_includes_digest_context`、`test_update_code_digest_subprocess_calls`、`test_update_code_digest_diff_fallback_on_first_commit`、`test_update_code_digest_exception_fallback` | PASS |

## 技术约束验证

| 约束 | 结果 |
|------|------|
| 不破坏现有 61 个测试 | 87 passed（原 61 全部保留通过） |
| Python 3.9+ 兼容 | 未使用任何 3.10+ 特性 |
| 不引入新外部依赖 | 摘要通过 Brain（Claude 调用）实现，无新依赖 |

## 总结

5 个需求全部 PASS，测试套件 87/87 通过，CLI 功能正常。验收通过。
