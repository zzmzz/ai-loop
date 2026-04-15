# Changelog

本项目的所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- **流式 JSON 双向通信**：RoleRunner 从 `subprocess stdout` 文本模式重写为 `stream-json` 双向通信模式（`--output-format stream-json --input-format stream-json`），支持实时事件流解析和 `control_request` 自动应答
- **人工协作模式**：新增 `human_decision` 配置项（`low` / `high`），`high` 模式下角色遇到歧义/多方案/架构决策时暂停并通过 `interaction_callback` 向用户提问，收到回答后继续执行
- **Brain 内联上下文**：Brain 决策时直接读取 round_dir 中的产物文件内容内联到 prompt，无需依赖工具调用读取文件
- **角色专属记忆增强**：`round_summary` 决策点输出 `memories` 字段，为 product/developer/reviewer 三个角色生成差异化的记忆摘要
- **记忆压缩增强**：`compact_memories` 支持累积历史摘要——压缩时合并已有摘要与待压缩轮次，生成新的"历史摘要"章节
- **docs/ 文档体系**：按业务域组织的 7 篇技术文档（architecture、orchestration、brain、roles、memory-context、config-reference、development）+ index.md 全局索引

### Changed
- 删除根目录冗余模板文件（`templates/`），代码统一使用 `ai_loop/templates/`
- README 精简为项目概述 + 快速开始，详细文档指向 `docs/`
- CONTRIBUTING.md 精简为指向 `docs/development.md`

### Removed
- 移除 `HUMAN_DECISION_POINTS` 配置项，人工决策改为基于 `human_decision` 等级控制（`low` 全自动 / `high` 关键点暂停）

## [0.1.0] - 2026-04-13

### Added
- 核心编排引擎（Orchestrator）：驱动 需求→设计→实现→审查→验收 完整流程
- Brain 决策大脑：6 个决策点（post_requirement, post_design, post_implementation, post_review, post_acceptance, round_summary）
- 三角色体系：Product（产品经理）、Developer（开发者）、Reviewer（审查者）
- CLI 工具：`ai-loop init` 初始化项目、`ai-loop run` 运行迭代循环
- 项目配置（`config.yaml`）：支持 web / cli / library 三种项目类型
- VerificationConfig：不同项目类型使用不同验收策略
- ContextCollector：阶段间上下文自动注入，减少重复文件读取
- 持久记忆：CLAUDE.md 累积记忆 + 滑动窗口压缩（`memory_window`）
- 角色专属记忆：Brain 为 product / developer / reviewer 生成差异化摘要
- 代码理解缓存：`code-digest.md` 增量阅读机制
- Dev Server 生命周期管理：自动启动、健康检查、优雅停止
- `ai-loop init` 自动检测：通过 Claude Code 分析项目结构
- `--type` 和 `--test-command` 选项支持 CLI/library 项目初始化
- 流式输出：verbose 模式实时显示 Agent 执行过程
- 87 个测试，全通过
