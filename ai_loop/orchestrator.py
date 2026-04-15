# ai_loop/orchestrator.py
from importlib import resources
from pathlib import Path
import subprocess
from typing import Callable, Optional
from ai_loop.config import AiLoopConfig, load_config
from ai_loop.state import LoopState, load_state, save_state
from ai_loop.server import DevServer
from ai_loop.brain import Brain, BrainDecision
from ai_loop.memory import MemoryManager
from ai_loop.roles.base import RoleRunner
from ai_loop.roles.product import ProductRole
from ai_loop.roles.developer import DeveloperRole
from ai_loop.roles.reviewer import ReviewerRole
from ai_loop.context import ContextCollector
import ai_loop.templates

HUMAN_COLLABORATION_INSTRUCTION = """

## 人工协作模式

你在协作模式下工作。当遇到以下情况时，暂停并向调度者提问：
- 需求存在歧义或多种理解
- 有 2 个以上可行方案且各有取舍
- 涉及影响范围大的架构决策
- 你不确定产品意图或优先级

提问规则：
- 一次只问一个问题
- 优先提供 2-3 个选项 + 你的推荐 + 理由
- 开放式问题也可以，但尽量给出方向性建议
- 信息足够后立即继续执行，不要过度确认

提问时在输出末尾附加标记：
{"needs_input": true}

收到回答后继续工作。不再有疑问时正常完成任务，不附加标记。
"""

_ROLE_TEMPLATE_MAP = {
    "orchestrator": "orchestrator_claude.md",
    "product": "product_claude.md",
    "developer": "developer_claude.md",
    "reviewer": "reviewer_claude.md",
}


