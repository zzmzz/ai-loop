# AI Loop

**AI 驱动的产品迭代闭环框架** -- 让多个 AI Agent 扮演产品经理、开发者、审查者，自动完成 需求 -> 设计 -> 实现 -> 审查 -> 验收 的完整迭代循环。

## 为什么做这个

用 AI 写代码的人都有这个体验：**你变成了循环里最慢的那个环节**。

AI 几分钟就能写完一个功能，但你得花时间去看它写的对不对、逻辑有没有偏、是不是真的满足了你要的东西。然后反馈修改意见，再看一遍，再反馈... 你本质上变成了一个人肉 CI -- 不断在 "AI 实现" 和 "人工验收" 之间循环。

要么你把验收标准描述得极其精确（这本身就是巨大的工作量），要么你就得一遍遍人工检查。

但仔细想想，"这个实现是否满足了需求" 这件事，AI 也能做。也许现在还做不到 100% 可靠，但它能做到 80%，而且这个能力只会越来越强。**总有一天 AI 能理解业务目标和产物之间的一致性**。

AI Loop 就是基于这个判断的一次实践：把 "人工循环" 变成 "AI 循环"，让多个 AI Agent 各自扮演产品经理、开发者、审查者，自动完成需求->实现->审查->验收的闭环。人类从循环的执行者变成监督者 -- 只在 AI 搞不定的时候介入。

## 核心思路

### 多角色分离，而非万能 Agent

很多人用 AI 的方式是给一个大 prompt 说 "帮我做 XXX"。这种方式在复杂任务上效果不好，因为单一角色容易自说自话，缺乏制衡。

AI Loop 的做法是**角色分离**：

- **Product (产品经理)** -- 关注用户体验和业务价值，通过 Playwright 浏览器实际体验产品，提需求、做验收
- **Developer (开发者)** -- 关注技术实现，严格遵循 TDD，写代码、跑测试
- **Reviewer (审查者)** -- 独立的第二双眼睛，从规范合规、代码质量、安全性、测试覆盖、回归风险五个维度审查

每个角色有独立的**工作空间**（CLAUDE.md 上下文）、独立的**工具权限**（产品经理不能改代码，开发者不能跳过测试），以及独立的**判断标准**。

### Brain：决策大脑

光有角色分离还不够 -- 需要一个独立的"裁判"来判断每个环节的产出是否合格。

Brain 是一个轻量的决策引擎，在 6 个关键决策点被调用：

```
需求完成后 -> Brain 判断是否清晰可执行
设计完成后 -> Brain 判断设计是否合理
实现完成后 -> Brain 判断是否完整
审查完成后 -> Brain 评估问题严重度
验收完成后 -> Brain 确认是否通过
轮次结束后 -> Brain 生成总结
```

Brain 的决策结果驱动流程走向 -- 继续推进、打回重做、还是升级给人类。这避免了"AI 自己写的代码自己说好"的问题。

### 有限重试 + 人类兜底

完全自治的 AI 系统是危险的。AI Loop 设计了两层安全网：

1. **有限重试** -- 审查最多 3 轮，验收最多 2 轮。超过阈值自动升级
2. **ESCALATE 机制** -- 当 Brain 判断问题超出 AI 能力（如产品方向性决策），主动暂停并请求人类介入

这确保了人类始终在循环中。

## 架构

```
                    ┌─────────────────┐
                    │   Orchestrator  │  ← 编排器：驱动整个流程
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌───────────┐    ┌──────────────┐   ┌───────────┐
    │  Product  │    │  Developer   │   │ Reviewer  │
    │  Agent    │    │  Agent       │   │ Agent     │
    │           │    │              │   │           │
    │ Playwright│    │ TDD + Code   │   │ 5维审查    │
    │ 浏览器体验 │    │ 编辑写测试    │   │ 只读分析   │
    └───────────┘    └──────────────┘   └───────────┘
            │                │                │
            └────────────────┼────────────────┘
                             │
                    ┌────────▼────────┐
                    │     Brain       │  ← 决策大脑：每个阶段做判断
                    │  (独立裁判)      │
                    └────────┬────────┘
                             │
                 PROCEED / REFINE / REDO
                 APPROVE / REWORK / ESCALATE
```

### 一轮迭代的完整流程

```
1. 产品探索  ──→  Brain: 需求够清晰吗？
                    ├─ PROCEED → 继续
                    └─ REFINE  → 产品重写需求

2. 技术设计  ──→  Brain: 设计合理吗？
                    ├─ PROCEED → 继续
                    ├─ CLARIFY → 产品回答问题 → 重新设计
                    └─ REDO    → 开发重新设计

3. TDD 实现  ──→  Brain: 实现完整吗？
                    ├─ PROCEED → 继续
                    └─ RETRY   → 开发补完

4. 代码审查  ──→  Brain: 审查结果如何？
   (最多3轮)       ├─ APPROVE    → 继续
                    ├─ SKIP_MINOR → 小问题跳过
                    ├─ REWORK     → 开发修复 → 重新审查
                    └─ ESCALATE   → 人类介入

5. 产品验收  ──→  Brain: 验收通过吗？
   (最多2轮)       ├─ PASS      → 完成!
                    ├─ FAIL_IMPL → 开发修复 → 重新验收
                    ├─ FAIL_REQ  → 需求有问题 → 重新定义 → 重新实现
                    └─ ESCALATE  → 人类介入

6. 轮次总结  ──→  更新所有角色的记忆 → 进入下一轮
```

