# 决策系统（Brain）

> 源文件：`ai_loop/brain.py`

Brain 是编排器的独立裁判，在每个阶段产出后做出 JSON 格式的决策，驱动流程走向。Brain 本身不使用任何工具（`allowed_tools=[]`），只基于文件内容做纯推理判断。

## 6 个决策点

### post_requirement

- **触发时机**：Product 完成需求探索后
- **输入文件**：`requirement.md`
- **指令**：判断需求文档是否足够清晰、具体、可执行
- **可选决策**：

| 决策 | 含义 | 后续动作 |
|------|------|----------|
| `PROCEED` | 清晰可执行 | 进入技术设计 |
| `REFINE` | 需要细化 | Product 重新探索 |

### post_design

- **触发时机**：Developer 完成技术设计后
- **输入文件**：`requirement.md`, `design.md`
- **指令**：判断设计是否合理、是否与需求匹配
- **可选决策**：

| 决策 | 含义 | 后续动作 |
|------|------|----------|
| `PROCEED` | 合理 | 进入实现 |
| `CLARIFY` | 有待确认问题 | Product 回答 → 重新设计 |
| `REDO` | 偏离需求 | Developer 重新设计 |

### post_implementation

- **触发时机**：Developer 完成实现后
- **输入文件**：`requirement.md`, `design.md`, `dev-log.md`
- **指令**：判断实现是否完整，验证是否充分
- **可选决策**：

| 决策 | 含义 | 后续动作 |
|------|------|----------|
| `PROCEED` | 实现完整 | 进入审查 |
| `RETRY` | 有遗漏 | Developer 补完 |

### post_review

- **触发时机**：Reviewer 完成审查后
- **输入文件**：`requirement.md`, `review.md`
- **指令**：评估审查反馈的合理性和严重程度
- **可选决策**：

| 决策 | 含义 | 后续动作 |
|------|------|----------|
| `APPROVE` | 无需修改 | 进入验收 |
| `SKIP_MINOR` | 只有 Minor 问题 | 进入验收 |
| `REWORK` | 有 Critical/Important | Developer 修复 → 重新审查 |
| `ESCALATE` | 需人类介入 | 暂停流程 |

### post_acceptance

- **触发时机**：Product 完成验收后
- **输入文件**：`requirement.md`, `acceptance.md`
- **指令**：评估验收结果（acceptance.md 中 result 为 PASS/PARTIAL/FAIL）
- **可选决策**：

| 决策 | 含义 | 后续动作 |
|------|------|----------|
| `PASS` | 全部通过 | 轮次完成 |
| `PARTIAL_OK` | P0 全过，仅 P1/P2 未过 | 轮次完成（下轮处理） |
| `FAIL_IMPL` | P0 未过，实现问题 | Developer 修复 → 重新验收 |
| `FAIL_REQ` | 需求不清 | Product 重探索 → 重新实现 |
| `ESCALATE` | 需人类介入 | 暂停流程 |

### round_summary

- **触发时机**：验收通过后
- **输入文件**：`requirement.md`, `design.md`, `dev-log.md`, `review.md`, `acceptance.md`
- **指令**：生成本轮总结 + 角色专属记忆
- **输出 JSON schema**：

```json
{
  "decision": "PASS",
  "reason": "一句话总结",
  "details": "完整轮次总结",
  "memories": {
    "product": "侧重需求变更、用户反馈、验收结果",
    "developer": "侧重技术决策、架构变更、代码模式",
    "reviewer": "侧重审查发现的模式、反复出现的问题"
  }
}
```

## BrainDecision 数据结构

```python
@dataclass
class BrainDecision:
    decision: str          # 决策标识（PROCEED, APPROVE, ESCALATE 等）
    reason: str            # 一句话理由
    details: str = ""      # 补充细节
    memories: dict = {}    # 角色专属记忆（仅 round_summary 使用）
```

### JSON 解析策略

`BrainDecision.from_claude_output(raw)` 按以下顺序尝试解析 Claude 输出：

1. 直接 `json.loads()` 整个输出
2. 从 markdown 代码块中提取 JSON（`` ```json ... ``` ``）
3. 兜底：返回 `PROCEED`（附带原始输出前 500 字符）

## 附加能力

### 代码摘要生成

```python
Brain.generate_code_digest(project_path, digest_path, tree_output, diff_output)
```

每轮结束后，Orchestrator 收集目录树和 git diff，交给 Brain 生成/更新 `code-digest.md`。下一轮 Product 探索时注入此摘要，避免每轮重复读取全量代码。

### 记忆压缩

```python
Brain.summarize_memories(old_memories_text) -> str
```

当累积记忆轮次超过 `memory_window` 时，MemoryManager 调用此方法将旧记忆压缩为不超过 500 字的摘要。详见 [记忆与上下文](memory-context.md)。

## Prompt 构建模式

Brain 的 prompt 结构固定：

```
你是编排器决策大脑。根据以下文件内容做出判断。

决策点：{decision_point}
{decision_point_specific_instruction}

相关文件内容：
### requirement.md
{content}

### design.md
{content}

根据上述文件内容，输出 JSON 格式的决策：
{"decision": "...", "reason": "一句话理由", "details": "补充细节（可选）"}

只输出 JSON，不要输出其他内容。
```

文件内容通过内联方式注入（而非让 Brain 自己读取文件），确保 Brain 的 `allowed_tools=[]` 约束有效。
