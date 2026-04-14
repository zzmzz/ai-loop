import subprocess
import yaml


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

    def call(self, prompt: str, cwd: str, timeout: int = 600) -> str:
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
