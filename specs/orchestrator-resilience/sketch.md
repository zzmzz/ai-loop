## 目标

修复 ai-loop 编排器在实际使用中暴露的 4 个核心问题：断点续跑、QA 反馈传递、端口冲突处理、Brain 质量把关。

## 问题 1：断点续跑

### 现状

- `state.py:LoopState` 有 `phase` 字段但始终为 `"idle"`，从未在流程中更新
- `cli.py:240` catch 异常后 `continue` 直接调 `run_single_round()`，从头执行 `product:explore`
- 已有的 `requirement.md`、`design.md` 等产物被浪费

### 方案

在 `orchestrator.py::run_single_round` 的每个阶段转换前，将 phase 写入 state.json。恢复时根据 phase 跳过已完成阶段。

**改动点：**

- `ai_loop/orchestrator.py::run_single_round` — 每个阶段前调用 `_save_phase(phase_name)`；方法开头增加恢复逻辑，根据 `self._state.phase` 跳到对应阶段
- `ai_loop/state.py::LoopState` — 无需改结构，`phase` 字段已有，只需实际使用

**阶段定义（phase 值）：**

```
idle → product_explore → post_requirement → developer_develop → post_development
→ qa_acceptance → post_acceptance → round_summary → idle
```

**恢复逻辑：**
- `idle` → 从头开始
- `product_explore` → 从 product:explore 开始（含 confirm_requirements）
- `developer_develop` → 跳过 product，从 developer:develop 开始
- `qa_acceptance` → 跳过 product+developer，从 qa_acceptance 开始
- 其他中间 phase → 跳到对应阶段

## 问题 2：FAIL_IMPL 不传 QA 反馈

### 现状

- `context.py::PHASE_DEPS` 中 `developer:implement` 只依赖 `["design.md", "clarification.md"]`
- QA 验收的 `acceptance.md` 包含修复建议但不传给开发者
- 开发者盲改，导致超时

### 方案

在 `PHASE_DEPS` 中为 `developer:implement` 添加 `acceptance.md`。

**改动点：**

- `ai_loop/context.py::PHASE_DEPS["developer:implement"]` — 从 `["design.md", "clarification.md"]` 改为 `["design.md", "clarification.md", "acceptance.md"]`

一行改动。acceptance.md 不存在时（首次 implement 而非修复）`collect` 自动跳过。

## 问题 3：DevServer 端口冲突

### 现状

- `server.py::start` 只检查 `is_running()`（自己的进程是否活着），不检查端口是否被其他进程占用
- 端口被上次残留进程占用时，新进程启动失败，`_wait_healthy` 检测到进程退出后抛异常

### 方案

在 `start()` 中，启动进程前解析 `health_url` 获取端口，用 `lsof` 检测并 kill 占用进程。

**改动点：**

- `ai_loop/server.py::DevServer.start` — 在 `Popen` 之前调用 `_kill_port_holders()`
- `ai_loop/server.py::DevServer._kill_port_holders` — 新增私有方法，从 `health_url` 解析端口，`lsof -ti:{port}` 找到 PID，`kill` 掉

**边界处理：**
- `lsof` 返回空 → 无需处理
- kill 失败 → 打日志警告，不阻塞后续启动（启动失败时 `_wait_healthy` 会兜底报错）
- macOS/Linux 都有 `lsof`，跨平台无问题

## 问题 4：Brain 质量把关

### 现状

- `brain.py::DECISION_POINT_INSTRUCTIONS["post_design"]` 只说"判断这份设计是否合理、是否与需求匹配"，太笼统
- Brain 总是回 PROCEED + "结构完整"，从未检查具体数值范围、兼容性等细节
- 导致设计偏差在 QA 阶段才发现，修复成本 $3+ 一次

### 方案

强化 `post_design` 的 instruction，要求 Brain 做逐项对照检查，输出检查清单。

**改动点：**

- `ai_loop/brain.py::DECISION_POINT_INSTRUCTIONS["post_design"]` — 替换为详细的检查清单 prompt

**新 instruction 要点：**
1. 逐条对照：需求中每个验收标准是否在设计中有对应方案
2. 数值/范围检查：需求中提到的具体数值（范围、阈值、格式）在设计中是否一致
3. 兼容性检查：改动是否考虑了已有数据/接口的向后兼容
4. 遗漏检查：需求明确说"要做"但设计中未提及的内容
5. 输出格式：必须列出检查项清单 + 每项 PASS/FAIL + 汇总判定

同时优化 `post_development` 的 instruction，要求对照 requirement 的验收标准逐项检查 dev-log 中的证据。

## 验证方式

1. 断点续跑：
   - 单测：mock `_call_role`，验证 phase=`developer_develop` 时跳过 product:explore
   - 手动：运行到 developer 阶段后 kill 进程，重启后确认从 developer 继续

2. QA 反馈传递：
   - 单测：round_dir 有 acceptance.md 时，`collect("developer:implement", ...)` 返回内容包含 acceptance.md

3. 端口冲突：
   - 单测：mock `subprocess.run`（lsof），验证调用了 kill
   - 手动：先启 dev server，再跑 ai-loop，确认自动 kill 旧进程

4. Brain 质量把关：
   - 集成测试：给 Brain 一份"需求要 [0,100] 但设计写 [0,1]"的样例，验证判定为 REDO
   - 现有 brain 测试适配新 prompt 格式
