from pathlib import Path

from ai_loop.config import VerificationConfig


class ProductRole:
    def __init__(self, verification: VerificationConfig, knowledge_dir: Path):
        self.verification = verification
        self._knowledge_dir = knowledge_dir

    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        builders = {
            "explore": self._explore_prompt,
            "clarify": self._clarify_prompt,
            "qa_acceptance": self._qa_acceptance_prompt,
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
        kd = self._knowledge_dir
        return f"""你是产品经理。你的任务是体验当前产品并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读 product-knowledge/index.md（已附在下方，如有），根据本轮目标 Read 相关子文档，快速恢复产品认知
2. 阅读项目代码摘要（code-digest.md 已附在下方，如有），了解已知项目状态
3. 通过 git diff 查看自上轮以来的代码变更
4. 只针对变更部分深入阅读
5. 编写 Playwright Python 脚本访问 {self.verification.base_url}，像真实用户一样走完主要流程
6. 截图保存到当前工作区的 notes/ 目录
7. 回答下方"强制问题"，理清需求本质
8. 按模板输出需求文档
9. 更新产品认知文档：将本次探索的新发现写入 `{kd}/` 目录

{self._knowledge_maintenance_instruction()}

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

**数量约束：每轮最多 3 条需求（1 条 P0 + 至多 2 条 P1/P2）。**
如果发现的问题超过 3 个，只保留优先级最高的 3 条写入本章节，其余写入末尾的"延迟池"。

每条需求格式：
- **[P0/P1/P2] 需求标题**：现状是什么 → 期望是什么

优先级说明：P0=必须做 P1=应该做 P2=可以做

### 不做的事情
（明确排除的范围，避免开发者过度发挥）

### 验收标准
（逐条可验证的条件，与具体需求一一对应）

### 延迟池（可选）
（优先级不够进入本轮的需求，一句话描述 + 优先级，供下一轮参考）"""

    def _explore_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        kd = self._knowledge_dir
        return f"""你是产品经理。你的任务是体验当前 CLI 工具并提出改进需求。

当前目标：
{goals_text}

工作步骤：
1. 阅读 product-knowledge/index.md（已附在下方，如有），根据本轮目标 Read 相关子文档，快速恢复产品认知
2. 阅读项目代码摘要（code-digest.md 已附在下方，如有），了解已知项目状态
3. 通过 git diff 查看自上轮以来的代码变更
4. 只针对变更部分深入阅读
5. 运行以下示例命令，像真实用户一样体验 CLI 行为：
{examples}
6. 运行测试命令了解现有测试覆盖：`{self.verification.test_command}`
7. 回答下方"强制问题"，理清需求本质
8. 按模板输出需求文档
9. 更新产品认知文档：将本次探索的新发现写入 `{kd}/` 目录

{self._knowledge_maintenance_instruction()}

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

**数量约束：每轮最多 3 条需求（1 条 P0 + 至多 2 条 P1/P2）。**
如果发现的问题超过 3 个，只保留优先级最高的 3 条写入本章节，其余写入末尾的"延迟池"。

每条需求格式：
- **[P0/P1/P2] 需求标题**：现状是什么 → 期望是什么

优先级说明：P0=必须做 P1=应该做 P2=可以做

### 不做的事情
（明确排除的范围，避免开发者过度发挥）

### 验收标准
（逐条可验证的条件，与具体需求一一对应）

### 延迟池（可选）
（优先级不够进入本轮的需求，一句话描述 + 优先级，供下一轮参考）"""

    def _knowledge_maintenance_instruction(self):
        kd = self._knowledge_dir
        return f"""## 产品认知文档维护

目录：`{kd}/`

维护规则：
- 使用 Write 工具写入文件，仅限 `{kd}/` 目录
- 按业务域拆分子文档（如 auth.md、export.md），每个域一个文件
- 同步维护 `{kd}/index.md` 索引

index.md 格式：
```
# 产品认知索引

| 业务域 | 文件 | 概述 | 最后更新 |
|--------|------|------|----------|
| 用户认证 | auth.md | 登录/注册/权限体系 | Round 3 |
```

子文档格式：
```
# {{业务域名称}}

## 功能概述
（这个域包含哪些功能，面向谁）

## 体验现状
（当前的交互流程和体验质量）

## 已知问题
（发现但未解决的问题，按优先级排列）

## 改进历史
- Round N: 改了什么 → 效果如何
```

要求：
- 已有子文档做增量更新，不要全量重写
- 已解决的问题从"已知问题"移到"改进历史"
- 新发现的业务域创建新文件并更新 index"""

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

    def _qa_acceptance_prompt(self, round_num, round_dir, goals_text):
        if self.verification.type == "web":
            return self._qa_acceptance_prompt_web(round_num, round_dir, goals_text)
        return self._qa_acceptance_prompt_cli(round_num, round_dir, goals_text)

    def _qa_acceptance_prompt_web(self, round_num, round_dir, goals_text):
        kd = self._knowledge_dir
        return f"""你是 QA 工程师兼产品经理。你的任务是对本轮开发成果进行系统化测试与验收。

当前目标：
{goals_text}

## 工作流程

### 第一阶段：需求验证（必做）

1. 参考下方附带的需求文档（注意每条需求的优先级 P0/P1/P2）
2. 编写 Playwright Python 脚本访问 {self.verification.base_url}，逐条验证需求是否被满足
3. 每条需求验证前后各截一张图作为证据：
   - `notes/accept-{{需求编号}}-before.png`（操作前状态）
   - `notes/accept-{{需求编号}}-after.png`（操作后状态）

### 第二阶段：系统化探索（必做）

需求验证完成后，主动探索产品寻找需求未覆盖的问题：

1. **核心流程走查**：从用户视角走完主要业务流程，关注边界情况
2. **交互完整性**：检查按钮响应、表单验证、错误提示、加载状态
3. **跨页面一致性**：导航、布局、样式在不同页面间是否一致
4. **异常场景**：网络错误、空数据、超长输入、并发操作
5. 每个发现的问题都截图保存到 `notes/explore-{{序号}}.png`

### 第三阶段：汇总评估

1. 对所有发现的问题进行分级
2. 计算健康评分
3. 更新 `{kd}/` 下的相关产品认知子文档

## 问题严重级别

- **Critical**：功能完全不可用、数据丢失、安全漏洞 — 必须立即修复
- **High**：核心流程受阻、严重影响用户体验 — 应在本轮修复
- **Medium**：非核心功能异常、体验不佳但有 workaround — 建议下轮处理
- **Low**：美观问题、文案优化、边缘场景 — 记入延迟池

## 输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: qa_acceptance
result: PASS / PARTIAL / FAIL
timestamp: （当前时间 ISO 格式）
---

文件正文按以下结构组织：

### 需求验证

| 需求 | 优先级 | 结果 | 证据 | 备注 |
|------|--------|------|------|------|
| REQ-N: 标题 | P0/P1/P2 | PASS/FAIL | notes/accept-N-after.png | FAIL 时附原因 |

### 探索发现

| # | 问题描述 | 严重级别 | 证据 | 建议 |
|---|----------|----------|------|------|
| 1 | 描述 | Critical/High/Medium/Low | notes/explore-1.png | 修复建议 |

### 健康评分

**总分: X / 100**

| 维度 | 得分 | 说明 |
|------|------|------|
| 需求满足 | /50 | P0 全过 +30，P1 每条 +10，P2 每条 +5 |
| 功能稳定性 | /25 | 无 Critical=25，有 Critical=0，每个 High -5 |
| 用户体验 | /25 | 基于探索发现的 Medium/Low 问题数量扣分 |

### 总判定

result: PASS / PARTIAL / FAIL
reason: 一句话总结

### 延迟池

列出非本轮范围的发现（Medium/Low），供下轮参考

## result 总判定规则

- **PASS**：所有需求通过，无 Critical/High 探索发现，健康评分 ≥ 80
- **PARTIAL**：P0 全部通过但存在 P1/P2 未通过，或有 High 探索发现，健康评分 60-79
- **FAIL**：任何 P0 未通过，或有 Critical 探索发现，或健康评分 < 60"""

    def _qa_acceptance_prompt_cli(self, round_num, round_dir, goals_text):
        examples = "\n".join(f"  - `{e}`" for e in self.verification.run_examples)
        kd = self._knowledge_dir
        return f"""你是 QA 工程师兼产品经理。你的任务是对本轮开发成果进行系统化测试与验收。

当前目标：
{goals_text}

## 工作流程

### 第一阶段：需求验证（必做）

1. 参考下方附带的需求文档（注意每条需求的优先级 P0/P1/P2）
2. 运行测试命令确认全部通过：`{self.verification.test_command}`
3. 执行以下示例命令，验证 CLI 行为符合预期：
{examples}
4. 将关键命令输出保存为证据：`notes/accept-{{需求编号}}-output.txt`

### 第二阶段：系统化探索（必做）

需求验证完成后，主动探索产品寻找需求未覆盖的问题：

1. **边界输入测试**：空参数、超长参数、特殊字符、无效路径
2. **错误处理**：各命令的错误提示是否清晰、退出码是否正确
3. **帮助信息**：--help 输出是否完整准确
4. **兼容性**：不同参数组合是否正常工作
5. 每个发现的问题保存命令输出到 `notes/explore-{{序号}}-output.txt`

### 第三阶段：汇总评估

1. 对所有发现的问题进行分级
2. 计算健康评分
3. 更新 `{kd}/` 下的相关产品认知子文档

## 问题严重级别

- **Critical**：功能完全不可用、数据丢失、安全漏洞 — 必须立即修复
- **High**：核心流程受阻、严重影响用户体验 — 应在本轮修复
- **Medium**：非核心功能异常、体验不佳但有 workaround — 建议下轮处理
- **Low**：美观问题、文案优化、边缘场景 — 记入延迟池

## 输出文件：{round_dir}/acceptance.md

文件头部：
---
round: {round_num}
role: product
phase: qa_acceptance
result: PASS / PARTIAL / FAIL
timestamp: （当前时间 ISO 格式）
---

文件正文按以下结构组织：

### 需求验证

| 需求 | 优先级 | 结果 | 证据 | 备注 |
|------|--------|------|------|------|
| REQ-N: 标题 | P0/P1/P2 | PASS/FAIL | notes/accept-N-output.txt | FAIL 时附原因 |

### 探索发现

| # | 问题描述 | 严重级别 | 证据 | 建议 |
|---|----------|----------|------|------|
| 1 | 描述 | Critical/High/Medium/Low | notes/explore-1-output.txt | 修复建议 |

### 健康评分

**总分: X / 100**

| 维度 | 得分 | 说明 |
|------|------|------|
| 需求满足 | /50 | P0 全过 +30，P1 每条 +10，P2 每条 +5 |
| 功能稳定性 | /25 | 无 Critical=25，有 Critical=0，每个 High -5 |
| 用户体验 | /25 | 基于探索发现的 Medium/Low 问题数量扣分 |

### 总判定

result: PASS / PARTIAL / FAIL
reason: 一句话总结

### 延迟池

列出非本轮范围的发现（Medium/Low），供下轮参考

## result 总判定规则

- **PASS**：所有需求通过，无 Critical/High 探索发现，健康评分 ≥ 80
- **PARTIAL**：P0 全部通过但存在 P1/P2 未通过，或有 High 探索发现，健康评分 60-79
- **FAIL**：任何 P0 未通过，或有 Critical 探索发现，或健康评分 < 60"""
