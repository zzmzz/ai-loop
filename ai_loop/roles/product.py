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
6. 回答下方"强制问题"，理清需求本质
7. 按模板输出需求文档

## 强制问题（先回答再写需求）

在写需求前，你必须先在草稿中回答以下问题（答案不需要写入 requirement.md，但必须指导你的需求输出）：
- **目标用户是谁？** 他们现在怎么完成这个任务？
- **现状最大的痛点是什么？** 用户会在哪一步卡住或放弃？
- **最窄的切入点是什么？** 改动最小但体验提升最大的一个点
- **怎么验证做对了？** 用户行为或数据上的可观测变化

## 输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

文件正文按以下模板组织：

### 问题描述
（一段话说清楚要解决什么问题）

### 目标用户
（谁会受益，当前怎么做）

### 具体需求
每条需求格式：
- **[P0/P1/P2] 需求标题**：现状是什么 → 期望是什么

优先级说明：P0=必须做 P1=应该做 P2=可以做

### 不做的事情
（明确排除的范围，避免开发者过度发挥）

### 验收标准
（逐条可验证的条件，与具体需求一一对应）"""

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
6. 回答下方"强制问题"，理清需求本质
7. 按模板输出需求文档

## 强制问题（先回答再写需求）

在写需求前，你必须先在草稿中回答以下问题（答案不需要写入 requirement.md，但必须指导你的需求输出）：
- **目标用户是谁？** 他们现在怎么完成这个任务？
- **现状最大的痛点是什么？** 用户会在哪一步卡住或放弃？
- **最窄的切入点是什么？** 改动最小但体验提升最大的一个点
- **怎么验证做对了？** 用户行为或数据上的可观测变化

## 输出文件：{round_dir}/requirement.md

文件头部必须包含 YAML frontmatter：
---
round: {round_num}
role: product
phase: requirement
result: null
timestamp: （当前时间 ISO 格式）
---

文件正文按以下模板组织：

### 问题描述
（一段话说清楚要解决什么问题）

### 目标用户
（谁会受益，当前怎么做）

### 具体需求
每条需求格式：
- **[P0/P1/P2] 需求标题**：现状是什么 → 期望是什么

优先级说明：P0=必须做 P1=应该做 P2=可以做

### 不做的事情
（明确排除的范围，避免开发者过度发挥）

### 验收标准
（逐条可验证的条件，与具体需求一一对应）"""

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

1. 参考下方附带的需求文档（注意每条需求的优先级 P0/P1/P2）
2. 编写 Playwright Python 脚本访问 {self.verification.base_url}，逐条验证需求是否被满足
3. 每条需求验证前后各截一张图，命名规则：
   - `notes/accept-{{需求编号}}-before.png`（操作前状态）
   - `notes/accept-{{需求编号}}-after.png`（操作后状态）
4. 输出验收结果

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS / PARTIAL / FAIL
timestamp: （当前时间 ISO 格式）
---

## 验收结果判定规则

逐条验证需求，每条给出：
- 需求编号和标题
- 优先级（P0/P1/P2）
- 结果：PASS / FAIL
- 截图路径（before/after）
- FAIL 时附原因

## result 总判定

- **PASS**：所有需求均通过
- **PARTIAL**：P0 全部通过，但存在 P1 或 P2 未通过
- **FAIL**：任何 P0 未通过"""

    def _acceptance_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        return f"""你是产品经理。你的任务是验收本轮开发成果。

1. 参考下方附带的需求文档（注意每条需求的优先级 P0/P1/P2）
2. 运行测试命令确认全部通过：`{self.verification.test_command}`
3. 执行以下示例命令，验证 CLI 行为符合预期：
{examples}
4. 将关键命令输出保存为证据：`notes/accept-{{需求编号}}-output.txt`
5. 逐条对照需求，判定是否满足

输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: acceptance
result: PASS / PARTIAL / FAIL
timestamp: （当前时间 ISO 格式）
---

## 验收结果判定规则

逐条验证需求，每条给出：
- 需求编号和标题
- 优先级（P0/P1/P2）
- 结果：PASS / FAIL
- 证据（截图路径或命令输出文件路径）
- FAIL 时附原因

## result 总判定

- **PASS**：所有需求均通过
- **PARTIAL**：P0 全部通过，但存在 P1 或 P2 未通过
- **FAIL**：任何 P0 未通过"""
