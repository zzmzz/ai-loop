---
round: 1
role: developer
phase: design
result: null
timestamp: 2026-04-14T21:15:00+08:00
---

# 实现计划：优化记忆与上下文存储机制

## 现状分析

通过代码审查，确认以下关键数据流：

1. **双重注入路径**：`Orchestrator._call_role()` (orchestrator.py:179) 先调用 `ContextCollector.collect()` 将文件内容拼入 prompt，然后角色 prompt 模板中又以 `阅读 xxx 文件：{path}` 的形式指示 Claude 通过 Read 工具重读同一文件。
2. **Brain 路径引用**：`Brain.decide()` (brain.py:95) 在 prompt 中只列文件路径 `- {fpath}`，让 Claude 通过 Read/Glob/Grep 工具读取，每个决策点独立调用，同一 round 中 requirement.md 被 Brain 读取多达 5 次。
3. **记忆广播**：`_update_all_memories()` (orchestrator.py:206) 将同一段 summary 追加到所有 4 个角色的 CLAUDE.md。
4. **记忆只增不减**：`MemoryManager.append_memory()` (memory.py:8) 无窗口、无摘要机制。
5. **ContextCollector PHASE_DEPS 不完整**：`reviewer:review` 依赖 `[requirement.md, design.md]`，但 prompt 还引用了 dev-log.md；`product:acceptance` 的 CLI 版本 prompt 还引用了 run_examples 结果但这不是文件问题。

## 修改文件清单

| 文件 | 改动类型 | 涉及需求 |
|------|----------|----------|
| `ai_loop/context.py` | 修改 | REQ-1 |
| `ai_loop/roles/product.py` | 修改 | REQ-1, REQ-5 |
| `ai_loop/roles/developer.py` | 修改 | REQ-1 |
| `ai_loop/roles/reviewer.py` | 修改 | REQ-1 |
| `ai_loop/brain.py` | 修改 | REQ-2, REQ-4, REQ-5 |
| `ai_loop/memory.py` | 修改 | REQ-3 |
| `ai_loop/config.py` | 修改 | REQ-3 |
| `ai_loop/orchestrator.py` | 修改 | REQ-3, REQ-4, REQ-5 |
| `tests/test_context.py` | 修改 | REQ-1 |
| `tests/test_brain.py` | 修改 | REQ-2, REQ-4 |
| `tests/test_memory.py` | 修改 | REQ-3 |
| `tests/test_roles.py` | 修改 | REQ-1, REQ-5 |
| `tests/test_orchestrator.py` | 修改 | REQ-3, REQ-4, REQ-5 |
| `tests/test_integration.py` | 修改 | REQ-2 |

## 分步实现计划

### Step 1: REQ-1 — 补全 ContextCollector PHASE_DEPS 并移除 prompt 中的文件读取指示

**做什么：** 采用方案 A。ContextCollector 已注入内容到 prompt，移除角色 prompt 模板中的"阅读 xxx 文件"指示，改为"以下前序产出已附在下方"。同时补全 PHASE_DEPS 中遗漏的依赖。

**改哪个文件：**

#### 1.1 `ai_loop/context.py`

修改 `PHASE_DEPS`：
- `reviewer:review`: `["requirement.md", "design.md"]` → `["requirement.md", "design.md", "dev-log.md"]`（补齐 prompt 中引用的 dev-log.md）

#### 1.2 `ai_loop/roles/developer.py`

- `_design_prompt()`：移除 `阅读需求文档：{round_dir}/requirement.md`，改为 `需求文档已附在下方，无需再次读取。`
- `_implement_prompt()`：移除 `阅读设计文档：{round_dir}/design.md` 和 `如有澄清文档也请阅读：{round_dir}/clarification.md（如存在）`，改为 `设计文档和澄清文档（如有）已附在下方，无需再次读取。`
- `_verify_prompt()`：移除 `对照 {round_dir}/requirement.md 检查每个需求点`，改为 `对照下方附带的需求文档检查每个需求点`
- `_fix_review_prompt()`：移除 `阅读审查意见：{round_dir}/review.md`，改为 `审查意见已附在下方，无需再次读取。`

#### 1.3 `ai_loop/roles/product.py`

- `_clarify_prompt()`：移除 `请阅读：{round_dir}/design.md，找到"待确认问题"章节。`，改为 `设计文档已附在下方，请找到"待确认问题"章节。`
- `_acceptance_prompt_web()`：移除 `1. 阅读本轮需求：{round_dir}/requirement.md`，改为 `1. 参考下方附带的需求文档`
- `_acceptance_prompt_cli()`：同上

#### 1.4 `ai_loop/roles/reviewer.py`