## 实现原理

### Claude Code 作为 Agent 运行时

AI Loop 没有自己实现 LLM 调用，而是把 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 当作 Agent 运行时。每个角色都是一次 `claude -p` 调用：

```python
# 每个角色就是一次受控的 Claude Code 调用
cmd = [
    "claude",
    "-p", prompt,                              # 角色专属的 prompt
    "--allowedTools", "Read,Glob,Grep,Edit",   # 角色专属的工具权限
    "--output-format", "stream-json",          # 流式输出，实时可见
]
subprocess.Popen(cmd, cwd=workspace)           # 在角色专属的工作空间运行
```

这种设计的好处：
- **工具隔离** -- 产品经理只能读代码 + 跑浏览器，不能改代码；审查者只读不写
- **上下文隔离** -- 每个角色有自己的 CLAUDE.md，带有角色专属的指导原则
- **流式输出** -- verbose 模式下能实时看到每个 Agent 在做什么（调了什么工具、读了什么文件）

### 持久记忆

每个角色的 CLAUDE.md 文件不仅是角色指南，还是**累积记忆**的载体：

```markdown
## 累积记忆

### Round 001
- 添加了暗色模式，使用 CSS 变量实现主题切换

### Round 002
- 优化了移动端布局，修复了导航栏溢出问题
```

每轮结束后，Brain 生成的总结会追加到所有角色的记忆中，确保下一轮开始时每个角色都知道之前发生了什么。

### 开发服务器生命周期

产品经理需要用浏览器体验真实产品，这需要 dev server 在运行。AI Loop 自动管理这个生命周期：

- 在需求探索和验收阶段前自动启动 dev server
- 通过 HTTP 健康检查等待 server 就绪
- 在不需要时优雅停止（SIGTERM -> SIGKILL 兜底）

## 快速开始

### 安装

```bash
pip install -e .

# 如果需要浏览器自动化（产品经理角色需要）
pip install -e ".[browser]"
playwright install chromium
```

前置条件：需要安装 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) 并确保 `claude` 命令可用。

### 初始化项目

```bash
# 自动检测项目配置（通过 Claude Code 分析项目结构）
ai-loop init /path/to/your/project

# 或手动指定
ai-loop init . \
  --name "MyApp" \
  --start-command "npm run dev" \
  --health-url "http://localhost:3000" \
  --base-url "http://localhost:3000" \
  --goal "添加暗色模式支持"
```

初始化后会在项目根目录创建 `.ai-loop/` 目录：

```
.ai-loop/
├── config.yaml              # 项目配置
├── state.json               # 迭代状态
├── rounds/                  # 每轮的产出物
│   └── 001/
│       ├── requirement.md   # 需求文档
│       ├── design.md        # 技术设计
│       ├── dev-log.md       # 开发日志
│       ├── review.md        # 审查报告
│       └── acceptance.md    # 验收结果
└── workspaces/              # 角色工作空间
    ├── orchestrator/CLAUDE.md
    ├── product/CLAUDE.md
    ├── developer/CLAUDE.md
    └── reviewer/CLAUDE.md
```

### 运行迭代

```bash
# 启动迭代循环（默认 verbose 模式，实时显示 Agent 执行过程）
ai-loop run .

# 安静模式
ai-loop run . --quiet

# 运行时追加目标
ai-loop run . --goal "优化首屏加载速度"
```

每轮结束后会提示：
- **c** (继续) -- 进入下一轮迭代
- **g** (加目标) -- 添加新的改进目标
- **s** (停止) -- 结束循环

## 配置

```yaml
# .ai-loop/config.yaml
project:
  name: MyApp
  path: /absolute/path/to/project
  description: 一个 Web 应用

goals:
  - 添加暗色模式
  - 优化移动端体验

server:
  start_command: npm run dev
  start_cwd: .
  health_url: http://localhost:3000
  health_timeout: 30          # 等待 server 就绪的超时秒数
  stop_signal: SIGTERM

browser:
  base_url: http://localhost:3000

limits:
  max_review_retries: 3       # 审查最多重试次数
  max_acceptance_retries: 2   # 验收最多重试次数
```

## 设计哲学

1. **角色制衡优于单点万能** -- 分离的角色会互相挑战，比单个 Agent 自洽的输出更可靠
2. **有限自治优于完全自治** -- 设置重试上限和 ESCALATE 机制，确保人类始终在循环中
3. **证据优于断言** -- 开发者角色被要求贴出命令输出作为证据，禁止使用"应该可以""看起来没问题"等措辞
4. **TDD 作为质量锚点** -- 强制 RED -> GREEN -> REFACTOR 流程，测试是实现的前提而非补充
5. **记忆驱动连续性** -- 通过 CLAUDE.md 累积记忆，让多轮迭代之间保持上下文连贯

## 技术栈

- **Python 3.10+**
- **Claude Code CLI** -- 作为 Agent 运行时
- **Click** -- CLI 框架
- **PyYAML** -- 配置管理
- **Requests** -- 健康检查
- **Playwright** (可选) -- 浏览器自动化

## 作者

**Steven Zhu** ([@zmzhu](https://github.com/zmzhu))

受够了在 "AI 写代码" 和 "人工验收" 之间无限循环，所以写了这个项目，把自己从循环里解放出来。核心赌注是：AI 理解"业务目标和产物是否一致"这件事，已经够用了，而且只会越来越好。

## License

MIT
