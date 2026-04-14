from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class ProjectConfig:
    name: str
    path: str
    description: str = ""


@dataclass
class ServerConfig:
    start_command: str
    health_url: str
    start_cwd: str = "."
    health_timeout: int = 30
    stop_signal: str = "SIGTERM"


@dataclass
class BrowserConfig:
    base_url: str


@dataclass
class LimitsConfig:
    max_review_retries: int = 3
    max_acceptance_retries: int = 2


@dataclass
class AiLoopConfig:
    project: ProjectConfig
    goals: list[str]
    server: ServerConfig
    browser: BrowserConfig
    limits: LimitsConfig = field(default_factory=LimitsConfig)


def _require(data: dict, *keys: str, context: str = "") -> None:
    for key in keys:
        if key not in data or data[key] is None:
            prefix = f"{context}." if context else ""
            raise ValueError(f"Missing required config field: {prefix}{key}")


def load_config(path: Path) -> AiLoopConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    proj = raw.get("project", {})
    _require(proj, "name", "path", context="project")

    srv = raw.get("server", {})
    _require(srv, "start_command", "health_url", context="server")

    brw = raw.get("browser", {})
    _require(brw, "base_url", context="browser")

    lim = raw.get("limits", {})

    return AiLoopConfig(
        project=ProjectConfig(
            name=proj["name"],
            path=proj["path"],
            description=proj.get("description", ""),
        ),
        goals=raw.get("goals", []),
        server=ServerConfig(
            start_command=srv["start_command"],
            health_url=srv["health_url"],
            start_cwd=srv.get("start_cwd", "."),
            health_timeout=srv.get("health_timeout", 30),
            stop_signal=srv.get("stop_signal", "SIGTERM"),
        ),
        browser=BrowserConfig(base_url=brw["base_url"]),
        limits=LimitsConfig(
            max_review_retries=lim.get("max_review_retries", 3),
            max_acceptance_retries=lim.get("max_acceptance_retries", 2),
        ),
    )
