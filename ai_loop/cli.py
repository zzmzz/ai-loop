# ai_loop/cli.py
from importlib import resources
from pathlib import Path
import shutil

import click
import yaml

from ai_loop.config import HUMAN_DECISION_LEVELS
from ai_loop.detect import detect_project_config
from ai_loop.orchestrator import Orchestrator
from ai_loop.state import LoopState, save_state
import ai_loop.templates


def _interaction_callback(question_text: str) -> str:
    """展示角色的提问并收集用户回答。"""
    click.echo(f"\n{'─' * 40}")
    click.echo(f"  🤚 需要你的输入")
    click.echo(f"{'─' * 40}")
    click.echo(question_text)
    click.echo()
    return click.prompt("你的回答")


@click.group()
def main():
    """AI Loop: AI-driven product iteration framework."""
    pass


@main.command()
@click.argument("project_path", type=click.Path(), default=".")
@click.option("--name", default=None, help="Project name (auto-detected if omitted)")
@click.option("--type", "project_type", type=click.Choice(["web", "cli", "library"]),
              default="web", help="Project type (determines verification strategy)")
@click.option("--start-command", default=None, help="Dev server start command")
@click.option("--health-url", default=None, help="Health check URL")
@click.option("--base-url", default=None, help="Browser base URL")
@click.option("--test-command", default=None, help="Test command for CLI/library projects")
@click.option("--run-example", multiple=True, help="CLI run examples (repeatable)")
@click.option("--goal", multiple=True, help="Initial goals (repeatable)")
@click.option("--description", default=None, help="Project description")
@click.option("--no-detect", is_flag=True, help="Skip auto-detection, prompt manually")
def init(project_path, name, project_type, start_command, health_url, base_url, test_command, run_example, goal, description, no_detect):
    """Initialize AI Loop for a target project."""
    project = Path(project_path).resolve()

    if not project.exists():
        try:
            project.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise click.ClickException(f"目录创建失败: {project}: {e}")

    ai_dir = project / ".ai-loop"

    if ai_dir.exists():
        raise click.ClickException(f".ai-loop 目录已存在: {ai_dir}")

    # Auto-detect missing config via Claude Code
    detected = {}
    if not no_detect:
        if project_type == "web":
            needs_detect = any(
                v is None for v in [name, start_command, health_url, base_url]
            )
        else:
            needs_detect = any(v is None for v in [name, test_command])
        if needs_detect:
            click.echo("正在分析项目，自动检测配置...")
            try:
                detected = detect_project_config(str(project))
                click.echo("检测完成。")
            except Exception as e:
                click.echo(f"自动检测失败: {e}")
                click.echo("将使用手动输入。")

    # Use detected values as defaults, let user confirm/override
    name = name or detected.get("name") or click.prompt("项目名称")
    description = description if description is not None else detected.get("description", "")

    if project_type == "web":
        start_command = start_command or detected.get("start_command") or click.prompt("Dev server 启动命令")
        health_url = health_url or detected.get("health_url") or click.prompt("健康检查 URL")
        base_url = base_url or detected.get("base_url") or health_url
    else:
        # CLI or library project
        test_command = test_command or detected.get("test_command") or click.prompt("测试命令")
        if not run_example:
            detected_examples = detected.get("run_examples", [])
            run_example = tuple(detected_examples) if detected_examples else ()

    if not goal:
        detected_goals = detected.get("goals", [])
        goal = tuple(detected_goals) if detected_goals else ()

    # Show detected config for confirmation
    if detected:
        click.echo(f"\n  项目名称:    {name}")
        click.echo(f"  描述:        {description}")
        if project_type == "web":
            click.echo(f"  启动命令:    {start_command}")
            click.echo(f"  健康检查:    {health_url}")
            click.echo(f"  浏览器 URL:  {base_url}")
        else:
            click.echo(f"  测试命令:    {test_command}")
        if goal:
            click.echo(f"  目标:        {', '.join(goal)}")
        click.echo()
        if not click.confirm("以上配置是否正确？", default=True):
            name = click.prompt("项目名称", default=name)
            description = click.prompt("描述", default=description)
            if project_type == "web":
                start_command = click.prompt("启动命令", default=start_command)
                health_url = click.prompt("健康检查 URL", default=health_url)
                base_url = click.prompt("浏览器 URL", default=base_url)
            else:
                test_command = click.prompt("测试命令", default=test_command)

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
        try:
            ref = resources.files(ai_loop.templates).joinpath(template_name)
            (ws / "CLAUDE.md").write_text(ref.read_text(encoding="utf-8"))
        except (FileNotFoundError, TypeError):
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
        "limits": {"max_review_retries": 3, "max_acceptance_retries": 2},
    }

    if project_type == "web":
        config["server"] = {
            "start_command": start_command,
            "start_cwd": ".",
            "health_url": health_url,
            "health_timeout": 30,
            "stop_signal": "SIGTERM",
        }
        config["browser"] = {"base_url": base_url}
        config["verification"] = {
            "type": "web",
            "base_url": base_url,
        }
    else:
        # CLI or library project
        config["verification"] = {
            "type": project_type,
            "test_command": test_command,
            "run_examples": list(run_example),
        }
    (ai_dir / "config.yaml").write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False)
    )

    # Write initial state
    save_state(LoopState(), ai_dir / "state.json")

    click.echo(f"AI Loop 初始化完成: {ai_dir}")


