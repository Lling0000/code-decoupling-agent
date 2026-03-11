# Code Decoupling Agent

**给屎山代码做体检的受控诊断系统。**

每个团队都有这么一坨代码 -- import 成环、handler 里直接写 SQL、同一个环境变量散落在十几个文件里、一个 utils 模块被半个项目依赖、全局变量在函数里随手改。所有人都知道该重构，但没人敢动，因为谁也说不清改了这里会炸到哪里。

Code Decoupling Agent 就是给这种屎山做体检的工具。它扫描你的 Python 仓库，画出结构性耦合的全景图，产出经过复核的诊断结果和有边界的整改计划 -- 而且整个过程被严格的门禁体系管住：不过测试不行，不过策略不行，仓库跑不起来也不行。

---

## 核心能力

- **AST 静态分析** -- import 图、调用图、数据库访问信号、环境变量映射、全局状态检测、utils 过度依赖追踪
- **7 条诊断规则** -- 覆盖实际 Python 项目中最常见的耦合模式
- **多 Agent 管线** -- Governor / Scanner / Validator / Planner / Critic 按序执行，确定性工具做底座
- **Finding 复核机制** -- 规则引擎的原始输出不直接当结论；每条 finding 都经过二次确认，打上置信度之后才进入规划
- **硬门禁体系** -- 测试门禁 + 策略门禁 + 运行门禁，三道关卡缺一不可
- **双输出** -- 给 agent 读的结构化 JSON + 给人看的 Markdown 报告
- **零强制依赖** -- 只用 Python 标准库就能跑
- **LLM 可选** -- 不配 LLM 也能完整运行（确定性回退模式）；配了 DashScope / 百炼 API 后可以用大模型做智能复核和规划
- **全面可配** -- 优先级权重、策略规则、模型路由、保护路径、阈值全部外置到配置文件

---

## 系统架构

```
                          目标 Python 仓库
                                |
                                v
                   +------------------------+
                   |       Governor         |   总控编排
                   +------------------------+
                                |
                +---------------+----------------+
                |                                 |
                v                                 v
   +------------------------+       +------------------------+
   |     Tool Runner        |       |      模型路由           |
   |   (确定性扫描工具链)    |       |  (配置/环境变量/回退)   |
   +------------------------+       +------------------------+
                |
   +------+------+------+------+------+------+------+
   |      |      |      |      |      |      |      |
   v      v      v      v      v      v      v      v
import  定义   调用   环境    DB   utils  全局   规则
  图    扫描   扫描  变量   信号   依赖  状态   引擎
                |
                v
   +------------------------+
   |   Validator Agent      |   逐条确认/驳回 finding
   +------------------------+
                |
                v
   +------------------------+
   |   模块画像 Agent        |   模块级分析与优先级排序
   +------------------------+
                |
                v
   +------------------------+
   |    Planner Agent       |   生成 triage + 整改计划
   +------------------------+
                |
                v
   +------------------------+
   |    Critic Agent        |   审查计划风险与范围
   +------------------------+
                |
                v
   +------------------------+
   |      策略引擎           |   硬约束执行
   +------------------------+
                |
         +------+------+
         |              |
         v              v
   summary.md    artifacts/*.json
    (给人看)       (给 agent 看)
```

---

## 快速开始

### 安装

```bash
git clone https://github.com/study8677/code-decoupling-agent.git
cd code-decoupling-agent
python -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

运行时依赖**只有 Python 标准库**。`requirements.txt` 是给开发工具链用的。

### 跑一次诊断

```bash
python main.py --repo /path/to/your/python/repo --output ./output
```

### 带门禁的完整运行

```bash
python main.py \
  --repo /path/to/your/python/repo \
  --output ./output \
  --run-gates \
  --target-test-command "pytest" \
  --runtime-command "python app.py"
