class DeveloperRole:
    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
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

    def _design_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。当前阶段：技术设计。

阅读需求文档：{round_dir}/requirement.md

然后输出实现计划：
- 列出需要创建/修改的文件和路径
- 将任务分解为小步骤（每步 2-5 分钟工作量）
- 每个步骤包含：做什么、改哪个文件、预期结果
- 遵循 YAGNI —— 只设计需求要的，不多做
- 如有不确定的问题，写在 "## 待确认问题" 章节

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

阅读设计文档：{round_dir}/design.md
如有澄清文档也请阅读：{round_dir}/clarification.md（如存在）

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
2. 对照 {round_dir}/requirement.md 检查每个需求点是否有测试覆盖
3. 运行 lint（如有）
4. git diff 检查是否有调试代码遗留

只贴命令输出作为证据，不要用"应该""可能"等措辞。"""

    def _fix_review_prompt(self, round_num, round_dir, goals_text):
        return f"""你是开发者。你收到了代码审查反馈，需要修复。

阅读审查意见：{round_dir}/review.md

处理每条反馈时：
1. 用自己的话复述这条反馈要求什么
2. 去代码里验证：审查者说的对吗？
3. 技术上正确 → 实现修改 + 写测试验证
4. 有合理异议 → 在 dev-log.md 记录理由，标记 DISAGREE
5. 禁止无脑同意

修复完成后重新执行完整验证（测试套件 + lint + diff 检查）。

更新文件：{round_dir}/dev-log.md（追加审查修复记录）"""
