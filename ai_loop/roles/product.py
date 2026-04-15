from ai_loop.config import VerificationConfig


class ProductRole:
    def __init__(self, verification: VerificationConfig):
        self.verification = verification

    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
            "explore": self._explore_prompt,
            "clarify": self._clarify_prompt,
            "acceptance": self._acceptance_prompt,
        }
        builder = builders.get(phase)
        if builder is None:
            raise ValueError(f"Unknown product phase: {phase}")
        prompt = builder(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt

    def _explore_prompt(self, round_num, round_dir, goals_text):
        if self.verification.type == "web":
            return self._explore_prompt_web(round_num, round_dir, goals_text)
        return self._explore_prompt_cli(round_num, round_dir, goals_text)

    def _explore_prompt_web(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。你的任务是体验当前产品并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读项目代码摘要（code-digest.md 已附在下方，如有），了解已知项目状态
2. 通过 git diff 查看自上轮以来的代码变更
3. 只针对变更部分深入阅读
4. 编写 Playwright Python 脚本访问 {self.verification.base_url}，像真实用户一样走完主要流程
5. 截图保存到当前工作区的 notes/ 目录
6. 结合代码理解和实际体验，输出需求文档

输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

需求要具体可执行，避免模糊描述。每条需求说清楚"现状是什么"和"期望是什么"。"""

    def _explore_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        return f"""你是产品经理。你的任务是体验当前 CLI 工具并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读项目代码摘要（code-digest.md 已附在下方，如有），了解已知项目状态
2. 通过 git diff 查看自上轮以来的代码变更
3. 只针对变更部分深入阅读
4. 运行以下示例命令，像真实用户一样体验 CLI 行为：
{examples}
5. 运行测试命令了解现有测试覆盖：`{self.verification.test_command}`
6. 结合代码理解和实际体验，输出需求文档

输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

需求要具体可执行，避免模糊描述。每条需求说清楚"现状是什么"和"期望是什么"。"""

    def _clarify_prompt(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。开发者在设计文档中提出了待确认问题，请你回答。

设计文档已附在下方，请找到"待确认问题"章节。

基于你对产品和用户的理解，逐一回答每个问题。
如果某个问题涉及产品方向性决策且你不确定，标注为 NEEDS_HUMAN。

输出文件：{round_dir}/clarification.md

文件头部：
---
round: {round_num}
role: product
phase: clarification
result: null
timestamp: （当前时间 ISO 格式）
---"""

    def _acceptance_prompt(self, round_num, round_dir, goals_text):
        if self.verification.type == "web":
            return self._acceptance_prompt_web(round_num, round_dir, goals_text)
        return self._acceptance_prompt_cli(round_num, round_dir, goals_text)

    def _acceptance_prompt_web(self, round_num, round_dir, goals_text):
        return f"""你是产品经理。你的任务是验收本轮开发成果。

1. 参考下方附带的需求文档
2. 编写 Playwright Python 脚本访问 {self.verification.base_url}，逐条验证需求是否被满足
3. 截图保存到 notes/ 目录，用于对比
4. 输出验收结果

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS 或 FAIL
timestamp: （当前时间 ISO 格式）
---

result 必须是 PASS 或 FAIL。如果 FAIL，逐条列出未通过的需求和原因。"""

    def _acceptance_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        return f"""你是产品经理。你的任务是验收本轮开发成果。

1. 参考下方附带的需求文档
2. 运行测试命令确认全部通过：`{self.verification.test_command}`
3. 执行以下示例命令，验证 CLI 行为符合预期：
{examples}
4. 检查命令输出和生成的文件是否正确
5. 逐条对照需求，判定是否满足

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS 或 FAIL
timestamp: （当前时间 ISO 格式）
---

result 必须是 PASS 或 FAIL。如果 FAIL，逐条列出未通过的需求和原因。"""