- `_review_prompt()`：移除文件路径引用列表 `1. 需求：{round_dir}/requirement.md 2. 设计：{round_dir}/design.md 3. 开发日志：{round_dir}/dev-log.md`，改为 `需求、设计和开发日志已附在下方，直接引用即可。`

**预期结果：** 所有角色 prompt 中不再出现 `阅读 xxx 文件：{path}` 的指示，文件内容统一由 ContextCollector 注入。prompt 中只保留指向输出文件的写入路径。现有 61 个测试全部通过。

**对现有测试的影响：** `tests/test_roles.py` 中部分断言检查 prompt 中包含文件路径（如 `assert "requirement.md" in prompt`）。这些断言在 prompt 仍然提到 `requirement.md`（如输出路径 `输出文件：{round_dir}/design.md`）的情况下仍可通过。需要逐一检查每个断言是否需要调整。

---

### Step 2: REQ-2 — Brain 决策上下文内联注入

**做什么：** 修改 `Brain.decide()` 方法，将文件内容直接内联到 prompt 中，不再依赖 Read 工具。将 `allowed_tools` 从 `["Read", "Glob", "Grep"]` 缩减为 `[]`。

**改哪个文件：**

#### 2.1 `ai_loop/brain.py`

修改 `Brain.decide()` 方法：

```python
# 当前实现：只列路径
file_refs.append(f"- {fpath}")

# 改为：内联文件内容
content = fpath.read_text()
file_refs.append(f"### {fname}\n\n{content}")
```

修改 prompt 模板：
- 将 `请阅读上述文件后，输出 JSON` 改为 `根据上述文件内容，输出 JSON`
- 将 `相关文件：` 改为 `相关文件内容：`

修改 `__init__`：
- `allowed_tools=["Read", "Glob", "Grep"]` → `allowed_tools=[]`

#### 2.2 `tests/test_brain.py`

- 调整 `test_decide_post_requirement` 等测试：验证 prompt 中包含文件**内容**而非仅路径
- 验证 `Brain._runner.allowed_tools == []`

#### 2.3 `tests/test_integration.py`

- `mock_subprocess_run` 中 Brain 的识别条件 `"决策大脑" in prompt` 仍然成立，无需改动
- 但 prompt 内容更长了（包含文件内容），确认 mock 正常匹配

**预期结果：** Brain prompt 直接包含文件内容，`allowed_tools` 为空列表，所有 Brain 测试通过。

---

### Step 3: REQ-3 — 累积记忆滑动窗口和摘要机制

**做什么：** 在 config 中新增 `memory_window` 配置项，在 MemoryManager 中增加记忆压缩方法，由 Orchestrator 在更新记忆后触发压缩。

**改哪个文件：**

#### 3.1 `ai_loop/config.py`

- `LimitsConfig` 增加字段 `memory_window: int = 5`
- `load_config()` 中解析 `memory_window`

#### 3.2 `ai_loop/memory.py`

新增方法 `compact_memories()`：

```python
def compact_memories(self, claude_md: Path, window: int, summarizer) -> None:
    """保留最近 window 轮的完整记忆，将更早的轮次通过 summarizer 压缩为摘要。
    
    Args:
        claude_md: CLAUDE.md 文件路径
        window: 保留的最近轮次数
        summarizer: 可调用对象，接收旧记忆文本，返回摘要字符串
    """
```

逻辑：
1. 解析 `## 累积记忆` section 下的所有 `### Round NNN` 子段
2. 如果轮次数 <= window，不做操作
3. 提取超出窗口的旧轮次文本
4. 检查是否已存在 `### 历史摘要` 段落，如有则将其内容也纳入待压缩文本
5. 调用 `summarizer(old_text)` 获取摘要
6. 重写 `## 累积记忆` section：`### 历史摘要\n{摘要}\n\n### Round X\n...\n### Round Y\n...`

新增方法 `get_all_round_sections()`：

```python
def get_all_round_sections(self, claude_md: Path) -> list[tuple[int, str]]:
    """返回所有 (round_num, content) 的列表，按轮次排序。"""
```

#### 3.3 `ai_loop/brain.py`

在 `DECISION_POINT_INSTRUCTIONS` 同级位置新增一个摘要用 prompt 构建方法，或在 Brain 类中新增：

```python
def summarize_memories(self, old_memories_text: str) -> str:
    """调用 Claude 将旧记忆压缩为一段概括性摘要。"""
```

该方法构建一个简短 prompt，要求 Claude 将多轮记忆合并为一段不超过 500 字的概括性描述，只输出摘要文本。

#### 3.4 `ai_loop/orchestrator.py`

在 `_update_all_memories()` 末尾增加压缩逻辑：

```python
def _update_all_memories(self, rnd, round_dir, summary):
    for role_name in (...):
        self._memory.append_memory(claude_md, rnd, f"- {summary}")
        if self._memory.count_rounds(claude_md) > self._config.limits.memory_window:
            self._memory.compact_memories(
                claude_md,
                window=self._config.limits.memory_window,
                summarizer=self._brain.summarize_memories,
            )
```

