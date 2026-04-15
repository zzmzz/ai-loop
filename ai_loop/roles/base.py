import json
import subprocess
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

    def call(self, prompt: str, cwd: str, timeout: int = 600,
             verbose: bool = False,
             interaction_callback=None) -> str:
        cmd = [
            "claude",
            "--output-format", "stream-json",
            "--input-format", "stream-json",
            "--permission-prompt-tool", "stdio",
        ]
        if verbose:
            cmd.append("--verbose")
        if self.allowed_tools:
            cmd += ["--allowedTools", ",".join(self.allowed_tools)]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )

        # Send initial prompt
        self._send_message(proc, prompt)

        final_result = ""
        self._last_stats = {"duration_ms": 0, "cost_usd": 0, "turns": 0}
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")

                if etype == "control_request":
                    self._handle_control_request(proc, event)
                elif etype == "result":
                    self._last_stats = {
                        "duration_ms": event.get("duration_ms", 0),
                        "cost_usd": event.get("total_cost_usd", 0),
                        "turns": event.get("num_turns", 0),
                    }
                    result_text = event.get("result", "")
                    if interaction_callback and self._has_needs_input(result_text):
                        question = self._extract_question(result_text)
                        answer = interaction_callback(question)
                        self._send_message(proc, answer)
                    else:
                        final_result = result_text
                        break
                elif verbose:
                    self._render_event(event)

            proc.stdin.close()
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError(
                f"Claude CLI 调用超时 (role={self.role_name}, "
                f"timeout={timeout}s)"
            )

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(
                f"Claude CLI 调用失败 (role={self.role_name}, "
                f"exit={proc.returncode}): {stderr[:500]}"
            )
        return final_result

    @property
    def last_stats(self) -> dict:
        """Stats from the most recent call: duration_ms, cost_usd, turns."""
        return getattr(self, "_last_stats", {"duration_ms": 0, "cost_usd": 0, "turns": 0})

    def _send_message(self, proc, content: str) -> None:
        msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": content},
        })
        proc.stdin.write(msg + "\n")
        proc.stdin.flush()

    def _handle_control_request(self, proc, event: dict) -> None:
        request_id = event.get("request_id", "")
        request = event.get("request", {})
        input_data = request.get("input", {})
        response = json.dumps({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": {
                    "behavior": "allow",
                    "updatedInput": input_data,
                },
            },
        })
        proc.stdin.write(response + "\n")
        proc.stdin.flush()

    @staticmethod
    def _has_needs_input(text: str) -> bool:
        return '{"needs_input": true}' in text or '{"needs_input":true}' in text

    @staticmethod
    def _extract_question(text: str) -> str:
        for marker in ('{"needs_input": true}', '{"needs_input":true}'):
            if marker in text:
                return text[:text.rfind(marker)].strip()
        return text.strip()

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
                        lines = text.strip().split("\n")
                        for ln in lines[:3]:
                            print(f"  {_c('dim', '│')} {ln}", flush=True)
                        if len(lines) > 3:
                            print(f"  {_c('dim', '│ ... (' + str(len(lines) - 3) + ' more lines)')}", flush=True)

        elif etype == "result":
            cost = event.get("total_cost_usd", 0)
            turns = event.get("num_turns", 0)
            duration = event.get("duration_ms", 0)
            print(
                f"  {_c('green', '✓')} "
                f"{_c('dim', f'{turns} turns, {duration/1000:.1f}s, ${cost:.4f}')}",
                flush=True,
            )
