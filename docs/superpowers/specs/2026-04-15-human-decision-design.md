# Human Decision Level Design

## Overview

为 ai-loop 增加人工决策度（human decision level）功能，允许用户在 high 模式下深度介入每个角色的执行过程。角色在遇到不确定性时自主暂停并以 brainstorming 风格向用户提问，多轮对话直到信息充分后继续执行。

## Motivation

当前系统中人工干预仅在 ESCALATE 时被动触发，用户无法在需求澄清和技术方案选型等关键环节主动介入。high 模式让用户成为角色的"协作者"，在关键决策点提供方向性输入。

## Configuration

### config.yaml

```yaml
human_decision: "high"  # "low" (default) | "high"
```

- `low`: 全自动，角色自行决策一切，当前行为不变
- `high`: 角色可自主暂停提问，用户深度参与
- 默认 `"low"`

### CLI Override

```bash
ai-loop run --human-decision high ./my-project
```

CLI `--human-decision` 参数覆盖配置文件值（仅运行时生效，不持久化到 config.yaml）。

### Config Dataclass

```python
HUMAN_DECISION_LEVELS = ("low", "high")

@dataclass
class AiLoopConfig:
    ...
    human_decision: str = "low"
```

删除之前实现的 `HUMAN_DECISION_POINTS`（不再需要按决策点配置，暂停由角色自主决定）。

## RoleRunner: Stream-JSON Bidirectional Communication

### Architecture Change

统一所有角色执行从 `claude -p` 一次性调用改为 cc-connect 风格的双向 stream-json 通信。

### Process Lifecycle

```
启动子进程:
  claude --output-format stream-json
         --input-format stream-json
         --permission-prompt-tool stdio
         --allowedTools <tools>
         [--verbose]

stdin → 发送 JSON 消息
stdout ← 接收 JSON 事件流
关闭 stdin → 结束会话
```

### Message Protocol

**发送消息（stdin）：**

```json
{"type": "user", "message": {"role": "user", "content": "<prompt text>"}}
```

**接收事件（stdout）：** 每行一个 JSON 对象（NDJSON）

| Event Type | Purpose | Key Fields |
|---|---|---|
| `system` | 会话初始化 | `session_id` |
| `assistant` | 角色回复 | `message.content[]` (text / tool_use / thinking) |
| `user` | 工具执行结果 | `message.content[]` (tool_result) |
| `result` | 一轮完成 | `result`, `session_id`, `usage` |
| `control_request` | 权限请求 | `request_id`, `request.tool_name` |

**权限处理（control_request → control_response）：**

```json
{"type": "control_response", "response": {"subtype": "success", "request_id": "<id>", "response": {"behavior": "allow", "updatedInput": {}}}}
```

所有 control_request 自动批准（角色的 allowedTools 已经限定了安全范围）。

### RoleRunner.call() Interface

```python
def call(self, prompt: str, cwd: str,
         verbose: bool = False,
         interaction_callback: Optional[Callable[[str], str]] = None) -> str:
```

- `interaction_callback`: 当检测到 `needs_input` 时调用，传入角色的提问文本，返回用户的回答
- 返回值: 最终的 result 文本

### Execution Loop

```
1. Popen 启动 claude 子进程（stdin=PIPE, stdout=PIPE）
2. stdin 写入 prompt JSON + '\n'
3. 逐行读取 stdout:
   - system → 存 session_id
   - assistant → verbose 模式打印文本/工具调用
   - control_request → 自动批准，stdin 写入 control_response
   - result → 一轮完成，进入步骤 4
4. 检查 result 文本:
   ├─ interaction_callback 存在且 result 包含 {"needs_input": true}
   │  → 提取提问文本（result 中 needs_input 标记之前的内容）
   │  → 调用 callback 获取用户回答
   │  → stdin 写入回答 JSON
   │  → 回到步骤 3
   └─ 否则
      → 关闭 stdin
      → 等待进程退出
      → 返回 result 文本
```

