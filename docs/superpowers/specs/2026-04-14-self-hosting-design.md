# AI Loop Self-Hosting：让 ai-loop 迭代自己

## 背景与动机

ai-loop 是一个 AI 驱动的产品迭代闭环框架，通过多角色 Agent（产品经理、开发者、审查者）互相制衡来自动完成需求 -> 设计 -> 实现 -> 审查 -> 验收的闭环。

当前框架有两个限制阻碍了 dogfooding（用自己跑自己）：

1. **验收绑定 Web** — ProductRole 的 explore 和 acceptance 阶段硬编码了 Playwright 浏览器验证，而 ai-loop 本身是 CLI 工具，无法用浏览器验收。
2. **上下文传递不充分** — 角色之间的信息传递依赖"去读某个文件"的指令，但不传递前序阶段的关键结论。角色被迫自行翻找早期文件（例如验收通过后开发仍回看 clarification.md），导致行为偏离预期。

## 目标

让 ai-loop 能够以 Feature 级别的粒度迭代自身代码，完整走通 explore -> design -> implement -> review -> acceptance 闭环。

## 设计

### 模块一：验收策略（Verification Strategy）

#### 配置层

在 `config.yaml` 中新增 `verification` 字段，取代 `browser` 字段：

```yaml
# Web 项目
verification:
  type: web
  base_url: http://localhost:3000

# CLI 项目（如 ai-loop 自身）
verification:
  type: cli
  test_command: "python -m pytest tests/ -v"
  run_examples:
    - "ai-loop init /tmp/test-project --name TestApp"
    - "ai-loop run /tmp/test-project --goal '添加暗色模式' -q"

# Library 项目（未来扩展）
verification:
  type: library
  test_command: "pytest"
```

#### 向后兼容

- 有 `browser.base_url` 但没有 `verification` -> 自动视为 `verification.type: web`，`base_url` 从 `browser` 取。
- 有 `server` -> 正常管理 dev server 生命周期；没有 -> 跳过。

#### 数据结构

`ai_loop/config.py` 新增：

```python
@dataclass
class VerificationConfig:
    type: str                        # "web" | "cli" | "library"
    base_url: str = ""               # web 专用
    test_command: str = ""           # cli/library 专用
    run_examples: list[str] = field(default_factory=list)  # cli 专用
```

现有 `BrowserConfig` 保留用于向后兼容解析，但内部统一转为 `VerificationConfig`。

`ServerConfig` 和 `BrowserConfig` 在 `AiLoopConfig` 中变为 `Optional`：

```python
@dataclass
class AiLoopConfig:
    project: ProjectConfig
    goals: list[str]
    verification: VerificationConfig
    server: ServerConfig | None = None      # web 必填，cli/library 可选
    browser: BrowserConfig | None = None    # 废弃，仅向后兼容
    limits: LimitsConfig = field(default_factory=LimitsConfig)
```

`load_config()` 逻辑：
1. 如果有 `verification` 字段，直接解析。
2. 否则如果有 `browser.base_url`，构造 `VerificationConfig(type="web", base_url=...)`。
3. 否则报错。
4. `server` 字段：如果存在则解析，不存在则为 `None`。

#### ProductRole 改动

`ProductRole.__init__` 接收 `VerificationConfig` 替代 `base_url: str`：

```python
class ProductRole:
    def __init__(self, verification: VerificationConfig):
        self.verification = verification
```

`_explore_prompt` 按 type 分支：
- `web`：现有 Playwright 体验流程（编写脚本访问 base_url，截图，输出需求）。
- `cli`：阅读项目代码理解架构 + 执行 `run_examples` 中的命令体验 CLI 行为 + 运行 `test_command` 了解现有测试覆盖 + 基于代码理解和实际体验输出需求文档。不使用 Playwright。

`_acceptance_prompt` 按 type 分支：
- `web`：现有 Playwright 截图验证。
- `cli`：逐条对照需求 + 运行 `test_command` 确认全部通过 + 执行 `run_examples` 验证 CLI 行为符合预期 + 检查命令输出和生成的文件是否正确。不使用 Playwright。

#### Orchestrator 改动

`_server_start()` / `_server_stop()` 增加条件判断：

```python
def _server_start(self):
    if self._config.server is None:
        return
    # ...现有逻辑

def _server_stop(self):
    if self._config.server is None:
        return
    # ...现有逻辑
```

构造 ProductRole 时传入 verification：

```python
self._product = ProductRole(verification=self._config.verification)
```

### 模块二：上下文管道（Context Pipeline）

#### 问题

