**Workspace**: `require-human-confirm-before-req`
**Created**: 2026-04-16
**Input**: 用户描述: "产品需求出的有点发散，我希望产品需求都和人确认之后再写进需求里"

---

## 目标

1. 限制产品角色每轮需求数量，避免发散
2. 在需求写入 `requirement.md` 之前增加人工确认环节：产品先出草案，人审核裁剪后再定稿

## 推荐方案

分两层解决：**prompt 层约束数量** + **流程层增加确认卡点**。

### 层 1：prompt 约束——限制需求数量

在 `_explore_prompt_web` 和 `_explore_prompt_cli` 的需求模板中，追加硬约束：

> 每轮最多 3 条需求（1 条 P0 + 至多 2 条 P1/P2）。如果发现的问题超过 3 个，只保留优先级最高的 3 条，其余记入"延迟池"（写在 requirement.md 末尾的 `### 延迟池` 章节，供下一轮参考）。

### 层 2：流程约束——需求草案人工确认

在 `product:explore` 和 Brain `post_requirement` 之间，插入一个人工确认环节：

1. 产品角色照常输出 `requirement.md`（此时它是"草案"）
2. 编排器读取草案，提取需求列表，呈现给人
3. 人选择保留/删除/修改每条需求
4. 编排器根据人的选择更新 `requirement.md`
5. 更新后的版本再交给 Brain 做 `post_requirement` 决策

**触发条件**：`human_decision` 配置项不为 `"low"`。当 `human_decision: "low"` 时跳过确认，保持现有全自动流程。

## 改动点

### 1. `ai_loop/roles/product.py` — prompt 中添加需求数量限制

`_explore_prompt_web` 和 `_explore_prompt_cli` 的 `### 具体需求` 章节前插入：

```
## 需求数量约束

每轮最多 3 条需求。超过 3 个问题时，只保留最高优先级的 3 条写入"具体需求"，其余写入末尾的"### 延迟池"。
延迟池格式：一句话描述 + 优先级，不需要完整展开。
```

两个方法各改一处，内容相同。

### 2. `ai_loop/orchestrator.py::run_single_round` — 在 post_requirement 前插入确认环节

在第 155 行 `decision = self._ask_brain("post_requirement", ...)` 之前，增加：

```python
if self._config.human_decision != "low":
    self._confirm_requirements(round_dir)
```

### 3. `ai_loop/orchestrator.py` — 新增 `_confirm_requirements` 方法

```python
def _confirm_requirements(self, round_dir: Path) -> None:
    """让人审核需求草案，裁剪或修改后再继续。"""
    req_path = round_dir / "requirement.md"
    if not req_path.exists():
        return

    content = req_path.read_text()
    reqs = self._extract_requirements(content)

    if not reqs:
        return

    self._log("\n\033[1m📋 产品需求草案待确认：\033[0m")
    for i, req in enumerate(reqs, 1):
        self._log(f"  {i}. [{req['priority']}] {req['title']}")

    if self._interaction_callback:
        response = self._interaction_callback(
            f"产品角色提出了 {len(reqs)} 条需求（见上方列表）。\n"
            "请选择操作：\n"
            "  [a] 全部接受\n"
            "  [d] 输入要删除的编号（逗号分隔，如 2,3）\n"
            "  [e] 打开 requirement.md 手动编辑后继续\n"
            "  [r] 全部拒绝，让产品重新出\n"
            "选择: "
        )
        response = response.strip().lower()
        if response == "r":
            req_path.unlink()
        elif response.startswith("d"):
            nums = response.replace("d", "").strip()
            self._remove_requirements(req_path, content, reqs, nums)
        elif response == "e":
            self._log(f"  请编辑 {req_path} 后按回车继续...")
            self._interaction_callback("编辑完成后按回车继续: ")
    # "a" 或其他输入 = 全部接受，不做操作
```

