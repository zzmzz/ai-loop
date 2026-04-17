# 角色系统

> 源文件：`ai_loop/roles/base.py`, `ai_loop/roles/product.py`, `ai_loop/roles/developer.py`

## RoleRunner：Claude Code 通信层

`RoleRunner` 封装了与 Claude Code CLI 的双向流式 JSON 通信。所有角色调用和 Brain 推理都通过 RoleRunner 执行。

### 通信协议

```
                  stdin (stream-json)              stdout (stream-json)
AI Loop ──────────────────────────────→ Claude Code ──────────────────────────→ AI Loop
         {"type": "user", "message": ...}          {"type": "assistant", ...}
         {"type": "control_response", ...}         {"type": "control_request", ...}
                                                   {"type": "result", ...}
```

**事件流处理**：

| 事件类型 | 处理方式 |
|----------|----------|
| `control_request` | 自动批准（auto-allow），返回 `control_response` |
| `result` | 检查是否包含 `{"needs_input": true}`；有则触发回调继续对话，无则作为最终结果 |
| `assistant` (verbose) | 渲染工具调用和文本输出到终端 |

### 多轮对话支持

RoleRunner 通过 `--input-format stream-json` 支持多轮对话：

1. 发送初始 prompt
2. 读取事件流直到 `result`
3. 如果 result 包含 `{"needs_input": true}`，提取问题部分
4. 通过 `interaction_callback` 获取用户回答
5. 将回答作为新的 user message 发送
6. 继续读取事件流

### Verbose 输出

verbose 模式下，RoleRunner 会实时渲染 Claude Code 的执行过程：

```
  ⚡ Read requirement.md
  ⚡ Bash pytest tests/ -v
  │ 你是产品经理...
  │ ... (3 more lines)
  ✓ 5 turns, 12.3s, $0.0421
```

### 构造参数

```python
RoleRunner(role_name: str, allowed_tools: list[str])
```

`allowed_tools` 映射到 `claude --allowedTools` 参数，实现工具权限隔离。

### 调用统计（last_stats）

每次 `call()` 返回前，会根据最近一条 `result` 事件更新 `last_stats`（`RoleRunner.last_stats` 属性）：`duration_ms`、`cost_usd`（对应事件字段 `total_cost_usd`）、`turns`（`num_turns`）。若尚无结果事件，则为零值。编排器用其写入 `EventLogger.log_ai_result`（见 [编排引擎](orchestration.md)）。

## 双角色详解

### ProductRole（产品经理）

```python
ProductRole(verification: VerificationConfig, knowledge_dir: Path)
```

`knowledge_dir` 通常为 `.ai-loop/product-knowledge`。Orchestrator 在 `product:explore` 时若存在 `knowledge_dir/index.md`，会将其内容附加到角色上下文（与 `code-digest.md` 类似）。

根据 `verification.type` 区分 web 和 cli/library 的行为差异。

**产品认知库（`product-knowledge/`）**：探索阶段 prompt 要求 Product 先读索引并按目标阅读子文档；探索结束后用 `Write` 将新发现写入该目录（仅限此目录），按业务域拆分文件并维护 `index.md`（表格列：业务域、文件、概述、最后更新）。验收阶段 prompt 要求根据验收结果更新相关子文档、记录改进效果。具体段落由 `ProductRole._knowledge_maintenance_instruction()` 生成。

**阶段与输出**：

| 阶段 | 方法 | 输出文件 | 说明 |
|------|------|----------|------|
| `explore` | `_explore_prompt_web` / `_explore_prompt_cli` | `requirement.md` | 体验产品 → 提需求 |
| `clarify` | `_clarify_prompt` | `clarification.md` | 回答 Developer 设计中的待确认问题 |
| `qa_acceptance` | `_qa_acceptance_prompt_web` / `_qa_acceptance_prompt_cli` | `acceptance.md` | 系统化测试 + 需求验收 |

**Web vs CLI 差异**：

| 行为 | Web | CLI/Library |
|------|-----|-------------|
| 探索方式 | Playwright 脚本访问 base_url | 运行示例命令 + 测试命令 |
| 验收方式 | Playwright 截图对比 | 命令输出 + 测试结果 |
| 证据格式 | before/after 截图 | 命令输出文件 |

**需求文档强制结构**：
- YAML frontmatter（round, role, phase, result, timestamp）
- 问题描述、目标用户、具体需求（P0/P1/P2 分级）、不做的事情、验收标准、延迟池（可选）

