**Workspace**: `add-interaction-logging`
**Created**: 2026-04-15
**Input**: 用户描述: "打印ai-loop的用户交互记录和ai输出记录日志，用于分析整个流程的问题，以便于优化该项目"

---

## 目标

为 ai-loop 添加结构化日志系统，记录两类关键信息：
1. **用户交互记录** — 每次人机交互的问题和回答、轮次间决策选择
2. **AI 输出记录** — 每次 AI 调用的 prompt（摘要）、完整输出、角色、阶段、耗时、token 花费

日志写入 `.ai-loop/logs/` 目录下的 JSONL 文件，每轮一个文件，便于后续分析流程瓶颈和问题。

## 推荐方案

引入一个 `EventLogger` 类，集中管理日志写入。所有事件以 JSON Lines 格式追加写入文件，每条记录带统一的时间戳和事件类型。

不使用 Python `logging` 模块（保持与项目现有风格一致，避免引入日志框架配置的复杂性）。直接写 JSONL 文件，简单可靠。

### 日志格式设计

每条记录的公共字段：

```json
{
  "timestamp": "2026-04-15T10:30:00.123Z",
  "round": 1,
  "event_type": "ai_call | ai_result | user_interaction | brain_decision | phase_transition | error",
  ...事件特定字段
}
```

**ai_call** — AI 调用发起时：
```json
{"event_type": "ai_call", "role": "product", "phase": "explore", "prompt_length": 2345, "prompt_preview": "前200字..."}
```

**ai_result** — AI 调用返回时：
```json
{"event_type": "ai_result", "role": "product", "phase": "explore", "result_length": 1500, "result_preview": "前200字...", "duration_ms": 45000, "cost_usd": 0.0234, "turns": 5}
```

**brain_decision** — Brain 决策：
```json
{"event_type": "brain_decision", "decision_point": "post_requirement", "decision": "PROCEED", "reason": "..."}
```

**user_interaction** — 用户交互：
```json
{"event_type": "user_interaction", "interaction_type": "collaboration_qa | round_action | escalation", "question_preview": "...", "answer": "c"}
```

**phase_transition** — 阶段转换：
```json
{"event_type": "phase_transition", "from": "product:explore", "to": "developer:design"}
```

**error** — 错误事件：
```json
{"event_type": "error", "context": "developer:implement", "error": "Claude CLI 调用超时..."}
```

## 改动点

### 1. 新增 `ai_loop/logger.py` — EventLogger 类

- `EventLogger(log_dir: Path, round_num: int)` — 初始化，打开 `logs/round-{NNN}.jsonl`
- `log_ai_call(role, phase, prompt)` — 记录 AI 调用
- `log_ai_result(role, phase, result, duration_ms, cost_usd, turns)` — 记录 AI 返回
- `log_brain_decision(decision_point, decision)` — 记录 Brain 决策
- `log_user_interaction(interaction_type, question, answer)` — 记录用户交互
- `log_phase_transition(from_phase, to_phase)` — 记录阶段转换
- `log_error(context, error)` — 记录错误
- 内部 `_write(event_dict)` — 追加一行 JSON 到文件

### 2. 修改 `ai_loop/roles/base.py::RoleRunner.call()` — 捕获 AI 数据

- 在 `call()` 方法签名中新增可选参数 `logger: EventLogger = None`
- 调用前：`logger.log_ai_call(role, phase, prompt_preview)`
- 解析 `result` 事件时：提取 `total_cost_usd`、`num_turns`、`duration_ms`
- 调用结束后：`logger.log_ai_result(role, phase, result, duration_ms, cost_usd, turns)`
- **注意**：当前 `_render_event` 已在解析 result 事件中的 cost/turns/duration，需在非 verbose 模式下也提取这些字段

### 3. 修改 `ai_loop/orchestrator.py::Orchestrator` — 注入 logger

- `__init__` 中创建 `EventLogger` 实例
- `_call_role()` 中：调用前后记录 phase_transition，将 logger 传给 `RoleRunner.call()`
- `_ask_brain()` 中：将 Brain 决策记录到 logger
- `run_single_round()` 中：在异常处理处记录 error 事件
- 轮次切换时：关闭当前 logger，为新轮次创建新的 logger

### 4. 修改 `ai_loop/cli.py` — 记录用户交互

- `_interaction_callback`：包装为带 logger 的闭包，记录 Q&A
- `run` 命令中的 `click.prompt`（轮次间决策）：在每次 prompt 后记录用户选择
- 错误处理中的用户选择：同上

### 5. 修改 `ai_loop/brain.py::Brain.decide()` — 无需改动

Brain 决策的日志记录在 `Orchestrator._ask_brain()` 中完成，Brain 本身不需要改动。

## 文件存储

```
.ai-loop/
  logs/
    round-001.jsonl    # 第 1 轮所有事件
    round-002.jsonl    # 第 2 轮所有事件
    ...
```

## 验证方式

1. **单测**：为 `EventLogger` 写单测，验证 JSONL 写入格式正确
2. **集成验证**：运行一轮 `ai-loop run`，检查 `.ai-loop/logs/round-001.jsonl` 生成且内容完整
3. **回归**：现有测试全部通过，`--cov-fail-under=80` 覆盖率不下降
4. **手动验证**：用 `cat .ai-loop/logs/round-001.jsonl | python -m json.tool --json-lines` 检查格式

## 已知风险

- `RoleRunner.call()` 中 result 事件的 `total_cost_usd` 等字段仅在 verbose/stream-json 模式下可用。需确认非 verbose 模式下这些字段是否仍在 stdout 中输出（根据代码分析，stream-json 始终输出所有事件，verbose 只控制是否 print 到终端，因此 cost 字段应始终可获取）。
- 日志文件可能较大（每轮包含完整 prompt 和 result 的摘要），但仅存储 preview（前 200 字），完整内容已在 rounds/ 下的 md 文件中。
