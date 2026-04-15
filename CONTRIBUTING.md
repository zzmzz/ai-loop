# 贡献指南

感谢你对 AI Loop 的兴趣！以下是参与开发所需的信息。

## 开发环境搭建

### 前置条件

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)（确保 `claude` 命令可用）

### 安装

```bash
git clone https://github.com/zmzhu/ai-loop.git
cd ai-loop

# 安装项目及开发依赖
pip install -e ".[dev]"

# 如果需要浏览器自动化（产品经理角色需要）
pip install -e ".[browser]"
playwright install chromium
```

## 运行测试

```bash
python -m pytest tests/ -v
```

所有 PR 提交前需确保测试全部通过。

## 项目结构

```
ai_loop/                 # 主包
├── brain.py             # Brain 决策引擎
├── cli.py               # Click CLI（init / run 命令）
├── config.py            # 配置加载与校验
├── context.py           # ContextCollector 阶段间上下文注入
├── detect.py            # 项目配置自动检测
├── memory.py            # 累积记忆管理（滑动窗口 + 摘要压缩）
├── orchestrator.py      # 编排器，驱动完整迭代流程
├── server.py            # Dev Server 生命周期管理
├── state.py             # 轮次/阶段/重试状态跟踪
├── roles/               # 角色实现
│   ├── base.py          # RoleRunner 基类
│   ├── product.py       # 产品经理角色
│   ├── developer.py     # 开发者角色
│   └── reviewer.py      # 审查者角色
└── templates/           # 角色 CLAUDE.md 模板

tests/                   # 测试套件
├── conftest.py          # 共享 fixtures
├── test_brain.py
├── test_cli.py
├── test_config.py
├── test_context.py
├── test_integration.py
├── test_memory.py
├── test_orchestrator.py
├── test_roles.py
├── test_server.py
└── test_state.py

.ai-loop/                # AI Loop 运行时目录（init 后生成）
├── config.yaml          # 项目配置
├── state.json           # 迭代状态
├── rounds/              # 每轮的产出物
└── workspaces/          # 角色工作空间
```

## 提交规范

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/) 风格：

- `feat:` 新功能
- `fix:` Bug 修复
- `docs:` 文档变更
- `refactor:` 重构（不影响功能）
- `test:` 测试相关
- `chore:` 构建/工具链/辅助变更

示例：

```
feat: add --type and --test-command options to init command
fix: use Optional[] syntax in server.py for Python 3.9 compat
docs: 添加项目 README
```