**需求数量限制**：每轮最多 3 条需求（1 条 P0 + 至多 2 条 P1/P2）。超出 3 条的需求写入末尾的"延迟池"章节（一句话描述 + 优先级），供下一轮参考。此限制在 web 和 cli 两种 explore prompt 中均生效。

**"强制问题"机制**：Product 在写需求前必须先回答 4 个问题（目标用户、最大痛点、最窄切入点、验证方式），确保需求聚焦而非发散。

### DeveloperRole（开发者）

```python
DeveloperRole()
```

无需配置参数，行为由 prompt 模板驱动。

**阶段与输出**：

| 阶段 | 输出文件 | 说明 |
|------|----------|------|
| `develop` | `design.md` + `dev-log.md` | 单 session 完成设计+实现（主流程使用） |
| `design` | `design.md` | 仅设计阶段（独立调用时使用） |
| `implement` | `dev-log.md` | 仅实现阶段（验收修复循环中使用） |
| `verify` | `dev-log.md`（追加） | 完整验证（测试、lint、diff 检查、覆盖率） |
| `fix_review` | `dev-log.md`（追加） | 处理审查反馈，允许 DISAGREE |

**`develop` 阶段双路径**：

Developer 在 `develop` 阶段根据需求规模自动选择路径：

- **Sketch 路径**（中小需求）：调用 `/sdd:sketch` → 人工确认 → 直接实现
- **Specify 路径**（大需求）：调用 `/sdd:specify` → 确认 → `/sdd:plan` → 确认 → `/sdd:tasks` → 确认 → `/sdd:implement`

两条路径在同一个 Claude CLI session 中执行，通过 `{"needs_input": true}` 在每个确认点暂停等待人工输入。

**TDD 强制流程**（两条路径共用）：
1. RED — 先写失败测试
2. 运行确认失败（断言失败，非报错）
3. GREEN — 最少代码让测试通过
4. 运行确认全部通过
5. REFACTOR — 清理，保持绿色

**禁止用语**："应该可以""看起来没问题"。只允许命令输出作为证据。

**审查修复规则**：先复述反馈 → 验证审查者说法 → 正确则修复 + 测试 → 有异议则标记 DISAGREE。禁止无脑同意。

### QA 测试验收（ProductRole `qa_acceptance` 阶段）

Product 在 `qa_acceptance` 阶段同时承担 QA 工程师和产品经理双重角色：

**工作流程**：

1. **需求验证**（必做）：逐条验证需求文档中的 P0/P1/P2 需求，留截图或命令输出作为证据
2. **系统化探索**（必做）：主动探索产品寻找需求未覆盖的问题（边界场景、交互完整性、异常处理）
3. **汇总评估**：问题分级 + 健康评分

**问题严重级别**：
- `Critical` — 功能完全不可用、数据丢失、安全漏洞（必须立即修复）
- `High` — 核心流程受阻、严重影响用户体验（应在本轮修复）
- `Medium` — 非核心功能异常、有 workaround（建议下轮处理）
- `Low` — 美观问题、文案优化、边缘场景（记入延迟池）

**健康评分**（满分 100）：

| 维度 | 分值 | 说明 |
|------|------|------|
| 需求满足 | /50 | P0 全过 +30，P1 每条 +10，P2 每条 +5 |
| 功能稳定性 | /25 | 无 Critical=25，有 Critical=0，每个 High -5 |
| 用户体验 | /25 | 基于探索发现的 Medium/Low 问题数量扣分 |

**结果判定**：
- `PASS` — 所有需求通过，无 Critical/High 探索发现，健康评分 ≥ 80
- `PARTIAL` — P0 全部通过但存在 P1/P2 未通过，或有 High 探索发现
- `FAIL` — 任何 P0 未通过，或有 Critical 探索发现，或健康评分 < 60

## YAML Frontmatter

所有角色产出的文件都包含统一的 YAML frontmatter：

```yaml
---
round: 1
role: product      # product / developer
phase: requirement # requirement / design / dev-log / qa_acceptance / clarification
result: null       # PASS / PARTIAL / FAIL / null
timestamp: 2026-04-15T10:30:00+08:00
---
```

RoleRunner 的 `parse_frontmatter()` 方法可解析此格式，用于后续流程判断。
