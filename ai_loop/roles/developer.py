class DeveloperRole:
    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
            "develop": self._develop_prompt,
            "design": self._design_prompt,
            "implement": self._implement_prompt,
            "verify": self._verify_prompt,
            "fix_review": self._fix_review_prompt,
        }
        builder = builders.get(phase)
        if builder is None:
            raise ValueError(f"Unknown developer phase: {phase}")
        prompt = builder(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt

    def _develop_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。本次任务包含完整开发周期：设计 → 实现 → 自验证。

需求文档已附在下方，无需再次读取。

## 第一步：评估需求规模并选择开发路径

仔细阅读需求，判断规模：
- **中小需求**（涉及 ≤3 个文件、改动意图清晰）→ 走 **Sketch 路径**
- **大需求**（涉及多模块、架构调整、不确定点多）→ 走 **Specify 路径**

---

## 路径 A：Sketch 路径（中小需求）

1. 调用 /sdd:sketch，传入需求摘要
2. sketch 完成后，将方案要点整理写入 {round_dir}/design.md
3. 暂停并向调度者确认方案：
   输出 sketch 方案摘要 + 关键改动点，然后在末尾附加 {{"needs_input": true}}
4. 收到确认后，按 sketch.md 直接实现（遵循下方 TDD 流程）
5. 完成自验证（见下方）
6. 将开发日志写入 {round_dir}/dev-log.md

## 路径 B：Specify 路径（大需求）

1. **Specify**：调用 /sdd:specify，传入需求摘要
   - 完成后暂停，输出 spec 摘要 + {{"needs_input": true}} 等待确认
2. **Plan**：收到确认后，调用 /sdd:plan
   - 完成后暂停，输出 plan 摘要 + {{"needs_input": true}} 等待确认
3. **Tasks**：收到确认后，调用 /sdd:tasks
   - 完成后暂停，输出 tasks 摘要 + {{"needs_input": true}} 等待确认
4. **Implement**：收到确认后，调用 /sdd:implement 执行实现
5. 将设计摘要写入 {round_dir}/design.md
6. 完成自验证（见下方）
7. 将开发日志写入 {round_dir}/dev-log.md

---

## TDD 实现流程（两条路径共用）

严格遵循 TDD 流程：
1. RED —— 先写一个会失败的测试，描述需求期望的行为
2. 运行测试，确认失败（断言失败，非报错）
3. GREEN —— 写最少的代码让测试通过
4. 运行测试，确认全部通过
5. REFACTOR —— 清理代码，保持测试绿色
6. 重复直到所有需求点覆盖

## 自验证（实现完成后必做）

1. 运行项目完整测试套件，贴出完整输出
2. 检查每个需求点是否有对应测试覆盖
3. 运行 lint（如有）
4. git diff 检查是否有调试代码遗留
5. 检查 pytest 覆盖率报告，确认无关键路径遗漏

禁止用语："应该可以"、"看起来没问题"。只允许贴出命令输出作为证据。

## 输出文件

- {round_dir}/design.md（设计方案）
- {round_dir}/dev-log.md（开发日志：每步做了什么、测试结果、验证输出）

design.md 文件头部：
---
round: {round_num}
role: developer
phase: design
result: null
timestamp: （当前时间 ISO 格式）
---

dev-log.md 文件头部：
---
round: {round_num}
role: developer
phase: dev-log
result: null
timestamp: （当前时间 ISO 格式）
---"""

    def _design_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。当前阶段：技术设计。

需求文档已附在下方，无需再次读取。

请按以下步骤完成设计：

1. 评估需求规模：
   - 涉及 ≤3 个文件、改动意图清晰 → 中小需求
   - 涉及多模块、架构调整、不确定点多 → 大需求

2. 根据规模调用 SDD 工具：
   - 中小需求 → 调用 /sdd:sketch，传入需求摘要
   - 大需求 → 调用 /sdd:specify，传入需求摘要

3. SDD 工具会引导你完成探索和方案收敛。如果遇到需要产品决策的问题，
   在输出末尾附加 {{"needs_input": true}} 标记，等待回答后继续。

4. SDD 产出完成后，将最终方案整理写入：{round_dir}/design.md
   格式要求：目标 + 推荐方案 + 改动点（含文件路径） + 验证方式

输出文件：{round_dir}/design.md

文件头部：
---
round: {round_num}
role: developer
phase: design
result: null
timestamp: （当前时间 ISO 格式）
---"""

    def _implement_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。当前阶段：实现。

设计文档和澄清文档（如有）已附在下方，无需再次读取。

严格遵循 TDD 流程：
1. RED —— 先写一个会失败的测试，描述需求期望的行为
2. 运行测试，确认失败（断言失败，非报错）
3. GREEN —— 写最少的代码让测试通过
4. 运行测试，确认全部通过
5. REFACTOR —— 清理代码，保持测试绿色
6. 重复直到所有需求点覆盖

实现完成后执行自验证：
1. 运行项目完整测试套件，贴出完整输出
2. 检查每个需求点是否有对应测试覆盖
3. 运行 lint（如有）
4. git diff 检查是否有调试代码遗留

实现完成后额外检查：
5. 检查 pytest 覆盖率报告，确认无关键路径遗漏

禁止用语："应该可以"、"看起来没问题"。只允许贴出命令输出作为证据。

输出文件：{round_dir}/dev-log.md（记录每步做了什么、测试结果、验证输出）

文件头部：
---
round: {round_num}
role: developer
phase: dev-log
result: null
timestamp: （当前时间 ISO 格式）
---"""

    def _verify_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。当前阶段：完成前验证。

运行以下验证并在 {round_dir}/dev-log.md 末尾追加验证结果：
1. 运行项目完整测试套件，贴出完整输出
2. 对照下方附带的需求文档检查每个需求点是否有测试覆盖
3. 运行 lint（如有）
4. git diff 检查是否有调试代码遗留
5. 检查 pytest 覆盖率报告（term-missing），确认新增代码已覆盖

只贴命令输出作为证据，不要用"应该""可能"等措辞。"""

    def _fix_review_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。你收到了代码审查反馈，需要修复。

审查意见已附在下方，无需再次读取。

处理每条反馈时：
1. 用自己的话复述这条反馈要求什么
2. 去代码里验证：审查者说的对吗？
3. 技术上正确 → 实现修改 + 写测试验证
4. 有合理异议 → 在 dev-log.md 记录理由，标记 DISAGREE
5. 禁止无脑同意

修复完成后重新执行完整验证（测试套件 + lint + diff 检查）。

更新文件：{round_dir}/dev-log.md（追加审查修复记录）"""
