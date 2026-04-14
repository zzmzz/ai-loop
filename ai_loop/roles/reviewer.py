class ReviewerRole:
    def build_prompt(self, phase: str, round_num: int, round_dir: str,
                     goals: list[str], context: str = "") -> str:
        if phase != "review":
            raise ValueError(f"Unknown reviewer phase: {phase}")
        goals_text = "\n".join(f"- {g}" for g in goals)
        prompt = self._review_prompt(round_num, round_dir, goals_text)
        if context:
            prompt += f"\n\n{context}"
        return prompt

    def _review_prompt(self, round_num, round_dir, goals_text):
        return f"""你是高级工程师，执行代码审查。

阅读以下文件建立上下文：
1. 需求：{round_dir}/requirement.md
2. 设计：{round_dir}/design.md
3. 开发日志：{round_dir}/dev-log.md
4. 运行 git diff 查看代码变更

按以下维度逐一审查：

1. 规范合规：每个需求点是否有对应实现？有没有 scope creep？
2. 代码质量：可读性、命名、结构，是否遵循项目已有模式
3. 安全与健壮性：OWASP Top 10、边界条件、错误处理
4. 测试覆盖：关键路径是否有测试，测试是否有意义
5. 回归风险：运行完整测试套件并贴出结果

每条反馈标记严重级别：
- Critical —— 必须修复
- Important —— 强烈建议修复
- Minor —— 可选改进

输出文件：{round_dir}/review.md

文件头部：
---
round: {round_num}
role: reviewer
phase: review
result: APPROVE 或 REQUEST_CHANGES
timestamp: （当前时间 ISO 格式）
---

result 必须是 APPROVE 或 REQUEST_CHANGES。"""
