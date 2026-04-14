# ai_loop/detect.py
"""Use Claude Code to auto-detect project configuration."""
import json
import subprocess


DETECT_PROMPT = """\
分析当前项目目录，检测以下信息并以 JSON 格式输出（不要输出其他内容）：

{
  "name": "项目名称（基于目录名或 package.json/pyproject.toml 中的 name）",
  "description": "一句话描述这个项目是做什么的",
  "start_command": "启动 dev server 的命令（如 pnpm dev, npm start, yarn dev, cargo run 等）",
  "health_url": "dev server 启动后的健康检查 URL（如 http://localhost:3000）",
  "base_url": "浏览器访问的 URL（通常和 health_url 一样）",
  "goals": ["基于项目现状，建议的一个改进目标"]
}

检测规则：
1. 读取 package.json 的 scripts.dev / scripts.start 来确定启动命令
2. 如果有 vite.config / next.config / nuxt.config，从中推断端口
3. 如果是 Tauri 项目（有 src-tauri），用 tauri 的 dev 命令
4. 如果是 Python 项目，检查 manage.py / pyproject.toml
5. 端口优先从配置文件中读取，找不到就用框架默认端口
6. 只输出 JSON，不要 markdown 代码块，不要解释
"""


def detect_project_config(project_path: str) -> dict:
    """Call Claude Code to analyze the project and detect config."""
    cmd = [
        "claude",
        "-p", DETECT_PROMPT,
        "--cwd", project_path,
        "--allowedTools", "Read,Glob,Grep,Bash",
        "--output-format", "text",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"项目检测失败: {result.stderr[:500]}")

    raw = result.stdout.strip()
    # Try to extract JSON from possible markdown wrapping
    if "```" in raw:
        lines = raw.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        raw = "\n".join(json_lines)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find JSON object in the output
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        raise RuntimeError(f"无法解析检测结果:\n{result.stdout[:500]}")