#### 3.5 `tests/test_memory.py`

新增测试：
- `test_compact_memories_within_window_no_op`：轮次 <= window 时不压缩
- `test_compact_memories_exceeding_window`：轮次 > window 时，旧轮次被替换为摘要段落
- `test_compact_memories_preserves_recent`：压缩后最近 N 轮内容完整保留
- `test_compact_memories_with_existing_summary`：已有历史摘要时正确合并

#### 3.6 `tests/test_config.py`

新增测试：
- `test_memory_window_loaded_from_config`
- `test_memory_window_default_value`

**预期结果：** 当轮次数 > memory_window 时，旧记忆自动压缩为摘要。CLAUDE.md 中记忆部分保持可控大小。新配置项可正常加载。

---

### Step 4: REQ-4 — 角色专属记忆

**做什么：** 修改 Brain 的 round_summary 指令，要求其输出按角色区分的记忆内容；修改 BrainDecision 解析逻辑以提取 memories 字段；修改 Orchestrator 分发逻辑。

**改哪个文件：**

#### 4.1 `ai_loop/brain.py`

修改 `DECISION_POINT_INSTRUCTIONS["round_summary"]`：

```python
"round_summary": (
    "生成本轮总结。输出 JSON 格式：\n"
    '{"decision": "PASS", "reason": "一句话总结", '
    '"details": "完整轮次总结", '
    '"memories": {"product": "...", "developer": "...", "reviewer": "..."}}\n'
    "memories 中为各角色生成差异化的记忆内容：\n"
    "- product：侧重需求变更、用户反馈、验收结果\n"
    "- developer：侧重技术决策、架构变更、代码模式\n"
    "- reviewer：侧重审查发现的模式、反复出现的问题\n"
),
```

修改 `BrainDecision`：
- 新增字段 `memories: dict = field(default_factory=dict)`
- `from_claude_output()` 中解析 `memories` 字段（缺失时 fallback 为空 dict）

#### 4.2 `ai_loop/orchestrator.py`

修改 `_update_all_memories()`：

```python
def _update_all_memories(self, rnd, round_dir, summary, memories=None):
    for role_name in ("orchestrator", "product", "developer", "reviewer"):
        claude_md = self._dir / "workspaces" / role_name / "CLAUDE.md"
        if claude_md.exists():
            if memories and role_name in memories:
                content = f"- {memories[role_name]}"
            else:
                content = f"- {summary}"
            self._memory.append_memory(claude_md, rnd, content)
            # ... compact logic from Step 3
```

修改 `run_single_round()` 中调用处：

```python
summary_decision = self._ask_brain("round_summary", round_dir=round_dir)
summary = summary_decision.details or summary_decision.reason
memories = summary_decision.memories  # 新增
self._update_all_memories(rnd, round_dir, summary, memories=memories)
```

Orchestrator 角色收到通用 summary（因为 memories dict 中无 orchestrator key）。

#### 4.3 `tests/test_brain.py`

- 修改 `test_decide_round_summary`：验证返回的 BrainDecision 包含 memories 字段
- 新增 `test_brain_decision_with_memories`：测试解析含 memories 的 JSON

#### 4.4 `tests/test_orchestrator.py`

- 新增 `test_role_specific_memories`：验证不同角色 CLAUDE.md 收到不同的记忆内容

**预期结果：** Brain round_summary 输出包含 memories 字段，各角色 CLAUDE.md 追加属于自己的记忆内容。

---

### Step 5: REQ-5 — 项目代码理解缓存

**做什么：** 在每轮结束时通过 Brain 生成/更新 `code-digest.md`，修改 Product:explore prompt 使其优先使用 digest。

**改哪个文件：**

#### 5.1 `ai_loop/brain.py`

新增方法 `generate_code_digest()`：

```python
def generate_code_digest(self, project_path: str, digest_path: Path, 
                         changed_files: list[str]) -> None:
    """生成或更新项目代码摘要文件。
    
    如果 digest 已存在，只更新变更部分。
    如果不存在，生成完整摘要。
    """
```

该方法构建 prompt 让 Claude 分析项目结构并生成摘要。使用 `allowed_tools=["Read", "Glob", "Grep", "Bash"]` 的独立 RoleRunner（因为需要实际读取项目代码），或者直接在 prompt 中注入必要信息（目录树 + git diff）。

选择方案：在 Orchestrator 层获取目录树和 git diff 信息，作为 prompt 内容传给 Brain，Brain 仍然用 `allowed_tools=[]` 生成摘要。这样保持 Brain 无工具调用的一致性。

#### 5.2 `ai_loop/orchestrator.py`

