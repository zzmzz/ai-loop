import json
import subprocess
import sys
import yaml


# ANSI color helpers
_COLORS = {
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "reset": "\033[0m",
    "bold": "\033[1m",
}


def _c(color: str, text: str) -> str:
    return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


def parse_frontmatter(content: str) -> tuple[dict, str]:
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return {}, content
        return fm, parts[2].strip()
    except yaml.YAMLError:
        return {}, content


class RoleRunner:
    def __init__(self, role_name: str, allowed_tools: list[str]):
        self.role_name = role_name
        self.allowed_tools = allowed_tools

    def call(self, prompt: str, cwd: str, timeout: int = 600, verbose: bool = False) -> str:
        if verbose:
            return self._call_streaming(prompt, cwd, timeout)
        return self._call_quiet(prompt, cwd, timeout)

    def _call_quiet(self, prompt: str, cwd: str, timeout: int) -> str:
        cmd = [
            "claude",
            "-p", prompt,
            "--allowedTools", ",".join(self.allowed_tools),
            "--output-format", "text",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI 调用失败 (role={self.role_name}, "
                f"exit={result.returncode}): {result.stderr[:500]}"
            )
        return result.stdout

    def _call_streaming(self, prompt: str, cwd: str, timeout: int) -> str:
        cmd = [
            "claude",
            "-p", prompt,
            "--allowedTools", ",".join(self.allowed_tools),
            "--output-format", "stream-json",
            "--verbose",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )

        final_result = ""
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._render_event(event)
                if event.get("type") == "result":
                    final_result = event.get("result", "")
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(
                f"Claude CLI 调用失败 (role={self.role_name}, "
                f"exit={proc.returncode}): {stderr[:500]}"
            )
        return final_result

    def _render_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "assistant":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                btype = block.get("type")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    desc = inp.get("description", inp.get("command", inp.get("pattern", "")))
                    if isinstance(desc, str) and len(desc) > 120:
                        desc = desc[:120] + "..."
                    print(f"  {_c('cyan', '⚡')} {_c('bold', name)} {_c('dim', str(desc))}", flush=True)
                elif btype == "text":
                    text = block.get("text", "")
                    if text.strip():
                        # Show first 3 lines of text output
                        lines = text.strip().split("\n")
                        for ln in lines[:3]:
                            print(f"  {_c('dim', '│')} {ln}", flush=True)
                        if len(lines) > 3:
                            print(f"  {_c('dim', '│ ... (' + str(len(lines) - 3) + ' more lines)')}", flush=True)

        elif etype == "user":
            tool_result = event.get("tool_use_result", {})
            if tool_result and isinstance(tool_result, dict):
                stdout = tool_result.get("stdout", "")
                stderr = tool_result.get("stderr", "")
                output = stdout or stderr
                if output:
                    lines = output.strip().split("\n")
                    for ln in lines[:2]:
                        if ln.strip():
                            print(f"  {_c('dim', '  →')} {_c('dim', ln[:100])}", flush=True)
                    if len(lines) > 2:
                        print(f"  {_c('dim', '  → ... (' + str(len(lines) - 2) + ' more lines)')}", flush=True)

        elif etype == "result":
            cost = event.get("total_cost_usd", 0)
            turns = event.get("num_turns", 0)
            duration = event.get("duration_ms", 0)
            print(
                f"  {_c('green', '✓')} "
                f"{_c('dim', f'{turns} turns, {duration/1000:.1f}s, ${cost:.4f}')}",
                flush=True,
            )
