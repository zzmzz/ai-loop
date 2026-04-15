# AI Loop

**AI 驱动的产品迭代闭环框架** -- 让多个 AI Agent 扮演产品经理、开发者、审查者，自动完成 需求 -> 设计 -> 实现 -> 审查 -> 验收 的完整迭代循环。

## 为什么做这个

用 AI 写代码的人都有这个体验：**你变成了循环里最慢的那个环节**。

AI 几分钟就能写完一个功能，但你得花时间去看它写的对不对、逻辑有没有偏、是不是真的满足了你要的东西。然后反馈修改意见，再看一遍，再反馈... 你本质上变成了一个人肉 CI -- 不断在 "AI 实现" 和 "人工验收" 之间循环。

AI Loop 把 "人工循环" 变成 "AI 循环"，让多个 AI Agent 各自扮演产品经理、开发者、审查者，自动完成需求->实现->审查->验收的闭环。人类从循环的执行者变成监督者 -- 只在 AI 搞不定的时候介入。

## 核心思路

- **角色分离** -- Product（浏览器体验产品）、Developer（TDD 实现）、Reviewer（5 维审查），工具权限互相隔离
- **Brain 决策** -- 独立裁判在 6 个关键决策点判断产出质量，驱动流程走向
- **有限重试 + ESCALATE** -- 审查最多 3 轮，验收最多 2 轮，超限自动升级给人类
- **人工协作** -- `human_decision: high` 模式下角色遇到歧义时暂停提问，收到回答后继续
- **持久记忆** -- CLAUDE.md 累积记忆 + 滑动窗口压缩，跨轮次保持上下文连贯

## 架构总览

```
                    ┌─────────────────┐
                    │   Orchestrator  │  ← 编排器：驱动整个流程
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌───────────┐    ┌──────────────┐   ┌───────────┐
    │  Product   │    │  Developer   │   │ Reviewer  │
    │  Agent     │    │  Agent       │   │ Agent     │
    └───────────┘    └──────────────┘   └───────────┘
                             │
                    ┌────────▼────────┐
                    │     Brain       │  ← 决策大脑
                    └─────────────────┘
```

一轮迭代：产品探索 → 技术设计 → TDD 实现 → 代码审查（≤3轮） → 产品验收（≤2轮） → 记忆更新

> 详细架构、数据流、各组件交互见 [docs/architecture.md](docs/architecture.md)

## 快速开始

### 安装

```bash
pip install -e .

# 浏览器自动化（web 项目的产品经理角色需要）
pip install -e ".[browser]"
playwright install chromium
```

前置条件：[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 可用。

### 初始化

```bash
# Web 项目（自动检测配置）
ai-loop init /path/to/your/project

# CLI 项目
ai-loop init . --type cli --test-command "python -m pytest"

# Library 项目
ai-loop init . --type library --test-command "python -m pytest"
```

### 运行

```bash
ai-loop run .                              # verbose 模式
ai-loop run . --quiet                      # 安静模式
ai-loop run . --goal "优化首屏加载速度"     # 追加目标
ai-loop run . --human-decision high        # 人工协作模式
```

> 完整配置参考见 [docs/config-reference.md](docs/config-reference.md)

## 文档

详细文档按业务域组织在 `docs/` 目录下：

| 文档 | 说明 |
|------|------|
| **[docs/index.md](docs/index.md)** | **全局索引** |
| [docs/architecture.md](docs/architecture.md) | 系统架构、组件关系、数据流 |
| [docs/orchestration.md](docs/orchestration.md) | 编排引擎完整流程、重试/升级/协作机制 |
| [docs/brain.md](docs/brain.md) | Brain 6 个决策点、JSON schema |
| [docs/roles.md](docs/roles.md) | RoleRunner + 三角色详解 |
| [docs/memory-context.md](docs/memory-context.md) | 累积记忆、滑动窗口压缩、ContextCollector |
| [docs/config-reference.md](docs/config-reference.md) | config.yaml 全字段说明 + CLI 命令参考 |
| [docs/development.md](docs/development.md) | 开发环境、测试规范、模块改动注意事项 |

## 技术栈

- **Python 3.10+** / **Claude Code CLI** / **Click** / **PyYAML** / **Requests** / **Playwright** (可选)

## License

MIT
