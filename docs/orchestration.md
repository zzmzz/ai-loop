# 编排引擎

> 源文件：`ai_loop/orchestrator.py`

Orchestrator 是 AI Loop 的核心调度器，驱动一轮完整的 需求→设计→实现→审查→验收 流程。

## 初始化

```python
Orchestrator(ai_loop_dir: Path, verbose: bool = False,
             interaction_callback: Optional[Callable] = None)
```

初始化时完成：
1. 加载 `config.yaml` → `AiLoopConfig`
2. 加载 `state.json` → `LoopState`
3. 创建 `MemoryManager`、`ContextCollector`
4. 确保 4 个工作空间目录存在（orchestrator/product/developer/reviewer），从 templates/ 复制初始 CLAUDE.md
5. 按配置决定是否创建 `DevServer`（web 项目需要，cli/library 不需要）
6. 创建 `Brain`（使用 orchestrator 工作空间）
7. 创建三角色实例和对应的 `RoleRunner`（工具权限各不同）

### 工具权限分配

| 角色 | 允许的工具 |
|------|-----------|
| product | Read, Glob, Grep, Bash |
| developer | Read, Glob, Grep, Edit, Write, Bash, Skill, Agent |
| reviewer | Read, Glob, Grep, Bash |
| brain | （无工具，纯推理） |

## run_single_round() 流程

一轮迭代由 `run_single_round()` 驱动，返回值为本轮总结字符串（或 `ESCALATE:context:reason`）。

### 阶段 1：需求探索

```
_server_start()                          ← web 项目启动 dev server
_call_role("product:explore", ...)       ← Product 体验产品、写 requirement.md
_ask_brain("post_requirement", ...)      ← Brain 判断需求是否清晰
  PROCEED → 继续
  REFINE  → Product 重新探索
_server_stop()
```

Product 探索时会自动注入 `code-digest.md`（如存在），避免每轮重复读取全量代码。

### 阶段 2：技术设计

```
_call_role("developer:design", ...)      ← Developer 写 design.md
                                            （自动注入 requirement.md）
_ask_brain("post_design", ...)           ← Brain 判断设计是否合理
  PROCEED → 继续
  CLARIFY → Product 回答问题 → Developer 重新设计
  REDO    → Developer 重新设计
```

### 阶段 3：TDD 实现

```
_call_role("developer:implement", ...)   ← Developer 写代码 + dev-log.md
                                            （自动注入 design.md + clarification.md）
_ask_brain("post_implementation", ...)   ← Brain 判断实现是否完整
  PROCEED → 继续
  RETRY   → Developer 补完
```

### 阶段 4：代码审查（循环，最多 max_review_retries 轮）

```
_server_start()
for attempt in range(max_review + 1):
    _call_role("reviewer:review", ...)   ← Reviewer 审查
                                            （自动注入 requirement + design + dev-log）
    _ask_brain("post_review", ...)       ← Brain 评估审查结果
      APPROVE / SKIP_MINOR → 跳出循环
      ESCALATE             → 返回 ESCALATE
      REWORK               → Developer 修复 + 验证 → 下一轮审查
超过次数 → ESCALATE
```

### 阶段 5：产品验收（循环，最多 max_acceptance_retries 轮）

```
for attempt in range(max_accept + 1):
    _call_role("product:acceptance", ...) ← Product 验收
                                             （自动注入 requirement + dev-log）
    _ask_brain("post_acceptance", ...)    ← Brain 评估验收结果
      PASS / PARTIAL_OK → 跳出循环
      ESCALATE          → 返回 ESCALATE
      FAIL_IMPL         → 停 Server → Developer 修复 → 启 Server → 重新验收
      FAIL_REQ          → 停 Server → Product 重探索 → Developer 重实现 → 启 Server → 重新验收
超过次数 → ESCALATE
_server_stop()
```

### 阶段 6：轮次收尾

```
Brain.round_summary(...)                 ← 生成角色专属记忆
_update_all_memories(...)                ← 写入各角色 CLAUDE.md
_update_code_digest(...)                 ← 更新 code-digest.md
state.complete_round(summary)            ← 推进状态到下一轮
```

## 人工协作模式

当 `config.human_decision == "high"` 时，每次角色调用会在 prompt 末尾附加协作指令：

```
## 人工协作模式

你在协作模式下工作。当遇到以下情况时，暂停并向调度者提问：
- 需求存在歧义或多种理解
- 有 2 个以上可行方案且各有取舍
- 涉及影响范围大的架构决策
- 你不确定产品意图或优先级

提问时在输出末尾附加标记：{"needs_input": true}
```

RoleRunner 检测到 `{"needs_input": true}` 后，通过 `interaction_callback` 收集用户输入，然后通过 stream-json 发送回 Claude Code 继续对话。这实现了 **AI 主导 + 人类按需介入** 的协作模式。

## ESCALATE 机制

当 Brain 决策为 ESCALATE 或重试次数耗尽时，`run_single_round()` 返回 `"ESCALATE:context:reason"` 格式的字符串。CLI 层收到后提示用户决策：

- 继续（c）— 进入下一轮
- 加目标（g）— 添加新目标后进入下一轮
- 停止（s）— 结束循环

## _call_role() 内部流程

```python
def _call_role(self, role_phase, rnd, round_dir, goals):
    role_name, phase = role_phase.split(":", 1)

    # 1. 收集前序产物作为上下文
    context = self._context_collector.collect(role_phase, round_dir)

    # 2. Product 探索时额外注入 code-digest.md
    if role_phase == "product:explore" and digest exists:
        context += code_digest_content

    # 3. 角色对象构建 prompt
    prompt = role.build_prompt(phase, rnd, round_dir, goals, context=context)

    # 4. high 模式下附加协作指令
    if config.human_decision == "high":
        prompt += HUMAN_COLLABORATION_INSTRUCTION

    # 5. RoleRunner 执行调用
    runner.call(prompt, cwd=workspace, verbose=..., interaction_callback=...)
```

## Dev Server 生命周期

仅 web 项目（`config.server` 非空）需要 Server：

- **启动时机**：需求探索前、审查循环开始前、验收失败后重新验收前
- **停止时机**：需求探索后、验收失败需要开发修复前、轮次结束后
- **健康检查**：HTTP GET `health_url`，轮询直到 200 或超时
- **停止策略**：先 SIGTERM，等 10s；超时则 SIGKILL，等 5s
