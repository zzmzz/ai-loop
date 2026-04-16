from pathlib import Path
import pytest
from ai_loop.memory import MemoryManager, MEMORY_SECTION_HEADER


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

    def test_get_all_round_sections(self, tmp_path: Path):
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        mgr.append_memory(md, round_num=1, content="- note1")
        mgr.append_memory(md, round_num=2, content="- note2")

        sections = mgr.get_all_round_sections(md)

        assert len(sections) == 2
        assert sections[0][0] == 1
        assert "note1" in sections[0][1]
        assert sections[1][0] == 2
        assert "note2" in sections[1][1]

    def test_compact_memories_within_window_no_op(self, tmp_path: Path):
        """When round count <= window, compact_memories should not change anything."""
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        for i in range(1, 4):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")

        original = md.read_text()
        mgr.compact_memories(md, window=5, summarizer=lambda t: "should not be called")

        assert md.read_text() == original

    def test_compact_memories_exceeding_window(self, tmp_path: Path):
        """When rounds > window, old rounds should be replaced with summary."""
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        for i in range(1, 8):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")

        mgr.compact_memories(md, window=3, summarizer=lambda t: "compressed summary")

        text = md.read_text()
        assert "### 历史摘要" in text
        assert "compressed summary" in text
        # Old rounds should be gone
        assert "### Round 001" not in text
        assert "### Round 002" not in text
        assert "### Round 003" not in text
        assert "### Round 004" not in text

    def test_compact_memories_preserves_recent(self, tmp_path: Path):
        """Recent N rounds within window should be preserved intact."""
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        for i in range(1, 8):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")

        mgr.compact_memories(md, window=3, summarizer=lambda t: "summary")

        text = md.read_text()
        # Last 3 rounds should be preserved
        assert "### Round 005" in text
        assert "### Round 006" in text
        assert "### Round 007" in text
        assert "Round 5 note" in text
        assert "Round 7 note" in text

    def test_compact_memories_with_existing_summary(self, tmp_path: Path):
        """When there's already a 历史摘要, it should be included in compression."""
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        for i in range(1, 6):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")

        # First compaction
        mgr.compact_memories(md, window=2, summarizer=lambda t: "first summary")

        # Add more rounds
        for i in range(6, 9):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")

        # Second compaction - should include old summary in text to compress
        received_texts = []
        def capture_summarizer(t):
            received_texts.append(t)
            return "merged summary"

        mgr.compact_memories(md, window=2, summarizer=capture_summarizer)

        text = md.read_text()
        assert "merged summary" in text
        # The old summary should have been passed to summarizer
        assert "first summary" in received_texts[0]

    def test_compact_memories_no_header_returns_safely(self, tmp_path: Path):
        """compact_memories should return without error when header is missing."""
        md = tmp_path / "CLAUDE.md"
        md.write_text("# Role: Product\n\nSome content without memory header.\n")
        mgr = MemoryManager()

        # Should not raise ValueError
        mgr.compact_memories(md, window=3, summarizer=lambda t: "should not be called")

        # File should be unchanged
        assert md.read_text() == "# Role: Product\n\nSome content without memory header.\n"

    def test_get_all_round_sections_skips_history_summary(self, tmp_path: Path):
        """get_all_round_sections should only return Round sections, not 历史摘要."""
        md = self._make_claude_md(tmp_path)
        mgr = MemoryManager()
        for i in range(1, 6):
            mgr.append_memory(md, round_num=i, content=f"- Round {i} note")
        # Compact to create a 历史摘要 section
        mgr.compact_memories(md, window=2, summarizer=lambda t: "historical summary")

        sections = mgr.get_all_round_sections(md)

        # Should only return the 2 recent rounds, not the summary
        assert len(sections) == 2
        round_nums = [s[0] for s in sections]
        assert 4 in round_nums
        assert 5 in round_nums
        # Verify summary exists but is not in sections
        text = md.read_text()
        assert "### 历史摘要" in text
        assert "historical summary" in text


class TestRefreshTemplate:
    def test_replaces_template_preserves_memory(self, tmp_path: Path):
        md = tmp_path / "CLAUDE.md"
        md.write_text(
            "# Role: Old\n\nOld instructions.\n\n"
            "## 累积记忆\n\n### Round 001\n- important note\n"
        )
        new_template = "# Role: New\n\nNew instructions.\n\n## 累积记忆\n"

        result = MemoryManager.refresh_template(md, new_template)

        assert result is True
        text = md.read_text()
        assert "# Role: New" in text
        assert "New instructions." in text
        assert "Old instructions." not in text
        assert "### Round 001" in text
        assert "important note" in text

    def test_no_change_returns_false(self, tmp_path: Path):
        md = tmp_path / "CLAUDE.md"
        md.write_text(
            "# Role: Same\n\nSame instructions.\n\n"
            "## 累积记忆\n\n### Round 001\n- note\n"
        )
        new_template = "# Role: Same\n\nSame instructions.\n\n## 累积记忆\n"

        result = MemoryManager.refresh_template(md, new_template)

        assert result is False

    def test_file_without_memory_header(self, tmp_path: Path):
        md = tmp_path / "CLAUDE.md"
        md.write_text("# Role: Legacy\n\nOld content only.\n")
        new_template = "# Role: Updated\n\nNew content.\n\n## 累积记忆\n"

        result = MemoryManager.refresh_template(md, new_template)

        assert result is True
        text = md.read_text()
        assert "# Role: Updated" in text
        assert MEMORY_SECTION_HEADER in text
        assert "Old content only." not in text

    def test_preserves_compacted_history(self, tmp_path: Path):
        md = tmp_path / "CLAUDE.md"
        md.write_text(
            "# Role: Dev\n\n## 累积记忆\n\n"
            "### 历史摘要\ncompressed info\n\n"
            "### Round 005\n- recent note\n"
        )
        new_template = "# Role: Dev v2\n\nUpdated instructions.\n\n## 累积记忆\n"

        result = MemoryManager.refresh_template(md, new_template)

        assert result is True
        text = md.read_text()
        assert "# Role: Dev v2" in text
        assert "### 历史摘要" in text
        assert "compressed info" in text
        assert "### Round 005" in text
        assert "recent note" in text
