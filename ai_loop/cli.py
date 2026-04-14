# ai_loop/cli.py
from pathlib import Path
import shutil

import click
import yaml

from ai_loop.orchestrator import Orchestrator
from ai_loop.state import LoopState, save_state

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@click.group()
def main():
    """AI Loop: AI-driven product iteration framework."""
    pass


@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--name", prompt="项目名称", help="Project name")
@click.option("--start-command", prompt="Dev server 启动命令", help="e.g. npm start")
@click.option("--health-url", prompt="健康检查 URL", help="e.g. http://localhost:3000")
@click.option("--base-url", prompt="浏览器访问 URL", help="e.g. http://localhost:3000")
@click.option("--goal", multiple=True, help="Initial goals (repeatable)")
@click.option("--description", default="", help="Project description")
def init(project_path, name, start_command, health_url, base_url, goal, description):
    """Initialize AI Loop for a target project."""
    project = Path(project_path).resolve()
    ai_dir = project / ".ai-loop"

    if ai_dir.exists():
        raise click.ClickException(f".ai-loop 目录已存在: {ai_dir}")

    # Create directory structure
    ai_dir.mkdir()
    (ai_dir / "rounds").mkdir()

    workspaces = ai_dir / "workspaces"
    role_template_map = {
        "orchestrator": "orchestrator_claude.md",
        "product": "product_claude.md",
        "developer": "developer_claude.md",
        "reviewer": "reviewer_claude.md",
    }

    for role_name, template_name in role_template_map.items():
        ws = workspaces / role_name
        ws.mkdir(parents=True)
        template = TEMPLATES_DIR / template_name
        if template.exists():
            shutil.copy(template, ws / "CLAUDE.md")
        else:
            (ws / "CLAUDE.md").write_text(f"# Role: {role_name}\n\n## 累积记忆\n")
        if role_name != "orchestrator":
            (ws / "notes").mkdir()

    # Write config
    config = {
        "project": {
            "name": name,
            "path": str(project),
            "description": description,
        },
        "goals": list(goal) if goal else [],
        "server": {
            "start_command": start_command,
            "start_cwd": ".",
            "health_url": health_url,
            "health_timeout": 30,
            "stop_signal": "SIGTERM",
        },
        "browser": {"base_url": base_url},
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }
    (ai_dir / "config.yaml").write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False)
    )

    # Write initial state
    save_state(LoopState(), ai_dir / "state.json")

    click.echo(f"AI Loop 初始化完成: {ai_dir}")


@main.command()
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--goal", multiple=True, help="Additional goals for this run")
def run(project_path, goal):
    """Run the AI Loop iteration cycle."""
    project = Path(project_path).resolve()
    ai_dir = project / ".ai-loop"

    if not ai_dir.exists():
        raise click.ClickException(
            f"未找到 .ai-loop 目录，请先运行: ai-loop init {project_path}"
        )

    # Inject additional goals
    if goal:
        config_path = ai_dir / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        config["goals"].extend(goal)
        config_path.write_text(
            yaml.dump(config, allow_unicode=True, default_flow_style=False)
        )

    orch = Orchestrator(ai_dir)

    while True:
        click.echo(f"\n{'=' * 50}")
        click.echo(f"  AI Loop - Round {orch._state.current_round} 开始")
        click.echo(f"{'=' * 50}\n")

        summary = orch.run_single_round()

        click.echo(f"\n{'=' * 50}")
        click.echo(f"  AI Loop - Round {orch._state.current_round - 1} 完成")
        click.echo(f"{'=' * 50}")
        click.echo(f"  结果: {summary}")
        click.echo(f"  产出物: {ai_dir / 'rounds'}")
        click.echo(f"{'=' * 50}\n")

        action = click.prompt(
            "请选择",
            type=click.Choice(["c", "g", "s"], case_sensitive=False),
            default="c",
            show_choices=True,
        )

        if action == "s":
            click.echo("循环已停止。")
            break
        elif action == "g":
            new_goal = click.prompt("输入新目标")
            config_path = ai_dir / "config.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)
            config["goals"].append(new_goal)
            config_path.write_text(
                yaml.dump(config, allow_unicode=True, default_flow_style=False)
            )
            orch._config.goals.append(new_goal)
            click.echo(f"已添加目标: {new_goal}")
        # action == "c" -> continue naturally


if __name__ == "__main__":
    main()
