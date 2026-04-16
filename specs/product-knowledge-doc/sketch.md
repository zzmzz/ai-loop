## 目标

产品角色每轮 explore 都要重新了解代码仓。增加"产品认知文档"机制：按业务域拆分为多个子文档 + 一个 index，产品角色在探索和验收后维护。注入时只注入 index，角色按需 Read 子文档，节省 token。

## 推荐方案

在 `.ai-loop/product-knowledge/` 目录维护产品认知文档：

```
.ai-loop/product-knowledge/
├── index.md          # 索引：列出所有业务域及一句话描述
├── auth.md           # 示例：认证模块的产品认知
├── export.md         # 示例：导出功能的产品认知
└── ...
```

- **index.md**：全量注入给所有角色。每条一行，包含域名、文件路径、一句话描述
- **子文档**：角色根据 index 中的描述判断相关性，自行 Read 需要的子文档
- **维护时机**：product:explore 结束后创建/更新，product:acceptance 结束后更新

与 `code-digest.md` 的区别：
- `code-digest.md`：Brain 自动生成，技术视角
- `product-knowledge/`：产品角色手动编写，产品视角（功能理解、体验现状、已知问题、改进历史）

## 改动点

### 1. `ai_loop/roles/product.py::__init__` — 增加 knowledge_dir 参数

```python
def __init__(self, verification: VerificationConfig, knowledge_dir: Path):
    self.verification = verification
    self._knowledge_dir = knowledge_dir
```

各 prompt builder 中使用 `self._knowledge_dir` 生成路径。

### 2. `ai_loop/roles/product.py::_explore_prompt_web` + `_explore_prompt_cli` — 增加文档维护步骤

在工作步骤中插入：
- **步骤 1 之前**新增："阅读 product-knowledge/index.md（已附在下方，如有），根据本轮目标 Read 相关子文档，快速恢复产品认知"
- **最后一步**新增："更新 `{knowledge_dir}/` 下的产品认知文档"

给出 index.md 和子文档的格式规范（写在 prompt 中）。

### 3. `ai_loop/roles/product.py::_acceptance_prompt_web` + `_acceptance_prompt_cli` — 增加文档更新步骤

验收完成后新增步骤：
- "根据验收结果更新 `{knowledge_dir}/` 下的相关子文档，记录本轮改进效果"

### 4. `ai_loop/orchestrator.py::__init__` — 传递 knowledge_dir

第 89 行：
```python
self._product = ProductRole(
    verification=self._config.verification,
    knowledge_dir=ai_loop_dir / "product-knowledge",
)
```

### 5. `ai_loop/orchestrator.py::_call_role` — 注入 index.md 给所有角色

在第 246 行 context 收集之后、第 252 行 prompt 构建之前，增加：

```python
# 注入 product-knowledge index 给所有角色
knowledge_index = self._dir / "product-knowledge" / "index.md"
if knowledge_index.exists():
    index_content = knowledge_index.read_text()
    context += f"\n\n## product-knowledge/index.md\n\n{index_content}"
```

角色已有 Read 权限，可自行读取子文档。

### 6. `ai_loop/orchestrator.py` 第 94 行 — 产品角色加 Write 权限

```python
"product": RoleRunner("product", ["Read", "Glob", "Grep", "Bash", "Write"]),
```

产品角色需要写文件来维护 product-knowledge 目录。prompt 中约束 Write 仅用于 `product-knowledge/` 目录。

### 7. `ai_loop/orchestrator.py::_ensure_workspaces` — 确保 product-knowledge 目录存在

在第 127 行附近新增：
```python
(self._dir / "product-knowledge").mkdir(exist_ok=True)
```

## index.md 格式规范（写入 prompt）

```markdown
# 产品认知索引

| 业务域 | 文件 | 概述 | 最后更新 |
|--------|------|------|----------|
| 用户认证 | auth.md | 登录/注册/权限体系，当前支持邮箱+OAuth | Round 3 |
| 数据导出 | export.md | 报表导出功能，支持 CSV/Excel | Round 5 |
```

## 子文档推荐结构（写入 prompt）

```markdown
# {业务域名称}

## 功能概述
（这个域包含哪些功能，面向谁）

## 体验现状
（当前的交互流程和体验质量）

## 已知问题
（发现但未解决的问题，按优先级排列）

## 改进历史
- Round N: 改了什么 → 效果如何
```

## 验证方式

- 运行一轮 ai-loop，确认 product:explore 后 `.ai-loop/product-knowledge/index.md` 和至少一个子文档被创建
- 运行第二轮，确认产品角色读取已有 index 后按需 Read 子文档，并做增量更新
- 确认 developer:design 等阶段 prompt 中包含 index.md 内容（通过 event log 验证）
- 确认 product:acceptance 后相关子文档被更新
- 现有测试不受影响