当前 prompt 只告诉角色"去读 `{round_dir}/design.md`"，角色需要自行读取文件。这导致：
- 角色可能读到不该看的文件（如验收后回看 clarification.md）
- 角色可能遗漏关键信息
- 角色浪费工具调用在"找信息"上

#### 方案

新增 `ContextCollector` 类，在调用每个角色前自动收集前序产物，直接注入 prompt。

#### 阶段依赖关系

```python
PHASE_DEPS = {
    "product:explore":       [],
    "developer:design":      ["requirement.md"],
    "product:clarify":       ["design.md"],
    "developer:implement":   ["design.md", "clarification.md"],
    "developer:verify":      ["requirement.md"],
    "reviewer:review":       ["requirement.md", "design.md"],
    "product:acceptance":    ["requirement.md", "dev-log.md"],
    "developer:fix_review":  ["review.md"],
}
```

#### 实现

新增文件 `ai_loop/context.py`：

```python
class ContextCollector:
    """从轮次目录中收集指定阶段的前序产物。"""

    PHASE_DEPS = { ... }  # 如上

    def collect(self, role_phase: str, round_dir: Path) -> str:
        """返回格式化的上下文文本。文件不存在则跳过。"""
        deps = self.PHASE_DEPS.get(role_phase, [])
        sections = []
        for fname in deps:
            fpath = round_dir / fname
            if fpath.exists():
                content = fpath.read_text()
                sections.append(f"## {fname}\n\n{content}")
        if not sections:
            return ""
        return "---以下是前序阶段的关键产出，供你参考---\n\n" + "\n\n".join(sections)
```

#### 角色集成

所有角色的 `build_prompt` 方法新增可选参数 `context: str = ""`，追加到 prompt 末尾。

`Orchestrator._call_role()` 在调用前收集上下文：

```python
def _call_role(self, role_phase, rnd, round_dir, goals):
    context = self._context_collector.collect(role_phase, round_dir)
    prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)
    # ...
```

#### 设计原则

1. **只传必要的** — 按 `PHASE_DEPS` 精确传递，不把所有文件塞进去。
2. **文件不存在则跳过** — clarification.md 不一定存在，静默跳过。
3. **不替代文件读取** — 上下文注入减少"找信息"的需要，但角色仍有文件读取权限。
4. **传全文不做摘要** — 产物文件不会太长，摘要有丢信息风险。

### 模块三：Dogfooding 配置

在项目根目录创建 `.ai-loop/config.yaml`，让 ai-loop 用自身框架迭代自身。

```yaml
project:
  name: ai-loop
  path: /Users/StevenZhu/code/ai-loop
  description: AI 驱动的产品迭代闭环框架

goals: []

verification:
  type: cli
  test_command: "python -m pytest tests/ -v"
  run_examples:
    - "python -m ai_loop.cli init /tmp/ai-loop-test --name TestApp --start-command 'echo ok' --health-url http://localhost:3000 --base-url http://localhost:3000"

limits:
  max_review_retries: 3
  max_acceptance_retries: 2
```

- 无 `server` 字段 — CLI 工具不需要 dev server。
- `test_command` — 产品角色跑测试验证实现正确性。
- `run_examples` — 产品角色执行 CLI 命令验证实际行为。

## 改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `ai_loop/config.py` | 修改 | 新增 `VerificationConfig`；`server`/`browser` 可选；向后兼容 |
| `ai_loop/context.py` | 新增 | `ContextCollector` 类 |
| `ai_loop/roles/product.py` | 修改 | 接收 `VerificationConfig`；prompt 按 type 分支 |
| `ai_loop/orchestrator.py` | 修改 | 集成 ContextCollector；server 条件化；传 verification 给 ProductRole |
| `ai_loop/cli.py` | 修改 | init 命令适配新配置结构 |
| `.ai-loop/config.yaml` | 新增 | Dogfooding 配置 |
| `tests/test_config.py` | 修改 | 测试新配置解析和向后兼容 |
| `tests/test_context.py` | 新增 | 测试 ContextCollector |
| `tests/test_roles.py` | 修改 | 测试 ProductRole 新 prompt |
| `tests/test_orchestrator.py` | 修改 | 测试 server 条件化和 context 注入 |

## 不改的部分

- `brain.py` — 决策系统不变。
- `roles/developer.py` — 开发角色 prompt 模板不变，仅 `build_prompt` 签名增加 `context` 参数。
- `roles/reviewer.py` — 审查角色不变，同上。
- `roles/base.py` — RoleRunner 不变。
- `memory.py` / `state.py` — 不变。