class Orchestrator:
    def __init__(self, ai_loop_dir: Path, verbose: bool = False,
                 interaction_callback: Optional[Callable] = None):
        self._dir = ai_loop_dir
        self._config = load_config(ai_loop_dir / "config.yaml")
        self._state_file = ai_loop_dir / "state.json"
        self._state = load_state(self._state_file)
        self._memory = MemoryManager()
        self._verbose = verbose
        self._context_collector = ContextCollector()
        self._interaction_callback = interaction_callback

        self._ensure_workspaces()

        project_path = self._config.project.path

        # Server is optional (CLI/library projects don't need one)
        if self._config.server:
            self._server = DevServer(
                start_command=self._config.server.start_command,
                cwd=project_path,
                health_url=self._config.server.health_url,
                health_timeout=self._config.server.health_timeout,
                stop_signal=self._config.server.stop_signal,
                log_path=ai_loop_dir / "server.log",
            )
        else:
            self._server = None

        self._brain = Brain(
            orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator")
        )

        self._product = ProductRole(verification=self._config.verification)
        self._developer = DeveloperRole()
        self._reviewer = ReviewerRole()

        self._runners = {
            "product": RoleRunner("product", ["Read", "Glob", "Grep", "Bash"]),
            "developer": RoleRunner("developer", ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]),
            "reviewer": RoleRunner("reviewer", ["Read", "Glob", "Grep", "Bash"]),
        }

    def _ensure_workspaces(self) -> None:
        """Ensure all workspace directories and template files exist."""
        workspaces = self._dir / "workspaces"
        for role_name, template_name in _ROLE_TEMPLATE_MAP.items():
            ws = workspaces / role_name
            ws.mkdir(parents=True, exist_ok=True)
            claude_md = ws / "CLAUDE.md"
            if not claude_md.exists():
                try:
                    ref = resources.files(ai_loop.templates).joinpath(template_name)
                    claude_md.write_text(ref.read_text(encoding="utf-8"))
                except (FileNotFoundError, TypeError):
                    claude_md.write_text(f"# Role: {role_name}\n\n## 累积记忆\n")
            if role_name != "orchestrator":
                (ws / "notes").mkdir(exist_ok=True)
        (self._dir / "rounds").mkdir(exist_ok=True)

    @property
    def current_round(self) -> int:
        return self._state.current_round

    def add_goal(self, goal: str) -> None:
        self._config.goals.append(goal)

    def run_single_round(self) -> str:
        rnd = self._state.current_round
        round_dir = self._state.round_dir(self._dir)
        round_dir.mkdir(parents=True, exist_ok=True)
        goals = self._config.goals

        # 1. Product explore
        self._server_start()
        self._call_role("product:explore", rnd, round_dir, goals)
        decision = self._ask_brain("post_requirement", round_dir=round_dir)
        if decision.decision == "REFINE":
            self._call_role("product:explore", rnd, round_dir, goals)
        self._server_stop()

        # 2. Developer design
        self._call_role("developer:design", rnd, round_dir, goals)
        decision = self._ask_brain("post_design", round_dir=round_dir)
        if decision.decision == "CLARIFY":
            self._call_role("product:clarify", rnd, round_dir, goals)
            self._call_role("developer:design", rnd, round_dir, goals)
        elif decision.decision == "REDO":
            self._call_role("developer:design", rnd, round_dir, goals)

        # 3. Developer implement + verify
        self._call_role("developer:implement", rnd, round_dir, goals)
        decision = self._ask_brain("post_implementation", round_dir=round_dir)
        if decision.decision == "RETRY":
            self._call_role("developer:implement", rnd, round_dir, goals)

        # 4. Review loop
        self._server_start()
        max_review = self._config.limits.max_review_retries
        for attempt in range(max_review + 1):
            self._call_role("reviewer:review", rnd, round_dir, goals)
            decision = self._ask_brain("post_review", round_dir=round_dir)
            if decision.decision in ("APPROVE", "SKIP_MINOR"):
                break
            if decision.decision == "ESCALATE":
                return self._escalate("review", decision.reason)
            if attempt < max_review:
                self._call_role("developer:fix_review", rnd, round_dir, goals)
                self._call_role("developer:verify", rnd, round_dir, goals)
        else:
            return self._escalate("review", f"审查 {max_review} 次仍未通过")

        # 5. Acceptance loop
        max_accept = self._config.limits.max_acceptance_retries
        for attempt in range(max_accept + 1):
            self._call_role("product:acceptance", rnd, round_dir, goals)
            decision = self._ask_brain("post_acceptance", round_dir=round_dir)
            if decision.decision == "PASS":
                break
            if decision.decision == "ESCALATE":
                return self._escalate("acceptance", decision.reason)
            if decision.decision == "FAIL_REQ":
                self._server_stop()
                self._call_role("product:explore", rnd, round_dir, goals)
                self._call_role("developer:implement", rnd, round_dir, goals)
                self._server_start()
            elif decision.decision == "FAIL_IMPL":
                self._server_stop()
                self._call_role("developer:implement", rnd, round_dir, goals)
                self._server_start()
        else:
            return self._escalate("acceptance", f"验收 {max_accept} 次仍未通过")

        self._server_stop()

        # 6. Round summary + memory update
        summary_decision = self._ask_brain("round_summary", round_dir=round_dir)
        summary = summary_decision.details or summary_decision.reason
        memories = summary_decision.memories
        self._update_all_memories(rnd, round_dir, summary, memories=memories)

        # 7. Generate/update code digest
        self._update_code_digest(round_dir)

        self._state.complete_round(summary)
        save_state(self._state, self._state_file)

        return summary

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(msg, flush=True)

    def _call_role(self, role_phase: str, rnd: int, round_dir: Path, goals: list[str]) -> None:
        role_name, phase = role_phase.split(":", 1)
        role_map = {
            "product": self._product,
            "developer": self._developer,
            "reviewer": self._reviewer,
        }
        role = role_map[role_name]
        self._log(f"\n\033[1m▶ [{role_name.upper()}] {phase}\033[0m")
        context = self._context_collector.collect(role_phase, round_dir)
        if role_phase == "product:explore":
            digest_path = self._dir / "code-digest.md"
            if digest_path.exists():
                digest = digest_path.read_text()
                context += f"\n\n## code-digest.md\n\n{digest}"
        prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)

        if self._config.human_decision == "high":
            prompt += HUMAN_COLLABORATION_INSTRUCTION
            callback = self._interaction_callback
        else:
            callback = None

        workspace = str(self._dir / "workspaces" / role_name)
        self._runners[role_name].call(
            prompt, cwd=workspace, verbose=self._verbose,
            interaction_callback=callback,
        )

    def _ask_brain(self, decision_point: str, round_dir: Path) -> BrainDecision:
        self._log(f"\n\033[2m🧠 Brain: {decision_point}\033[0m")
        decision = self._brain.decide(decision_point, round_dir=round_dir)
        self._log(f"\033[2m   → {decision.decision}: {decision.reason}\033[0m")
        return decision

    def _server_start(self) -> None:
        if self._server is None:
            return
        self._log("\033[2m🖥  Dev server 启动中...\033[0m")
        try:
            self._server.start()
            self._log("\033[2m🖥  Dev server 已就绪\033[0m")
        except Exception as e:
            self._log(f"\033[33m⚠ Dev server 启动失败: {e}\033[0m")

    def _server_stop(self) -> None:
        if self._server is None:
            return
        try:
            self._server.stop()
            self._log("\033[2m🖥  Dev server 已停止\033[0m")
        except Exception as e:
            self._log(f"\033[33m⚠ Dev server 停止失败: {e}\033[0m")

    def _escalate(self, context: str, reason: str) -> str:
        return f"ESCALATE:{context}:{reason}"

    def _update_code_digest(self, round_dir: Path) -> None:
        digest_path = self._dir / "code-digest.md"
        project_path = self._config.project.path
        try:
            tree_result = subprocess.run(
                ["find", ".", "-type", "f", "-not", "-path", "./.git/*",
                 "-not", "-path", "./.ai-loop/*", "-not", "-path", "./node_modules/*"],
                capture_output=True, text=True, cwd=project_path, timeout=10,
            )
            tree_output = tree_result.stdout[:3000]
        except Exception:
            tree_output = "(unable to get directory tree)"

        try:
            diff_result = subprocess.run(
                ["git", "diff", "HEAD~1", "--stat"],
                capture_output=True, text=True, cwd=project_path, timeout=10,
            )
            diff_output = diff_result.stdout[:3000]
            if diff_result.returncode != 0 or not diff_output.strip():
                # Fallback for first commit (HEAD~1 doesn't exist)
                log_result = subprocess.run(
                    ["git", "log", "-1", "--stat"],
                    capture_output=True, text=True, cwd=project_path, timeout=10,
                )
                diff_output = log_result.stdout[:3000]
        except Exception:
            diff_output = "(unable to get git diff)"

        self._brain.generate_code_digest(
            project_path=project_path,
            digest_path=digest_path,
            tree_output=tree_output,
            diff_output=diff_output,
        )

    def _update_all_memories(self, rnd: int, round_dir: Path, summary: str,
                             memories: dict = None) -> None:
        for role_name in ("orchestrator", "product", "developer", "reviewer"):
            claude_md = self._dir / "workspaces" / role_name / "CLAUDE.md"
            if claude_md.exists():
                if memories and role_name in memories:
                    content = f"- {memories[role_name]}"
                else:
                    content = f"- {summary}"
                self._memory.append_memory(claude_md, rnd, content)
                if self._memory.count_rounds(claude_md) > self._config.limits.memory_window:
                    self._memory.compact_memories(
                        claude_md,
                        window=self._config.limits.memory_window,
                        summarizer=self._brain.summarize_memories,
                    )
