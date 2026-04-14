from dataclasses import dataclass
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
        "生成本轮总结。在 details 字段中写一段简洁的轮次总结，"
        "包括：做了什么、结果如何、关键决策和发现。"
        "decision 固定为 PASS。"
    ),
}


@dataclass
class BrainDecision:
    decision: str
    reason: str
    details: str = ""

    @classmethod
    def from_claude_output(cls, raw: str) -> "BrainDecision":
        # Try direct JSON parse
        try:
            data = json.loads(raw.strip())
            return cls(
                decision=data["decision"],
                reason=data.get("reason", ""),
                details=data.get("details", ""),
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
            allowed_tools=["Read", "Glob", "Grep"],
        )
        self._cwd = orchestrator_cwd

    def decide(self, decision_point: str, round_dir: Path) -> BrainDecision:
        file_names = DECISION_POINT_FILES.get(decision_point, [])
        instruction = DECISION_POINT_INSTRUCTIONS.get(decision_point, "")

        file_refs = []
        for fname in file_names:
            fpath = round_dir / fname
            if fpath.exists():
                file_refs.append(f"- {fpath}")

        files_section = "\n".join(file_refs) if file_refs else "（无文件）"

        prompt = f"""你是编排器决策大脑。请阅读以下文件并做出判断。

决策点：{decision_point}
{instruction}

相关文件：
{files_section}

请阅读上述文件后，输出 JSON 格式的决策：
{{"decision": "...", "reason": "一句话理由", "details": "补充细节（可选）"}}

只输出 JSON，不要输出其他内容。"""

        raw_output = self._runner.call(prompt, cwd=self._cwd)
        return BrainDecision.from_claude_output(raw_output)