```

### 检查 LLM 配置

```bash
python main.py --check-llm-config
python main.py --check-llm-config --output ./output   # 同时写出健康检查产物
```

---

## 产出物

一次完整运行产出以下文件：

### 扫描产物

| 文件 | 内容 |
|------|------|
| `artifacts/import_graph.json` | 本地 import 边和模块依赖图 |
| `artifacts/definitions.json` | 类、函数、方法定义及行数 |
| `artifacts/call_graph.json` | 近似调用边 |
| `artifacts/env_usage.json` | 各文件的环境变量读取 |
| `artifacts/db_usage.json` | 数据库/ORM 访问信号及置信度 |
| `artifacts/utils_usage.json` | 共享工具模块依赖统计 |
| `artifacts/global_state.json` | 可变全局状态候选及变更证据 |
| `artifacts/findings.json` | 规则引擎的原始 finding |

### Agent 管线产物

| 文件 | 内容 |
|------|------|
| `artifacts/validated_findings.json` | 经 Validator 复核后的 finding（含置信度和确认状态） |
| `artifacts/repo_inventory.json` | 面向热点的仓库画像 |
| `artifacts/module_inventory.json` | 逐模块的结构画像 |
| `artifacts/module_priorities.json` | 按优先级排序的模块分组 |
| `artifacts/triage.json` | 按优先级归类的待处理 finding |
| `artifacts/action_plan.json` | 有边界、文件级粒度的整改步骤 |
| `artifacts/critic_review.json` | 对整改计划的风险评估 |
| `artifacts/planner_agent.json` | Planner Agent 执行元信息 |
| `artifacts/critic_agent.json` | Critic Agent 执行元信息 |
| `artifacts/model_routing.json` | 各 agent 角色实际使用的模型 |

### 报告

| 文件 | 内容 |
|------|------|
| `summary.md` | 人类可读的诊断报告 |
| `module_reports/lightweight/*.md` | 模块速览卡片 |
| `module_reports/heavyweight/*.md` | 模块深度分析 |
| `iteration_human_report.md` | 门禁结果人类报告（需 `--run-gates`） |
| `artifacts/iteration_agent_report.json` | 门禁结果结构化报告（需 `--run-gates`） |

---

## 多 Agent 管线

系统按严格顺序运行 6 个 agent。每个 agent 有明确的输入契约、输出契约和失败处理。

### 1. Governor（总控）

编排整条管线。先调 Tool Runner 做确定性扫描，再按序串联各 agent。Governor 本身不做任何判断，只负责传数据。

### 2. Tool Runner（确定性工具链）

执行全部 7 个扫描器和规则引擎。这是整个系统的事实底座 -- 不走 LLM，不做启发式猜测，纯 AST 解析。

### 3. Scanner Agent（仓库画像）

把原始扫描产物转化为面向热点的仓库画像。根据可配置的优先级权重（DB 信号数、全局状态风险、上游扇入度、无测试惩罚等）识别最高风险模块。

### 4. Validator Agent（Finding 复核）

逐条审查规则引擎的原始 finding。给每条 finding 打上 `confirmation_status`（confirmed / needs_review / rejected）和 `confidence` 等级。没有 LLM 时用确定性回退逻辑；配了 LLM 后用大模型做智能复核。

### 5. Planner Agent（规划）

接收可操作的 finding（confirmed + needs_review），产出：
- **triage** -- 按优先级分组的 finding
- **action plan** -- 有边界的整改计划，每步都限定文件范围、有成功标准、有回退条件

计划永远不会被自动执行。它是一份供人审查的提案。

### 6. Critic Agent（审查）

审查整改计划的：
- 范围是否过大（单步涉及太多文件）
- 是否触及受保护路径（auth、migration、security）
- 风险等级
- 是否需要先补测试

---

## 门禁体系

门禁体系执行一条硬规则：

> 只有「通过测试 + 通过策略 + 仓库可运行」的改动，才允许进入下一轮。否则它不是解耦系统，而是自动破坏系统。

### 测试门禁（Test Gate）

- 本系统自身测试（`python -m unittest`）
- 金标回归测试（固定输入的预期输出比对）
- 目标仓库回归测试（用户提供的测试命令）

### 策略门禁（Policy Gate）

- 受保护路径检查（auth、migration、security、credential 等）
- 步骤范围检查（单步最大文件数限制）
- 禁止自动执行检查

### 运行门禁（Runtime Gate）

- 目标仓库入口 smoke run
- 核心命令可执行验证
- 产物完整性检查

每道门禁产出三种决定之一：

| 决定 | 含义 |
|------|------|
| `allow_next_iteration` | 三道门禁全过，可以进入下一轮 |
| `hold_for_review` | 测试过了但存在中高风险项，暂停等人看 |
| `blocked` | 至少一道门禁失败，必须停下来 |

---

## 配置

### 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | DashScope / 百炼 API Key | （无） |
| `DASHSCOPE_BASE_URL` | API 接入地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DASHSCOPE_MODEL` | 默认模型（摘要、轻量任务） | `qwen3.5-flash` |
| `PLANNER_MODEL` | Planner / Critic / Validator / Governor 使用的模型 | `deepseek-v3.2` |
| `CODER_MODEL` | 重构/代码类任务使用的模型 | `qwen3-coder-flash` |
| `ENABLE_LIVE_AGENTS` | 设为 `1` 启用 LLM agent；设为 `0` 只走确定性逻辑 | `0` |

历史兼容：`BAILIAN_BASE_URL` 和 `BAILIAN_MODEL` 仍可用作别名。

### 配置文件

| 文件 | 用途 |
|------|------|
| `config/agent_models.json` | 模型路由：每个 agent 角色用哪个模型 |
| `config/policy_config.json` | 受保护路径、单步最大文件数、计划窗口大小 |
| `config/priority_weights.json` | 模块优先级排序的评分权重 |
| `config/gate_spec.json` | 门禁定义、检查项、通过条件 |
| `config/module_registry.json` | 模块元数据注册表 |

模型解析优先级：内置回退值 < 配置文件 < 环境变量。

---

## 诊断规则

规则引擎基于扫描产物运行 7 条规则：

| 规则 ID | 名称 | 检测什么 | 严重度 |
|---------|------|----------|--------|
| **RULE_A** | Handler 直接访问数据库 | handler/controller/router 文件里直接出现 DB/ORM 操作 | high/medium |
| **RULE_B** | 环境变量散读 | 同一个环境变量在多个业务文件中被直接 `os.getenv` | high/medium |
| **RULE_C** | Utils 过度依赖 | 共享 utils/common/helper 模块被 5+ 文件依赖，且跨 3+ 个包 | high/medium |
| **RULE_D** | 可变全局状态 | 模块级可变对象在函数作用域里被 append/update/pop 等方式修改 | high/medium |
| **RULE_E** | Import 循环 | import 图中存在强连通组件（Tarjan 算法检测） | high/medium |
| **RULE_F** | 文件/类过大 | 文件超过 500 行，或单个类包含 15+ 个方法 | medium |
| **RULE_G** | 跨层 DB 访问 | 非 handler、非数据访问层的文件直接包含多个高置信度 DB 操作 | medium |

每条 finding 包含：涉及文件列表、证据行、中文解释、具体整改建议。

---

## 设计哲学

**Agent 负责想，确定性工具负责干。**

这是整个系统最重要的边界：

| 职责 | 谁来做 |
|------|--------|
| 扫描、规则判断、策略门禁、测试执行、最终放行 | 确定性模块 |
| 理解、复核、分诊、规划、审查、解释 | Agent 模块 |

以下事情 agent **绝对不能**自己决定：

- 是否跳过测试
- 是否跳过策略检查
- 是否改受保护文件
- 仓库跑不起来时是否继续推进
- 是否把失败的改动带进下一轮

这条边界存在的原因很简单：诊断和规划需要智能，但验证和执行必须是机械的、不可商量的。如果 agent 能决定"这次测试可以不跑"，那整个系统的安全底线就没了。

---

## 已知限制

- 分析基于 AST，是近似的；动态 import、运行时间接调用、元编程都无法精确解析
- 数据库访问检测基于信号匹配（已知 ORM/驱动的名称模式）；非常规的数据访问方式会被漏掉
- 调用图是近似的 -- 通过变量或装饰器的间接调用可能捕获不到
- 只分析 `.py` 文件；模板、配置文件、SQL 文件、其他语言不在扫描范围内
- Refactor Agent 目前只做规划，不自动改代码，不生成 patch
- Import 循环检测用的是静态 import 图上的 Tarjan SCC 算法；运行时条件 import 不一定能反映出来
- LLM agent 需要 DashScope / 百炼兼容 API；暂不支持其他 provider

---

## 路线图

- 更强的仓库理解能力（跨文件数据流、装饰器解析）
- 受控的 patch plan 生成，支持 diff 预览
- 目标仓库测试执行集成
- 失败迭代的回滚策略
- 逐轮迭代状态持久化（跨会话的 stop/resume）
- 更完善的模块级 contract 和测试基础设施
- 支持 DashScope 之外的 LLM provider
- 多语言仓库支持（从 TypeScript/JavaScript 开始）

---

## 项目结构

```
code-decoupling-agent/
  main.py                  # CLI 入口
  agents/
    governor.py            # 管线总控
    tool_runner.py         # 确定性扫描执行器
    scanner_agent.py       # 仓库画像构建
    validator_agent.py     # Finding 复核
    planner_agent.py       # Triage 和整改计划生成
    critic_agent.py        # 计划风险审查
    module_report_agent.py # 模块画像与卡片生成
    contracts.py           # Agent 契约定义
  scanner/
    imports.py             # Import 图扫描
    definitions.py         # 类/函数/方法扫描
    calls.py               # 调用图扫描
    envs.py                # 环境变量使用扫描
    db_usage.py            # 数据库/ORM 信号扫描
    utils_usage.py         # 共享工具依赖扫描
    globals.py             # 全局状态风险扫描
  rules_engine/
    engine.py              # 规则执行（RULE_A 到 RULE_G）
  rules/
    config.py              # 规则阈值和关键词列表
  policy/
    engine.py              # 受保护路径和范围约束
  iteration/
    gate_runner.py         # 测试/策略/运行门禁执行
  llm/
    client.py              # DashScope / 百炼 API 客户端
    catalog.py             # 模型路由解析
    env.py                 # Provider 环境变量处理
    health.py              # LLM 健康检查探针
  config/
    agent_models.json      # 各 agent 角色的模型分配
    policy_config.json     # 策略规则和阈值
    priority_weights.json  # 模块优先级评分权重
    gate_spec.json         # 门禁定义
    module_registry.json   # 模块元数据
  report/
    renderer.py            # Markdown 报告生成
  models/
    schema.py              # 数据模型（Finding、RepoContext 等）
  common/
    helpers.py             # 内部共享工具
    log.py                 # 日志配置
  tests/
    test_smoke.py          # 基础冒烟测试
    test_design_specs.py   # 设计约束测试
    test_goldens.py        # 金标回归测试
    test_reporting.py      # 报告输出测试
    test_module_reports.py # 模块报告测试
    test_gate_runner.py    # 门禁执行器测试
    test_validator_agent.py # Validator Agent 测试
    test_improvements.py   # 改进验证测试
    fixtures/              # 测试用固定仓库
```

---

## 设计文档

| 文档 | 内容 |
|------|------|
| `ARCHITECTURE.md` | 系统总架构、分层定义、硬约束 |
| `MODULE_SPEC.md` | 模块契约、测试、报告规范 |
| `ITERATION_LOOP.md` | 迭代门禁、停止/继续条件、受控循环设计 |
| `MULTI_AGENT.md` | 多 Agent 角色、模型路由、阶段边界 |
| `AGENTS.md` | 项目定位、范围、明确非目标 |

---

## 许可证

见仓库内许可证文件。
