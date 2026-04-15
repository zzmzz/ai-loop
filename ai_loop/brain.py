from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from ai_loop.roles.base import RoleRunner

DECISION_POINT_FILES = {
    "post_requirement": ["requirement.md"],
    "post_design": ["requirement.md", "design.md"],
    "post_implementation": ["requirement.md", "design.md", "dev-log.md"],
    "post_review": ["requirement.md", "review.md"],
    "post_acceptance": ["requirement.md", "acceptance.md"],
    "round_summary": ["requirement.md", "design.md", "dev-log.md", "review.md", "acceptance.md"],
}

DECISION_POINT_INSTRUCTIONS = {
    "post_requirement": (
        "判断这份需求文档是否足够清晰、具体、可执行。"
        "可选决策：PROCEED（清晰可执行）/ REFINE（需要产品重新细化）"
    ),
    "post_design": (
        "判断这份设计是否合理、是否与需求匹配。"
        "可选决策：PROCEED（合理）/ CLARIFY（有待确认问题需要产品回答）/ REDO（设计偏离需求，需重做）"
    ),
    "post_implementation": (
        "判断实现是否完整，验证是否充分。"
        "可选决策：PROCEED（实现完整）/ RETRY（有遗漏或验证不充分）"
    ),
    "post_review": (
        "评估审查反馈的合理性和严重程度。"
        "可选决策：APPROVE（无需修改或已批准）/ REWORK（有 Critical/Important 需修复）"
        "/ SKIP_MINOR（只有 Minor 问题，可跳过）/ ESCALATE（需人类介入）"
    ),
    "post_acceptance": (
        "评估验收结果。"
        "可选决策：PASS（验收通过）/ FAIL_IMPL（实现问题，需开发修复）"
        "/ FAIL_REQ（需求不清导致，需产品重新定义）/ ESCALATE（需人类介入）"
    ),
    "round_summary": (
        "生成本轮总结。输出 JSON 格式：\n"
        '{"decision": "PASS", "reason": "一句话总结", '
        '"details": "完整轮次总结", '
        '"memories": {"product": "...", "developer": "...", "reviewer": "..."}}\n'
        "memories 中为各角色生成差异化的记忆内容：\n"
        "- product：侧重需求变更、用户反馈、验收结果\n"
        "- developer：侧重技术决策、架构变更、代码模式\n"
        "- reviewer：侧重审查发现的模式、反复出现的问题\n"
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
