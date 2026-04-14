# ai_loop/orchestrator.py
from pathlib import Path
from ai_loop.config import AiLoopConfig, load_config
from ai_loop.state import LoopState, load_state, save_state
from ai_loop.server import DevServer
from ai_loop.brain import Brain, BrainDecision
from ai_loop.memory import MemoryManager
from ai_loop.roles.base import RoleRunner
from ai_loop.roles.product import ProductRole
from ai_loop.roles.developer import DeveloperRole
from ai_loop.roles.reviewer import ReviewerRole


class Orchestrator:
    def __init__(self, ai_loop_dir: Path):
        self._dir = ai_loop_dir
        self._config = load_config(ai_loop_dir / "config.yaml")
        self._state_file = ai_loop_dir / "state.json"
        self._state = load_state(self._state_file)
        self._memory = MemoryManager()

        project_path = self._config.project.path
        self._server = DevServer(
            start_command=self._config.server.start_command,
            cwd=project_path,
            health_url=self._config.server.health_url,
            health_timeout=self._config.server.health_timeout,
            stop_signal=self._config.server.stop_signal,
            log_path=ai_loop_dir / "server.log",
        )
        self._brain = Brain(
            orchestrator_cwd=str(ai_loop_dir / "workspaces" / "orchestrator")
        )

        self._product = ProductRole(base_url=self._config.browser.base_url)
        self._developer = DeveloperRole()
        self._reviewer = ReviewerRole()

        self._runners = {
            "product": RoleRunner("product", ["Read", "Glob", "Grep", "Bash"]),
            "developer": RoleRunner("developer", ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]),
            "reviewer": RoleRunner("reviewer", ["Read", "Glob", "Grep", "Bash"]),
        }

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
        self._update_all_memories(rnd, round_dir, summary)
        self._state.complete_round(summary)
        save_state(self._state, self._state_file)

        return summary

    def _call_role(self, role_phase: str, rnd: int, round_dir: Path, goals: list[str]) -> None:
        role_name, phase = role_phase.split(":", 1)
        role_map = {
            "product": self._product,
            "developer": self._developer,
            "reviewer": self._reviewer,
        }
        role = role_map[role_name]
        prompt = role.build_prompt(phase, rnd, str(round_dir), goals)
        workspace = str(self._dir / "workspaces" / role_name)
        self._runners[role_name].call(prompt, cwd=workspace)

    def _ask_brain(self, decision_point: str, round_dir: Path) -> BrainDecision:
        return self._brain.decide(decision_point, round_dir=round_dir)

    def _server_start(self) -> None:
        self._server.start()

    def _server_stop(self) -> None:
        self._server.stop()

    def _escalate(self, context: str, reason: str) -> str:
        return f"ESCALATE:{context}:{reason}"

    def _update_all_memories(self, rnd: int, round_dir: Path, summary: str) -> None:
        for role_name in ("orchestrator", "product", "developer", "reviewer"):
            claude_md = self._dir / "workspaces" / role_name / "CLAUDE.md"
            if claude_md.exists():
                self._memory.append_memory(claude_md, rnd, f"- {summary}")
