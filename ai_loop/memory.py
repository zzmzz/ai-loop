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

    def get_all_round_sections(self, claude_md: Path) -> list[tuple[int, str]]:
        text = claude_md.read_text()
        pattern = r"### Round (\d{3})\n(.*?)(?=\n### |\Z)"
        matches = re.findall(pattern, text, re.DOTALL)
        return [(int(num), content.strip()) for num, content in matches]

    def compact_memories(self, claude_md: Path, window: int, summarizer) -> None:
        sections = self.get_all_round_sections(claude_md)
        if len(sections) <= window:
            return

        text = claude_md.read_text()
        if MEMORY_SECTION_HEADER not in text:
            return
        mem_idx = text.index(MEMORY_SECTION_HEADER)
        before_mem = text[:mem_idx + len(MEMORY_SECTION_HEADER)]

        # Collect existing summary if present
        existing_summary = ""
        summary_match = re.search(
            r"### 历史摘要\n(.*?)(?=\n### |\Z)", text, re.DOTALL
        )
        if summary_match:
            existing_summary = summary_match.group(1).strip()

        # Split into old (to compress) and recent (to keep)
        old_sections = sections[:-window]
        recent_sections = sections[-window:]

        # Build text to compress
        old_text_parts = []
        if existing_summary:
            old_text_parts.append(existing_summary)
        for rnd, content in old_sections:
            old_text_parts.append(f"### Round {rnd:03d}\n{content}")
        old_text = "\n\n".join(old_text_parts)

        summary = summarizer(old_text)

        # Rebuild memory section
        new_mem = f"\n### 历史摘要\n{summary}\n"
        for rnd, content in recent_sections:
            new_mem += f"\n### Round {rnd:03d}\n{content}\n"

        claude_md.write_text(before_mem + new_mem)

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
