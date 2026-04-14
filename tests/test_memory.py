from pathlib import Path
import pytest
from ai_loop.memory import MemoryManager


class TestMemoryManager:
    def _make_claude_md(self, path: Path) -> Path:
        md = path / "CLAUDE.md"
        md.write_text(
            "# Role: Product\n\n"
            "## 身份与工作方法\nI am product.\n\n"
            "## 项目上下文\nSome context.\n\n"
            "## 累积记忆\n"
        )
        return md

    def test_append_memory(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()

        mgr.append_memory(md, round_num=1, content="- Discovered login UX issue")

        text = md.read_text()
        assert "### Round 001" in text
        assert "Discovered login UX issue" in text

    def test_append_multiple_rounds(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()

        mgr.append_memory(md, round_num=1, content="- Round 1 note")
        mgr.append_memory(md, round_num=2, content="- Round 2 note")

        text = md.read_text()
        assert "### Round 001" in text
        assert "### Round 002" in text
        assert "Round 1 note" in text
        assert "Round 2 note" in text

    def test_does_not_duplicate_section(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()

        mgr.append_memory(md, round_num=1, content="- Note A")
        mgr.append_memory(md, round_num=1, content="- Note B")

        text = md.read_text()
        assert text.count("### Round 001") == 1
        assert "Note A" in text
        assert "Note B" in text

    def test_preserves_static_sections(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()

        mgr.append_memory(md, round_num=1, content="- Note")

        text = md.read_text()
        assert "# Role: Product" in text
        assert "## 身份与工作方法" in text
        assert "I am product." in text

    def test_count_rounds(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()

        for i in range(1, 6):
            mgr.append_memory(md, round_num=i, content=f"- Round {i}")

        assert mgr.count_rounds(md) == 5