在 `run_single_round()` 的 round summary 之后、state 保存之前，新增：

```python
# 7. Generate/update code digest
self._update_code_digest(round_dir)
```

新增方法 `_update_code_digest()`：

```python
def _update_code_digest(self, round_dir: Path) -> None:
    digest_path = self._dir / "code-digest.md"
    project_path = self._config.project.path
    # 收集目录结构和 git diff 信息，调用 Brain 生成摘要
    self._brain.generate_code_digest(project_path, digest_path, ...)
```

#### 5.3 `ai_loop/roles/product.py`

修改 `_explore_prompt_web()` 和 `_explore_prompt_cli()`：

将第一步从：
```
1. 阅读项目代码，理解当前功能和架构
```
改为：
```
1. 阅读项目代码摘要（code-digest.md 已附在下方，如有），了解已知项目状态
2. 通过 git diff 查看自上轮以来的代码变更
3. 只针对变更部分深入阅读
```

#### 5.4 `ai_loop/context.py`

修改 `PHASE_DEPS`，为 `product:explore` 添加对 code-digest 的支持：

由于 code-digest.md 存储在 `.ai-loop/code-digest.md`（不在 round_dir 中），需要在 ContextCollector 中增加对非 round_dir 文件的支持。

方案：在 `collect()` 方法中增加一个可选参数 `extra_files: list[Path]`，或者在 Orchestrator 层拼接 digest 内容到 context 中。

选择方案：在 Orchestrator._call_role() 中，对 `product:explore` 阶段额外读取 code-digest.md 并追加到 context。这样 ContextCollector 保持简洁，不需要感知 round_dir 外的文件。

修改 `Orchestrator._call_role()`：

```python
context = self._context_collector.collect(role_phase, round_dir)
if role_phase == "product:explore":
    digest_path = self._dir / "code-digest.md"
    if digest_path.exists():
        digest = digest_path.read_text()
        context += f"\n\n## code-digest.md\n\n{digest}"
```

#### 5.5 `tests/test_roles.py`

- 修改 `test_explore_prompt_*` 系列：验证 prompt 中不再包含"阅读项目代码"的全量指示
- 新增测试验证 prompt 中包含增量阅读指示

#### 5.6 `tests/test_orchestrator.py`

- 新增 `test_code_digest_generated_after_round`：验证 round 结束后调用了 digest 生成
- 新增 `test_explore_includes_digest_context`：验证 product:explore 的 context 中包含 digest 内容

**预期结果：** 每轮结束后 `.ai-loop/code-digest.md` 被创建/更新。Product:explore 优先读取 digest + git diff，不再全量阅读代码。

---

## 实施顺序

按依赖关系和优先级排序：

```
Step 1 (REQ-1) ──→ Step 2 (REQ-2) ──→ Step 3 (REQ-3) ──→ Step 4 (REQ-4) ──→ Step 5 (REQ-5)
     P0                  P0                 P1                  P2                 P1
```

- Step 1 和 Step 2 互相独立，可以并行实施，但建议先做 Step 1（改动更简单、涉及面更广），作为 Step 2 的参考模式。
- Step 3 是 Step 4 的基础（Step 4 的角色专属记忆也需要走压缩流程）。
- Step 5 独立于 Step 3/4，但建议放在最后，因为它涉及新增 Brain 能力和 Orchestrator 流程变更。

每个 Step 完成后运行 `python -m pytest tests/ -v` 确认全部通过。

## 待确认问题

### Q1: Brain summarize_memories 的 allowed_tools

Brain 的 `summarize_memories()` 方法只需要文本输入和文本输出，不需要任何工具。但它需要一个独立的 RoleRunner 实例还是复用 Brain 现有的 `_runner`（Step 2 之后 allowed_tools=[]）？

**建议**：复用 Brain 的 `_runner`（allowed_tools=[]），因为摘要任务只需要文本处理，不需要文件读取能力。

### Q2: code-digest.md 的初次生成

第 1 轮运行时 code-digest.md 不存在，Product:explore 阶段会走全量阅读路径（因为 digest 为空，prompt 中无 digest 内容）。第 1 轮结束后才生成 digest。这个行为是否可接受？

**建议**：可接受。第 1 轮本来就需要从零了解项目。也可以在 `ai-loop init` 时生成初始 digest，但这超出本需求范围。

### Q3: 记忆摘要的字数限制

需求提到"总字数不超过合理上限（如 3000 字）"。摘要生成时是否需要硬性截断？还是仅在 prompt 中要求 Claude "不超过 500 字"？

**建议**：在 summarize_memories 的 prompt 中要求 Claude "生成不超过 500 字的摘要"。不做硬截断，因为 Claude 通常能遵循字数限制。如果后续发现超标，再加硬截断作为防御措施。