@main.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
@click.option("--goal", multiple=True, help="Additional goals for this run")
@click.option("-v", "--verbose", is_flag=True, default=True, help="Show Claude Code processing details (default: on)")
@click.option("-q", "--quiet", is_flag=True, help="Hide Claude Code processing details")
@click.option("--human-decision", type=click.Choice(list(HUMAN_DECISION_LEVELS)),
              default=None, help="Human decision level: low (auto) / high (pause at key points)")
def run(project_path, goal, verbose, quiet, human_decision):
    """Run the AI Loop iteration cycle."""
    project = Path(project_path).resolve()
    ai_dir = project / ".ai-loop"

    if not ai_dir.exists():
        raise click.ClickException(
            f"未找到 .ai-loop 目录，请先运行: ai-loop init {project_path}"
        )

    show_details = verbose and not quiet

    callback = _interaction_callback
    orch = Orchestrator(ai_dir, verbose=show_details, interaction_callback=callback)

    # CLI 参数覆盖配置（仅运行时，不持久化）
    if human_decision:
        orch._config.human_decision = human_decision

    # Inject additional goals into runtime only (not persisted to config)
    for g in goal:
        orch.add_goal(g)

    while True:
        round_num = orch.current_round
        click.echo(f"\n{'=' * 50}")
        click.echo(f"  AI Loop - Round {round_num} 开始")
        click.echo(f"{'=' * 50}\n")

        try:
            summary = orch.run_single_round()
        except Exception as e:
            click.echo(f"\n{'=' * 50}")
            click.echo(f"  AI Loop - Round {round_num} 出错")
            click.echo(f"{'=' * 50}")
            click.echo(f"  错误: {e}")
            click.echo(f"{'=' * 50}\n")

            action = click.prompt(
                "请选择: [r]重试本轮 / [g]添加目标后重试 / [s]停止",
                type=click.Choice(["r", "g", "s"], case_sensitive=False),
                default="r",
                show_choices=True,
            )
            if action == "s":
                click.echo("循环已停止。")
                break
            elif action == "g":
                new_goal = click.prompt("输入新目标")
                orch.add_goal(new_goal)
                click.echo(f"已添加目标: {new_goal}")
            # r or g: continue to next iteration (retry)
            continue

        click.echo(f"\n{'=' * 50}")
        click.echo(f"  AI Loop - Round {round_num} 完成")
        click.echo(f"{'=' * 50}")
        click.echo(f"  结果: {summary}")
        click.echo(f"  产出物: {ai_dir / 'rounds'}")
        click.echo(f"{'=' * 50}\n")

        if summary.startswith("ESCALATE:"):
            _, context, reason = summary.split(":", 2)
            click.echo(f"  ⚠ 需要人类决策 [{context}]: {reason}\n")
            action = click.prompt(
                "请选择",
                type=click.Choice(["c", "g", "s"], case_sensitive=False),
                default="s",
                show_choices=True,
            )
        else:
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
            orch.add_goal(new_goal)
            click.echo(f"已添加目标: {new_goal}")


if __name__ == "__main__":
    main()
