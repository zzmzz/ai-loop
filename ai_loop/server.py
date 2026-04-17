import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)


class DevServer:
    def __init__(
        self,
        start_command: str,
        cwd: str,
        health_url: str,
        health_timeout: int = 30,
        stop_signal: str = "SIGTERM",
        log_path: Optional[Path] = None,
    ):
        self._start_command = start_command
        self._cwd = cwd
        self._health_url = health_url
        self._health_timeout = health_timeout
        self._stop_signal = getattr(signal, stop_signal, signal.SIGTERM)
        self._log_path = log_path
        self._process: Optional[subprocess.Popen] = None
        self._log_fh = None

    def start(self) -> None:
        if self.is_running():
            return

        self._kill_port_holders()

        self._log_fh = open(self._log_path, "a") if self._log_path else None
        self._process = subprocess.Popen(
            self._start_command,
            shell=True,
            cwd=self._cwd,
            stdout=self._log_fh or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        self._wait_healthy()

    def _kill_port_holders(self) -> None:
        """Kill processes occupying the health-check port before starting."""
        try:
            parsed = urlparse(self._health_url)
            port = parsed.port
            if not port:
                return
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            pids = result.stdout.strip()
            if not pids:
                return
            for pid in pids.split("\n"):
                pid = pid.strip()
                if pid:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        logger.info("Killed process %s on port %d", pid, port)
                    except (ProcessLookupError, ValueError):
                        pass
            time.sleep(0.5)
        except Exception as e:
            logger.warning("Failed to kill port holders: %s", e)

    def _wait_healthy(self) -> None:
        deadline = time.time() + self._health_timeout
        while time.time() < deadline:
            exit_code = self._process.poll()
            if exit_code is not None:
                raise RuntimeError(
                    f"Dev server 进程已退出，退出码: {exit_code}"
                )
            try:
                r = requests.get(self._health_url, timeout=2)
                if r.status_code == 200:
                    return
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(0.5)
        raise TimeoutError(
            f"Dev server 未在 {self._health_timeout}s 内就绪: {self._health_url}"
        )

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.send_signal(self._stop_signal)
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        finally:
            self._process = None
            if self._log_fh is not None:
                self._log_fh.close()
                self._log_fh = None

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
