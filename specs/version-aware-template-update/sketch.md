## 目标

ai-loop 版本更新后，`run` 时自动检测版本变化并更新各角色的 CLAUDE.md 模板部分，同时保留已有的累积记忆。

## 推荐方案

利用 `## 累积记忆` 作为天然分割线：模板内容在它之前，记忆内容在它之后。版本更新时，只替换分割线之前的部分，保留之后的记忆。

具体机制：
1. `LoopState` 新增 `ai_loop_version` 字段，持久化到 `state.json`
2. `Orchestrator.__init__` 中比较当前包版本与 state 中记录的版本
3. 版本不同时，对每个角色的 CLAUDE.md 执行"模板刷新"：用新模板替换 `## 累积记忆` 之前的内容，拼接回原有记忆
4. 刷新后更新 state 中的版本号

## 改动点

### 1. `ai_loop/state.py` — LoopState 新增版本字段

- `LoopState` dataclass 新增 `ai_loop_version: str = ""`
- `to_dict()` 序列化该字段
- `load_state()` 反序列化该字段（兼容旧 state 缺失时默认空串）

### 2. `ai_loop/memory.py` — 新增模板刷新函数

- 新增 `refresh_template(claude_md: Path, new_template: str) -> bool`
  - 读取现有 CLAUDE.md
  - 以 `MEMORY_SECTION_HEADER`（`## 累积记忆`）为分割线
  - 保留分割线及之后的所有内容（记忆部分）
  - 用 new_template 替换分割线之前的部分
  - 如果新旧模板部分相同则不写入，返回 False
  - 否则写入并返回 True

### 3. `ai_loop/orchestrator.py::_ensure_workspaces` — 加入版本感知逻辑

- 导入 `ai_loop.__version__` 和 `memory.refresh_template`
- 现有的 `if not claude_md.exists()` 逻辑保持不变（首次创建）
- 新增：当文件已存在且版本不同时，调用 `refresh_template()` 刷新模板
- 刷新完成后更新 `self._state.ai_loop_version` 并保存 state

### 4. `ai_loop/cli.py::init` — 初始化时记录版本

- init 写入 state.json 时设置 `ai_loop_version = __version__`

## 验证方式

1. 单元测试：构造一个带累积记忆的 CLAUDE.md，调用 `refresh_template()`，验证模板部分被替换、记忆部分完整保留
2. 单元测试：`LoopState` 序列化/反序列化包含 `ai_loop_version`，且旧格式兼容
3. 集成验证：修改模板内容 → `ai-loop run` → 检查 CLAUDE.md 模板已更新、记忆未丢失
