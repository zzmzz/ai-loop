from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
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
class VerificationConfig:
    type: str                        # "web" | "cli" | "library"
    base_url: str = ""               # web only
    test_command: str = ""           # cli/library
    run_examples: list[str] = field(default_factory=list)  # cli


@dataclass
class AiLoopConfig:
    project: ProjectConfig
    goals: list[str]
    verification: VerificationConfig
    server: Optional[ServerConfig] = None
    browser: Optional[BrowserConfig] = None
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

    # Parse server (optional)
    srv_raw = raw.get("server")
    server = None
    if srv_raw:
        _require(srv_raw, "start_command", "health_url", context="server")
        server = ServerConfig(
            start_command=srv_raw["start_command"],
            health_url=srv_raw["health_url"],
            start_cwd=srv_raw.get("start_cwd", "."),
            health_timeout=srv_raw.get("health_timeout", 30),
            stop_signal=srv_raw.get("stop_signal", "SIGTERM"),
        )

    # Parse verification (new) or fallback to browser (backward compat)
    ver_raw = raw.get("verification")
    brw_raw = raw.get("browser")
    browser = None

    if ver_raw:
        verification = VerificationConfig(
            type=ver_raw["type"],
            base_url=ver_raw.get("base_url", ""),
            test_command=ver_raw.get("test_command", ""),
            run_examples=ver_raw.get("run_examples", []),
        )
    elif brw_raw and brw_raw.get("base_url"):
        browser = BrowserConfig(base_url=brw_raw["base_url"])
        verification = VerificationConfig(type="web", base_url=brw_raw["base_url"])
    else:
        raise ValueError("Missing required config: either 'verification' or 'browser.base_url' must be provided")

    lim = raw.get("limits", {})

    return AiLoopConfig(
        project=ProjectConfig(
            name=proj["name"],
            path=proj["path"],
            description=proj.get("description", ""),
        ),
        goals=raw.get("goals", []),
        verification=verification,
        server=server,
        browser=browser,
        limits=LimitsConfig(
            max_review_retries=lim.get("max_review_retries", 3),
            max_acceptance_retries=lim.get("max_acceptance_retries", 2),
        ),
    )
