from pathlib import Path
import re

MEMORY_SECTION_HEADER = "## 累积记忆"


class MemoryManager:
    def append_memory(self, claude_md: Path, round_num: int, content: str) -> None:
        text = claude_md.read_text()
        round_header = f"### Round {round_num:03d}"

        if MEMORY_SECTION_HEADER not in text:
            text += f"\n{MEMORY_SECTION_HEADER}\n"

        if round_header in text:
            # Append to existing round section
            idx = text.index(round_header)
            next_section = re.search(r"\n### ", text[idx + len(round_header):])
            if next_section:
                insert_pos = idx + len(round_header) + next_section.start()
            else:
                insert_pos = len(text)
            text = text[:insert_pos].rstrip() + "\n" + content + "\n" + text[insert_pos:]
        else:
            # Append new round section at end
            text = text.rstrip() + f"\n\n{round_header}\n{content}\n"

        claude_md.write_text(text)

    def count_rounds(self, claude_md: Path) -> int:
        text = claude_md.read_text()
        return len(re.findall(r"### Round \d{3}", text))

    def update_context(self, claude_md: Path, project_path: str, description: str, goals: list[str]) -> None:
        text = claude_md.read_text()
        goals_text = "\n".join(f"- {g}" for g in goals)
        new_context = (
            f"## 项目上下文\n\n"
            f"项目根目录：{project_path}\n"
            f"项目描述：{description}\n"
            f"当前目标：\n{goals_text}\n"
        )
        text = re.sub(
            r"## 项目上下文.*?(?=\n## )",
            new_context,
            text,
            flags=re.DOTALL,
        )
        claude_md.write_text(text)
