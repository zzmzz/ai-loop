# ai_loop/orchestrator.py
from importlib import resources
from pathlib import Path
import re
import subprocess
from typing import Callable, Optional
from ai_loop import __version__
from ai_loop.config import AiLoopConfig, load_config
from ai_loop.state import LoopState, load_state, save_state
from ai_loop.server import DevServer
from ai_loop.brain import Brain, BrainDecision
from ai_loop.memory import MemoryManager, MEMORY_SECTION_HEADER
from ai_loop.logger import EventLogger
from ai_loop.roles.base import RoleRunner
from ai_loop.roles.product import ProductRole
from ai_loop.roles.developer import DeveloperRole
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

        self._logger = EventLogger(
            log_dir=ai_loop_dir / "logs",
            round_num=self._state.current_round,
        )
        self._last_phase = "init"

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

        self._product = ProductRole(
            verification=self._config.verification,
            knowledge_dir=ai_loop_dir / "product-knowledge",
        )
        self._developer = DeveloperRole()

        self._runners = {
            "product": RoleRunner("product", ["Read", "Glob", "Grep", "Bash", "Write"]),
            "developer": RoleRunner("developer", ["Read", "Glob", "Grep", "Edit", "Write", "Bash", "Skill", "Agent"]),
        }

    def _ensure_workspaces(self) -> None:
        """Ensure all workspace directories and template files exist.

        When the ai-loop package version has changed since the last run,
        refresh the template portion of each role's CLAUDE.md while
        preserving accumulated memories below the ``## 累积记忆`` marker.
        """
        version_changed = self._state.ai_loop_version != __version__
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
                    claude_md.write_text(f"# Role: {role_name}\n\n{MEMORY_SECTION_HEADER}\n")
            elif version_changed:
                try:
                    ref = resources.files(ai_loop.templates).joinpath(template_name)
                    new_template = ref.read_text(encoding="utf-8")
                    MemoryManager.refresh_template(claude_md, new_template)
                except (FileNotFoundError, TypeError):
                    pass
            if role_name != "orchestrator":
                (ws / "notes").mkdir(exist_ok=True)
        (self._dir / "rounds").mkdir(exist_ok=True)
        (self._dir / "product-knowledge").mkdir(exist_ok=True)

        if version_changed:
            self._state.ai_loop_version = __version__
            save_state(self._state, self._dir / "state.json")

    @property
    def current_round(self) -> int:
        return self._state.current_round

    def add_goal(self, goal: str) -> None:
        self._config.goals.append(goal)

    # Ordered phases for resume logic.  The value is the stage label used
    # to jump into the middle of ``run_single_round``.
    _PHASES = [
        "product_explore",
        "developer_develop",
        "qa_acceptance",
        "round_summary",
    ]

    def _save_phase(self, phase: str) -> None:
        """Persist the current phase so we can resume after a crash."""
        self._state.phase = phase
        save_state(self._state, self._state_file)

    def run_single_round(self) -> str:
        rnd = self._state.current_round
        self._logger.set_round(rnd)
        self._last_phase = "start"
        round_dir = self._state.round_dir(self._dir)
        round_dir.mkdir(parents=True, exist_ok=True)
        goals = self._config.goals

        # Determine where to resume from
        resume = self._state.phase
        if resume == "idle" or resume not in self._PHASES:
            resume = self._PHASES[0]  # start from beginning

        resume_idx = self._PHASES.index(resume)

        # ---------- 1. Product explore ----------
        if resume_idx <= self._PHASES.index("product_explore"):
            self._save_phase("product_explore")
            self._server_start()
            self._call_role("product:explore", rnd, round_dir, goals)
            if self._config.human_decision != "low":
                self._confirm_requirements(round_dir)
            decision = self._ask_brain("post_requirement", round_dir=round_dir)
            if decision.decision == "REFINE":
                self._call_role("product:explore", rnd, round_dir, goals)
                if self._config.human_decision != "low":
                    self._confirm_requirements(round_dir)
            self._server_stop()

        # ---------- 2. Developer develop ----------
        if resume_idx <= self._PHASES.index("developer_develop"):
            self._save_phase("developer_develop")
            self._call_role("developer:develop", rnd, round_dir, goals)
            decision = self._ask_brain("post_development", round_dir=round_dir)
            if decision.decision == "RETRY":
                self._call_role("developer:develop", rnd, round_dir, goals)

        # ---------- 3. QA acceptance loop ----------
        if resume_idx <= self._PHASES.index("qa_acceptance"):
            self._save_phase("qa_acceptance")
            self._server_start()
            max_accept = self._config.limits.max_acceptance_retries
            for attempt in range(max_accept + 1):
                self._call_role("product:qa_acceptance", rnd, round_dir, goals)
                decision = self._ask_brain("post_acceptance", round_dir=round_dir)
                if decision.decision in ("PASS", "PARTIAL_OK"):
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

        # ---------- 4. Round summary + memory ----------
        self._save_phase("round_summary")
        summary_decision = self._ask_brain("round_summary", round_dir=round_dir)
        summary = summary_decision.details or summary_decision.reason
        memories = summary_decision.memories
        self._update_all_memories(rnd, round_dir, summary, memories=memories)

        # 5. Generate/update code digest
        self._update_code_digest(round_dir)

        self._state.complete_round(summary)
        save_state(self._state, self._state_file)

        self._logger.log_phase_transition(from_phase=self._last_phase, to_phase="round_complete")
        self._logger.close()

        return summary

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(msg, flush=True)

    def _call_role(self, role_phase: str, rnd: int, round_dir: Path, goals: list[str]) -> None:
        role_name, phase = role_phase.split(":", 1)
        role_map = {
            "product": self._product,
            "developer": self._developer,
        }
        role = role_map[role_name]
        self._log(f"\n\033[1m▶ [{role_name.upper()}] {phase}\033[0m")
        self._logger.log_phase_transition(
            from_phase=self._last_phase,
            to_phase=role_phase,
        )
        self._last_phase = role_phase

        context = self._context_collector.collect(role_phase, round_dir)
        if role_phase == "product:explore":
            digest_path = self._dir / "code-digest.md"
            if digest_path.exists():
                digest = digest_path.read_text()
                context += f"\n\n## code-digest.md\n\n{digest}"
        knowledge_index = self._dir / "product-knowledge" / "index.md"
        if knowledge_index.exists():
            index_content = knowledge_index.read_text()
            context += f"\n\n## product-knowledge/index.md\n\n{index_content}"
        prompt = role.build_prompt(phase, rnd, str(round_dir), goals, context=context)

        if self._config.human_decision == "high":
            prompt += HUMAN_COLLABORATION_INSTRUCTION
            callback = self._interaction_callback
        else:
            callback = None

        self._logger.log_ai_call(role_name, phase, prompt)

        workspace = str(self._dir / "workspaces" / role_name)
        runner = self._runners[role_name]
        result = runner.call(
            prompt, cwd=workspace, verbose=self._verbose,
            interaction_callback=callback,
        )

        stats = runner.last_stats
        self._logger.log_ai_result(
            role=role_name, phase=phase, result=result,
            duration_ms=stats["duration_ms"],
            cost_usd=stats["cost_usd"],
            turns=stats["turns"],
        )

    def _ask_brain(self, decision_point: str, round_dir: Path) -> BrainDecision:
        self._log(f"\n\033[2m🧠 Brain: {decision_point}\033[0m")
        decision = self._brain.decide(decision_point, round_dir=round_dir)
        self._log(f"\033[2m   → {decision.decision}: {decision.reason}\033[0m")
        self._logger.log_brain_decision(
            decision_point=decision_point,
            decision=decision.decision,
            reason=decision.reason,
        )
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

    @staticmethod
    def _extract_requirements(content: str) -> list[dict]:
        """Extract requirement entries from requirement.md content."""
        reqs = []
        seen_titles = set()
        for m in re.finditer(r'##\s+REQ-(\d+)[：:]\s*(.+)', content):
            title = m.group(2).strip()
            if title not in seen_titles:
                seen_titles.add(title)
                reqs.append({"id": f"REQ-{m.group(1)}", "title": title,
                             "priority": "P1"})
        for m in re.finditer(r'(?:^|\n)-?\s*\*\*\[(P\d)\]\s*(.+?)\*\*', content):
            title = m.group(2).strip()
            if title not in seen_titles:
                seen_titles.add(title)
                reqs.append({"id": "", "title": title,
                             "priority": m.group(1)})
        for m in re.finditer(r'\|\s*(P\d)\s*\|\s*REQ-(\d+)', content):
            for req in reqs:
                if req["id"] == f"REQ-{m.group(2)}":
                    req["priority"] = m.group(1)
        return reqs

    @staticmethod
    def _remove_requirements(req_path: Path, content: str,
                             reqs: list[dict], nums_str: str) -> None:
        """Remove requirements by user-specified indices and rewrite the file."""
        try:
            to_remove = {int(n.strip()) for n in nums_str.split(",") if n.strip()}
        except ValueError:
            return
        titles_to_remove = set()
        for idx in to_remove:
            if 1 <= idx <= len(reqs):
                titles_to_remove.add(reqs[idx - 1]["title"])
        if not titles_to_remove:
            return
        lines = content.split("\n")
        result, skip = [], False
        for line in lines:
            if line.startswith("## REQ-") or (line.startswith("## ") and not line.startswith("## 背景")
                                               and not line.startswith("## 优先级")
                                               and not line.startswith("## 技术约束")):
                skip = any(t in line for t in titles_to_remove)
            if not skip:
                result.append(line)
        req_path.write_text("\n".join(result))

    def _confirm_requirements(self, round_dir: Path) -> None:
        """Present requirement draft to human for review before proceeding."""
        req_path = round_dir / "requirement.md"
        if not req_path.exists():
            return

        content = req_path.read_text()
        reqs = self._extract_requirements(content)

        if not reqs:
            return

        if not self._interaction_callback:
            return

        req_list = "\n".join(
            f"  {i}. [{req['priority']}] {req['title']}"
            for i, req in enumerate(reqs, 1)
        )
        response = self._interaction_callback(
            f"📋 产品需求草案待确认（共 {len(reqs)} 条）：\n"
            f"{req_list}\n\n"
            "请选择操作：\n"
            "  [a] 全部接受\n"
            "  [d] 输入要删除的编号（逗号分隔，如 d 2,3）\n"
            "  [e] 打开 requirement.md 手动编辑后继续\n"
            "  [r] 全部拒绝，让产品重新出\n"
            "选择: "
        )
        response = response.strip().lower()
        if response == "r":
            req_path.unlink()
            self._log("  🗑  已清空需求，将重新生成")
        elif response.startswith("d"):
            nums = response.replace("d", "").strip()
            self._remove_requirements(req_path, content, reqs, nums)
            self._log(f"  ✅ 已按指定编号裁剪需求")
        elif response == "e":
            self._log(f"  📝 请编辑 {req_path} 后按回车继续...")
            self._interaction_callback("编辑完成后按回车继续: ")

    def _escalate(self, context: str, reason: str) -> str:
        self._logger.log_error(context=context, error=f"ESCALATE: {reason}")
        self._logger.close()
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
        for role_name in ("orchestrator", "product", "developer"):
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
