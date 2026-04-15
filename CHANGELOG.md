# Changelog

本项目的所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Changed
- 删除根目录冗余模板文件（`templates/`），代码统一使用 `ai_loop/templates/`
- 更新 README：新增 CLI/library 项目类型文档、完整配置参考、Round 001 功能介绍
- 新增 CONTRIBUTING.md 和 CHANGELOG.md

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
