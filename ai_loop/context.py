from pathlib import Path


class ContextCollector:
    """Collects prior-phase artifacts and formats them for prompt injection."""

    PHASE_DEPS = {
        "product:explore": [],
        "developer:design": ["requirement.md"],
        "product:clarify": ["design.md"],
        "developer:implement": ["design.md", "clarification.md"],
        "developer:verify": ["requirement.md"],
        "reviewer:review": ["requirement.md", "design.md", "dev-log.md"],
        "product:acceptance": ["requirement.md", "dev-log.md"],
        "developer:fix_review": ["review.md"],
    }

    def collect(self, role_phase: str, round_dir: Path) -> str:
        """Read dependency files and return formatted context text.

        Returns empty string if no dependencies or no files found.
        """
        deps = self.PHASE_DEPS.get(role_phase, [])
        sections = []
        for fname in deps:
            fpath = round_dir / fname
            if fpath.exists():
                content = fpath.read_text()
                sections.append(f"## {fname}\n\n{content}")
        if not sections:
            return ""
        return "\n---以下是前序阶段的关键产出，供你参考---\n\n" + "\n\n".join(sections)
