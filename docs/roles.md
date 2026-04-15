# 角色系统

> 源文件：`ai_loop/roles/base.py`, `ai_loop/roles/product.py`, `ai_loop/roles/developer.py`, `ai_loop/roles/reviewer.py`

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

## 三角色详解

### ProductRole（产品经理）

```python
ProductRole(verification: VerificationConfig)
```

根据 `verification.type` 区分 web 和 cli/library 的行为差异。

**阶段与输出**：

| 阶段 | 方法 | 输出文件 | 说明 |
|------|------|----------|------|
| `explore` | `_explore_prompt_web` / `_explore_prompt_cli` | `requirement.md` | 体验产品 → 提需求 |
| `clarify` | `_clarify_prompt` | `clarification.md` | 回答 Developer 设计中的待确认问题 |
| `acceptance` | `_acceptance_prompt_web` / `_acceptance_prompt_cli` | `acceptance.md` | 逐条验证需求是否满足 |

**Web vs CLI 差异**：

| 行为 | Web | CLI/Library |
|------|-----|-------------|
| 探索方式 | Playwright 脚本访问 base_url | 运行示例命令 + 测试命令 |
| 验收方式 | Playwright 截图对比 | 命令输出 + 测试结果 |
| 证据格式 | before/after 截图 | 命令输出文件 |

**需求文档强制结构**：
- YAML frontmatter（round, role, phase, result, timestamp）
- 问题描述、目标用户、具体需求（P0/P1/P2 分级）、不做的事情、验收标准

**"强制问题"机制**：Product 在写需求前必须先回答 4 个问题（目标用户、最大痛点、最窄切入点、验证方式），确保需求聚焦而非发散。

### DeveloperRole（开发者）

```python
DeveloperRole()
```

无需配置参数，行为由 prompt 模板驱动。

**阶段与输出**：

| 阶段 | 输出文件 | 说明 |
|------|----------|------|
| `design` | `design.md` | 调用 SDD 工具（sketch/specify）完成技术设计 |
| `implement` | `dev-log.md` | 严格 TDD：RED → GREEN → REFACTOR |
| `verify` | `dev-log.md`（追加） | 完整验证（测试、lint、diff 检查、覆盖率） |
| `fix_review` | `dev-log.md`（追加） | 处理审查反馈，允许 DISAGREE |

**TDD 强制流程**：
1. RED — 先写失败测试
2. 运行确认失败（断言失败，非报错）
3. GREEN — 最少代码让测试通过
4. 运行确认全部通过
5. REFACTOR — 清理，保持绿色

**禁止用语**："应该可以""看起来没问题"。只允许命令输出作为证据。

**审查修复规则**：先复述反馈 → 验证审查者说法 → 正确则修复 + 测试 → 有异议则标记 DISAGREE。禁止无脑同意。

### ReviewerRole（审查者）

```python
ReviewerRole()
```

只有一个阶段 `review`，产出 `review.md`。

**5 维审查框架**：

| 维度 | 检查内容 |
|------|----------|
| 规范合规 | 每个需求点是否有对应实现，是否有 scope creep |
| 代码质量 | 可读性、命名、结构，是否遵循项目已有模式 |
| 安全与健壮性 | OWASP Top 10、边界条件、错误处理 |
| 测试覆盖 | 关键路径是否有测试，引用 pytest 覆盖率报告 |
| 回归风险 | 运行完整测试套件并贴出结果 |

**严重级别**：
- `Critical` — 必须修复
- `Important` — 强烈建议修复
- `Minor` — 可选改进

**结果**：`APPROVE` 或 `REQUEST_CHANGES`

## YAML Frontmatter

所有角色产出的文件都包含统一的 YAML frontmatter：

```yaml
---
round: 1
role: product      # product / developer / reviewer
phase: requirement # requirement / design / dev-log / review / acceptance / clarification
result: null       # PASS / FAIL / APPROVE / REQUEST_CHANGES / null
timestamp: 2026-04-15T10:30:00+08:00
---
```

RoleRunner 的 `parse_frontmatter()` 方法可解析此格式，用于后续流程判断。
