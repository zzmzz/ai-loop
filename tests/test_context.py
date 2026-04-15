from pathlib import Path
from ai_loop.context import ContextCollector


class TestContextCollector:
    def test_collect_returns_content_for_known_deps(self, tmp_path: Path):
        (tmp_path / "requirement.md").write_text("# Requirement\nFix the login bug")

        collector = ContextCollector()
        result = collector.collect("developer:design", tmp_path)

        assert "requirement.md" in result
        assert "Fix the login bug" in result
        assert "---" in result  # separator present

    def test_collect_skips_missing_files(self, tmp_path: Path):
        # developer:implement depends on design.md and clarification.md
        (tmp_path / "design.md").write_text("# Design\nThe plan")
        # clarification.md does NOT exist

        collector = ContextCollector()
        result = collector.collect("developer:implement", tmp_path)

        assert "design.md" in result
        assert "The plan" in result
        assert "clarification.md" not in result

    def test_collect_returns_empty_for_no_deps(self, tmp_path: Path):
        collector = ContextCollector()
        result = collector.collect("product:explore", tmp_path)

        assert result == ""

    def test_collect_returns_empty_for_unknown_phase(self, tmp_path: Path):
        collector = ContextCollector()
        result = collector.collect("unknown:phase", tmp_path)

        assert result == ""

    def test_collect_includes_multiple_deps(self, tmp_path: Path):
        (tmp_path / "requirement.md").write_text("req content")
        (tmp_path / "design.md").write_text("design content")

        collector = ContextCollector()
        result = collector.collect("reviewer:review", tmp_path)

        assert "requirement.md" in result
        assert "req content" in result
        assert "design.md" in result
        assert "design content" in result

    def test_reviewer_review_includes_dev_log(self, tmp_path: Path):
        """REQ-1: reviewer:review should depend on dev-log.md."""
        (tmp_path / "requirement.md").write_text("req")
        (tmp_path / "design.md").write_text("design")
        (tmp_path / "dev-log.md").write_text("dev log content")

        collector = ContextCollector()
        result = collector.collect("reviewer:review", tmp_path)

        assert "dev-log.md" in result
        assert "dev log content" in result
