# tests/test_detect.py
"""Unit tests for ai_loop.detect module."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from ai_loop.detect import detect_project_config


class TestDetectProjectConfig:
    @patch("ai_loop.detect.subprocess.run")
    def test_detect_normal_json(self, mock_run):
        """subprocess.run returns valid JSON — should parse correctly."""
        expected = {
            "name": "my-app",
            "description": "A cool app",
            "start_command": "npm start",
            "health_url": "http://localhost:3000",
            "base_url": "http://localhost:3000",
            "goals": ["Improve UX"],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(expected),
            stderr="",
        )
        result = detect_project_config("/tmp/project")
        assert result == expected
        mock_run.assert_called_once()

    @patch("ai_loop.detect.subprocess.run")
    def test_detect_markdown_wrapped_json(self, mock_run):
        """Output wrapped in ```json ... ``` — should strip and parse."""
        data = {"name": "wrapped-app", "description": "test"}
        wrapped = f"```json\n{json.dumps(data)}\n```"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=wrapped,
            stderr="",
        )
        result = detect_project_config("/tmp/project")
        assert result == data

    @patch("ai_loop.detect.subprocess.run")
    def test_detect_json_with_extra_text(self, mock_run):
        """JSON preceded/followed by extra text — should extract via find."""
        data = {"name": "extra-app", "description": "test"}
        raw = f"Here is the config:\n{json.dumps(data)}\nEnd of output."
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=raw,
            stderr="",
        )
        result = detect_project_config("/tmp/project")
        assert result == data

    @patch("ai_loop.detect.subprocess.run")
    def test_detect_timeout(self, mock_run):
        """subprocess.run raises TimeoutExpired — should raise RuntimeError."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        with pytest.raises(RuntimeError, match="项目检测超时"):
            detect_project_config("/tmp/project")

    @patch("ai_loop.detect.subprocess.run")
    def test_detect_nonzero_exit(self, mock_run):
        """Non-zero returncode — should raise RuntimeError with stderr."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Something went wrong",
        )
        with pytest.raises(RuntimeError, match="Something went wrong"):
            detect_project_config("/tmp/project")

    @patch("ai_loop.detect.subprocess.run")
    def test_detect_unparseable_output(self, mock_run):
        """Output with no valid JSON — should raise RuntimeError."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="This is not JSON at all, no braces here.",
            stderr="",
        )
        with pytest.raises(RuntimeError, match="无法解析检测结果"):
            detect_project_config("/tmp/project")