### 4. `ai_loop/orchestrator.py` — 新增 `_extract_requirements` 辅助方法

从 requirement.md 内容中提取需求列表（解析 `- **[P0/P1/P2] xxx**` 格式，或 `## REQ-N:` 格式）：

```python
def _extract_requirements(self, content: str) -> list[dict]:
    """从 requirement.md 提取需求条目。"""
    import re
    reqs = []
    # 匹配 "## REQ-N: title" 格式
    for m in re.finditer(r'##\s+REQ-(\d+)[：:]\s*(.+)', content):
        reqs.append({"id": f"REQ-{m.group(1)}", "title": m.group(2).strip(),
                      "priority": "P1"})
    # 匹配 "- **[P0] title**" 格式
    for m in re.finditer(r'-\s*\*\*\[(P\d)\]\s*(.+?)\*\*', content):
        reqs.append({"id": "", "title": m.group(2).strip(),
                      "priority": m.group(1)})
    # 从 ## REQ-N 标题行上方查找优先级表格来补全 priority
    for m in re.finditer(r'\|\s*(P\d)\s*\|\s*REQ-(\d+)', content):
        for req in reqs:
            if req["id"] == f"REQ-{m.group(2)}":
                req["priority"] = m.group(1)
    return reqs
```

### 5. `ai_loop/orchestrator.py` — 新增 `_remove_requirements` 辅助方法

按编号删除需求章节并重写文件：

```python
def _remove_requirements(self, req_path: Path, content: str,
                          reqs: list[dict], nums_str: str) -> None:
    """按用户指定的编号删除需求，重写 requirement.md。"""
    try:
        to_remove = {int(n.strip()) for n in nums_str.split(",") if n.strip()}
    except ValueError:
        self._log("  ⚠ 编号格式不对，跳过删除")
        return
    titles_to_remove = set()
    for idx in to_remove:
        if 1 <= idx <= len(reqs):
            titles_to_remove.add(reqs[idx - 1]["title"])
    if not titles_to_remove:
        return
    # 逐行过滤：删除匹配标题所在的 ## 章节（到下一个 ## 或文件结尾）
    lines = content.split("\n")
    result, skip = [], False
    for line in lines:
        if line.startswith("## REQ-") or line.startswith("## "):
            skip = any(t in line for t in titles_to_remove)
        if not skip:
            result.append(line)
    req_path.write_text("\n".join(result))
    self._log(f"  ✅ 已删除 {len(titles_to_remove)} 条需求")
```

### 6. `ai_loop/orchestrator.py::run_single_round` — REFINE 路径也要走确认

第 157 行 REFINE 分支的 `_call_role("product:explore", ...)` 之后，同样要走一次确认：

```python
if decision.decision == "REFINE":
    self._call_role("product:explore", rnd, round_dir, goals)
    if self._config.human_decision != "low":
        self._confirm_requirements(round_dir)
```

### 7. `ai_loop/roles/product.py` — prompt 中增加"延迟池"模板章节

在两个 explore prompt 的输出模板末尾（`### 验收标准` 之后）追加：

```
### 延迟池（可选）
（优先级不够进入本轮的需求，一句话描述 + 优先级，供下一轮参考）
```

## 验证方式

- 运行 `pytest tests/ -v` 确认现有测试不受影响
- 新增测试 `test_confirm_requirements`：mock `interaction_callback`，验证：
  - `human_decision: "low"` 时跳过确认
  - `human_decision: "high"` 时调用 callback 展示需求列表
  - 用户选 `r` 时 `requirement.md` 被删除
  - 用户选 `d 2,3` 时对应需求被移除
  - 用户选 `a` 时文件不变
- 新增测试 `test_extract_requirements`：验证两种需求格式（`## REQ-N:` 和 `- **[P0] title**`）都能正确提取
- 手动运行 `ai-loop run --human-decision high`，确认需求草案展示和交互流程正常