## Human Collaboration Instruction

仅 high 模式下，在角色 prompt 末尾追加以下指令：

```
## 人工协作模式

你在协作模式下工作。当遇到以下情况时，暂停并向调度者提问：
- 需求存在歧义或多种理解
- 有 2 个以上可行方案且各有取舍
- 涉及影响范围大的架构决策
- 你不确定产品意图或优先级

提问规则：
- 一次只问一个问题
- 优先提供 2-3 个选项 + 你的推荐 + 理由
- 开放式问题也可以，但尽量给出方向性建议
- 信息足够后立即继续执行，不要过度确认

提问时在输出末尾附加标记：
{"needs_input": true}

收到回答后继续工作。不再有疑问时正常完成任务，不附加标记。
```

此指令适用于所有角色（product、developer、reviewer），统一行为。

## Orchestrator Changes

### _call_role()

```python
def _call_role(self, role_phase, rnd, round_dir, goals):
    ...
    prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)

    # high 模式：追加协作指令 + 传入回调
    if self._config.human_decision == "high":
        prompt += HUMAN_COLLABORATION_INSTRUCTION
        callback = self._interaction_callback
    else:
        callback = None

    self._runners[role_name].call(
        prompt, cwd=workspace,
        verbose=self._verbose,
        interaction_callback=callback,
    )
```

### _ask_brain()

保持自动，不受 human_decision 影响。删除之前实现的回调逻辑。

### Constructor

```python
def __init__(self, ai_loop_dir: Path, verbose: bool = False,
             interaction_callback: Optional[Callable[[str], str]] = None):
    ...
    self._interaction_callback = interaction_callback
```

## CLI Changes

### Interaction Callback

```python
def _interaction_callback(question_text: str) -> str:
    click.echo(f"\n{'─' * 40}")
    click.echo(f"  🤚 需要你的输入")
    click.echo(f"{'─' * 40}")
    click.echo(question_text)
    click.echo()
    return click.prompt("你的回答")
```

回调只做展示和收集，不解析角色的提问结构。角色的问题格式（选项、推荐等）直接作为文本展示给用户，用户自由文本回答。

### run Command

```python
@main.command()
@click.option("--human-decision", type=click.Choice(["low", "high"]),
              default=None, help="Human decision level")
def run(project_path, goal, verbose, quiet, human_decision):
    ...
    # 回调始终传入，由 orchestrator 根据 human_decision 级别决定是否使用
    callback = _interaction_callback
    orch = Orchestrator(ai_dir, verbose=show_details,
                        interaction_callback=callback)
    # CLI 参数覆盖配置（仅运行时，不写入 config.yaml）
    if human_decision:
        orch._config.human_decision = human_decision
```

### Cleanup

删除之前的部分实现：
- `_DECISION_OPTIONS`, `_DECISION_POINT_NAMES`, 旧 `_human_decision_callback`
- `config.py` 中的 `HUMAN_DECISION_POINTS`
- `orchestrator.py` 中 `_ask_brain` 的回调逻辑

## Scope

### In Scope
- RoleRunner 改为 stream-json 双向通信
- `human_decision` 配置 + CLI 选项
- high 模式角色协作指令注入
- `needs_input` 检测与多轮对话循环
- CLI 交互回调

### Out of Scope
- Brain 决策逻辑不变
- 角色分工不变（product/developer/reviewer 职责不变）
- Context 注入机制不变
- Memory 管理不变
- MCP Server 方案（未来演进方向）

## Testing Strategy

- **RoleRunner**: mock subprocess，验证 stream-json 协议（发送、接收、权限自动批准、needs_input 循环）
- **Config**: 验证 human_decision 字段加载、默认值、校验
- **Orchestrator**: 验证 high 模式下 prompt 包含协作指令、callback 传递
- **CLI**: 验证 --human-decision 参数、回调函数行为
