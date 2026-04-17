from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from ai_loop.roles.base import RoleRunner

DECISION_POINT_FILES = {
    "post_requirement": ["requirement.md"],
    "post_development": ["requirement.md", "design.md", "dev-log.md"],
    "post_design": ["requirement.md", "design.md"],
    "post_implementation": ["requirement.md", "design.md", "dev-log.md"],
    "post_acceptance": ["requirement.md", "acceptance.md"],
    "round_summary": ["requirement.md", "design.md", "dev-log.md", "acceptance.md"],
}

DECISION_POINT_INSTRUCTIONS = {
    "post_requirement": (
        "判断这份需求文档是否足够清晰、具体、可执行。"
        "可选决策：PROCEED（清晰可执行）/ REFINE（需要产品重新细化）"
    ),
    "post_development": (
        "逐项对照需求文档的验收标准与 dev-log.md 中的实现证据：\n"
        "1. **验收标准逐项核实**：需求中每条验收标准，在 dev-log 中是否有明确的通过证据（测试结果、代码位置、截图等）？列出无证据项。\n"
        "2. **测试覆盖**：dev-log 声称的测试是否覆盖了需求中的关键场景？是否有边界条件遗漏？\n"
        "3. **设计一致性**：实现是否偏离了 design.md 的方案？如有偏离，是否合理？\n"
        "4. **回归风险**：是否有测试失败未修复？是否引入了已知问题？\n\n"
        "输出格式：先输出检查清单（每项标注 PASS/FAIL + 简要说明），再输出汇总决策。\n"
        "可选决策：PROCEED（全部 PASS 或 FAIL 项不影响核心功能）/ RETRY（有关键 FAIL 项，需重做）"
    ),
    "post_design": (
        "逐项对照需求文档和设计文档，按以下检查清单评审：\n"
        "1. **验收标准覆盖**：需求中的每条验收标准，设计中是否有对应的实现方案？列出未覆盖项。\n"
        "2. **数值与范围一致性**：需求中提到的具体数值（区间、阈值、格式、枚举值），设计中是否完全一致？列出不一致项。\n"
        "3. **兼容性**：改动是否考虑了已有数据、已有接口、已有存储的向后兼容？是否有数据迁移需要？\n"
        "4. **遗漏检查**：需求明确说「要做」但设计中未提及的内容。\n"
        "5. **不做的事情**：设计是否越界做了需求明确说「不做」的事？\n\n"
        "输出格式：先输出检查清单（每项标注 PASS/FAIL + 简要说明），再输出汇总决策。\n"
        "可选决策：PROCEED（全部 PASS）/ CLARIFY（有待确认问题需要产品回答）/ REDO（有 FAIL 项，设计需修正）"
    ),
    "post_implementation": (
        "判断实现是否完整，验证是否充分。"
        "可选决策：PROCEED（实现完整）/ RETRY（有遗漏或验证不充分）"
    ),
    "post_acceptance": (
        "评估 QA 测试与验收结果。acceptance.md 包含需求验证、探索发现和健康评分。\n"
        "重点关注：1) 需求验证是否全部通过 2) 探索发现中是否有 Critical/High 问题 3) 健康评分是否达标。\n"
        "可选决策：PASS（验收通过，健康评分 ≥ 80，无 Critical/High）"
        "/ PARTIAL_OK（P0 全过、无 Critical，有 High 但可接受，进入下一轮处理）"
        "/ FAIL_IMPL（P0 未通过或有 Critical 探索发现，属实现问题，需开发修复）"
        "/ FAIL_REQ（需求不清导致，需产品重新定义）/ ESCALATE（需人类介入）"
    ),
    "round_summary": (
        "生成本轮总结。输出 JSON 格式：\n"
        '{"decision": "PASS", "reason": "一句话总结", '
        '"details": "完整轮次总结", '
        '"memories": {"product": "...", "developer": "..."}}\n'
        "memories 中为各角色生成差异化的记忆内容：\n"
        "- product：侧重需求变更、用户反馈、验收结果、QA 发现\n"
        "- developer：侧重技术决策、架构变更、代码模式\n"
    ),
}


