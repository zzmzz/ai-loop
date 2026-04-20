# AI Loop 项目代码摘要

## 项目架构

AI Loop 是一个 AI 驱动的产品迭代框架，通过编排多个 AI 角色（产品经理、开发者、审查者）自动执行"需求→设计→实现→审查→验收"的完整迭代循环。底层通过 Claude CLI 的 stream-json 双向通信协议调用 AI 能力。支持 web、CLI、library 三种项目类型。

## 核心模块

### 编排层
- **orchestrator.py** — 核心编排器，驱动单轮迭代的完整流程：product:explore → developer:design → developer:implement → reviewer:review → product:acceptance。管理 DevServer 生命周期、Brain 决策调用、记忆更新和代码摘要生成。支持 human_decision 协作模式。
- **brain.py** — 决策大脑，在 6 个决策点（post_requirement/post_design/post_implementation/post_review/post_acceptance/round_summary）读取产出物并输出结构化 JSON 决策（PROCEED/REFINE/APPROVE/ESCALATE 等）。同时负责代码摘要生成和记忆压缩。
- **state.py** — 循环状态持久化，跟踪当前轮次、阶段、重试计数和历史记录，JSON 格式存储。

### 角色层
- **roles/base.py** — RoleRunner，封装 Claude CLI 的 stream-json 双向通信，处理 control_request 权限自动放行、needs_input 交互回调、事件渲染。支持按角色限定 allowed_tools。
- **roles/product.py** — 产品经理角色，构建 explore（需求发现）、clarify（答疑）、acceptance（验收）三个阶段的 prompt，区分 web/CLI 两种验证策略。
- **roles/developer.py** — 开发者角色，构建 design（技术设计）、implement（TDD 实现）、verify（验证）、fix_review（审查修复）四个阶段的 prompt。
- **roles/reviewer.py** — 审查者角色，构建 review prompt，按规范合规、代码质量、安全、测试覆盖、回归风险五维度审查。

### 基础设施层
- **config.py** — 配置加载，解析 config.yaml 为 dataclass 结构（ProjectConfig/ServerConfig/VerificationConfig/LimitsConfig），支持 web/CLI/library 三种项目类型。
- **context.py** — ContextCollector，根据阶段依赖关系自动收集前序产出物（requirement.md/design.md/dev-log.md 等）注入到 prompt 中。
- **memory.py** — MemoryManager，管理各角色 CLAUDE.md 中的累积记忆，支持按轮次追加、滑动窗口保留和历史摘要压缩。
- **server.py** — DevServer，管理开发服务器的启动/健康检查/停止生命周期（仅 web 项目使用）。
- **detect.py** — 项目自动检测，调用 Claude CLI 分析项目目录，推断项目名称、启动命令、测试命令等配置。
- **cli.py** — Click CLI 入口，提供 `init`（项目初始化）和 `run`（启动迭代循环）两个命令，支持错误恢复和目标注入。

### 模板层
- **templates/** — 四个角色的 CLAUDE.md 初始模板（orchestrator/product/developer/reviewer），定义角色身份、决策原则和项目上下文占位符。