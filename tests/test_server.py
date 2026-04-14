from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
import pytest
import requests
from ai_loop.server import DevServer


class TestDevServer:
    def make_server(self, tmp_path: Path) -> DevServer:
        log_file = tmp_path / "server.log"
        return DevServer(
            start_command="echo running",
            cwd=str(tmp_path),
            health_url="http://localhost:12345",
            health_timeout=2,
            stop_signal="SIGTERM",
            log_path=log_file,
        )

    @patch("ai_loop.server.subprocess.Popen")
    @patch("ai_loop.server.requests.get")
    def test_start_waits_for_health(self, mock_get, mock_popen, tmp_path: Path):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_get.return_value = MagicMock(status_code=200)

        server = self.make_server(tmp_path)
        server.start()

        assert server.is_running()
        mock_popen.assert_called_once()
        mock_get.assert_called()

    @patch("ai_loop.server.subprocess.Popen")
    def test_stop_terminates_process(self, mock_popen, tmp_path: Path):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        server = self.make_server(tmp_path)
        server._process = mock_process
        server.stop()

        mock_process.send_signal.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=10)

    @patch("ai_loop.server.subprocess.Popen")
    @patch("ai_loop.server.requests.get")
    def test_start_timeout_raises(self, mock_get, mock_popen, tmp_path: Path):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_get.side_effect = requests.ConnectionError("refused")

        server = self.make_server(tmp_path)
        with pytest.raises(TimeoutError, match="未在"):
            server.start()

    def test_stop_when_not_running_is_noop(self, tmp_path: Path):
        server = self.make_server(tmp_path)
        server.stop()  # should not raise

    @patch("ai_loop.server.subprocess.Popen")
    @patch("ai_loop.server.requests.get")
    def test_start_detects_process_crash(self, mock_get, mock_popen, tmp_path: Path):
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # exited with error
        mock_popen.return_value = mock_process

        server = self.make_server(tmp_path)
        with pytest.raises(RuntimeError, match="退出"):
            server.start()