@dataclass
class BrainDecision:
    decision: str
    reason: str
    details: str = ""
    memories: dict = field(default_factory=dict)

    @classmethod
    def from_claude_output(cls, raw: str) -> "BrainDecision":
        # Try direct JSON parse
        try:
            data = json.loads(raw.strip())
            return cls(
                decision=data["decision"],
                reason=data.get("reason", ""),
                details=data.get("details", ""),
                memories=data.get("memories", {}),
            )
        except (json.JSONDecodeError, KeyError):
            pass

        # Try extracting JSON from markdown code block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                return cls(
                    decision=data["decision"],
                    reason=data.get("reason", ""),
                    details=data.get("details", ""),
                    memories=data.get("memories", {}),
                )
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: assume PROCEED
        return cls(
            decision="PROCEED",
            reason="Fallback: could not parse Brain output as JSON",
            details=raw[:500],
        )


class Brain:
    def __init__(self, orchestrator_cwd: str):
        self._runner = RoleRunner(
            role_name="brain",
            allowed_tools=[],
        )
        self._cwd = orchestrator_cwd

    def decide(self, decision_point: str, round_dir: Path) -> BrainDecision:
        file_names = DECISION_POINT_FILES.get(decision_point, [])
        instruction = DECISION_POINT_INSTRUCTIONS.get(decision_point, "")

        file_refs = []
        for fname in file_names:
            fpath = round_dir / fname
            if fpath.exists():
                content = fpath.read_text()
                file_refs.append(f"### {fname}\n\n{content}")

        files_section = "\n\n".join(file_refs) if file_refs else "（无文件）"

        if decision_point == "round_summary":
            # round_summary instruction already specifies its own JSON schema (with memories field)
            format_hint = "按上述格式输出 JSON，不要输出其他内容。"
        else:
            format_hint = (
                '输出 JSON 格式的决策：\n'
                '{{"decision": "...", "reason": "一句话理由", "details": "补充细节（可选）"}}\n\n'
                '只输出 JSON，不要输出其他内容。'
            )

        prompt = f"""你是编排器决策大脑。根据以下文件内容做出判断。

决策点：{decision_point}
{instruction}

相关文件内容：
{files_section}

根据上述文件内容，{format_hint}"""

        raw_output = self._runner.call(prompt, cwd=self._cwd)
        return BrainDecision.from_claude_output(raw_output)

    def generate_code_digest(self, project_path: str, digest_path: Path,
                             tree_output: str, diff_output: str) -> None:
        existing = ""
        if digest_path.exists():
            existing = digest_path.read_text()

        if existing:
            prompt = f"""你是项目代码分析助手。请根据以下信息更新项目代码摘要。

当前摘要：
{existing}

目录结构：
{tree_output}

自上轮以来的代码变更（git diff）：
{diff_output}

请更新摘要，只修改变更涉及的部分。输出完整的更新后摘要，不要输出其他内容。"""
        else:
            prompt = f"""你是项目代码分析助手。请根据以下信息生成项目代码摘要。

项目路径：{project_path}

目录结构：
{tree_output}

最近代码变更（git diff）：
{diff_output}

生成一份结构化的代码摘要，包括：项目架构、主要模块、关键文件及其职责。
不超过 1000 字。只输出摘要文本，不要输出其他内容。"""

        result = self._runner.call(prompt, cwd=self._cwd)
        digest_path.write_text(result)

    def summarize_memories(self, old_memories_text: str) -> str:
        prompt = f"""你是记忆压缩助手。将以下多轮记忆合并为一段不超过 500 字的概括性摘要。
保留关键决策、发现和模式，去除冗余细节。只输出摘要文本，不要输出其他内容。

待压缩的记忆：
{old_memories_text}"""
        return self._runner.call(prompt, cwd=self._cwd)
