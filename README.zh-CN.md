# Code Decoupling Agent

[English](README.md) | [简体中文](README.zh-CN.md)

**在重构变成回归事故之前，先看清 Python 代码库里的耦合热点。**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![AST 静态分析](https://img.shields.io/badge/analysis-AST%20based-2F855A)](#能检测什么)
[![运行时依赖](https://img.shields.io/badge/runtime%20deps-stdlib%20only-0F766E)](#快速开始)
[![LLM 可选](https://img.shields.io/badge/LLM-optional-7C3AED)](#llm-可选)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Code Decoupling Agent 是一个本地 CLI，用来诊断 Python 仓库里的结构性耦合。它基于 AST 扫描代码，给模块做风险排序，复核 finding，并同时产出给人看的 Markdown 和给工具读的 JSON。

它**不会自动改你的代码**。它的职责是告诉你：哪里耦合最危险，证据是什么，为什么值得先处理，以及一个有边界的重构计划应该长什么样。

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py --repo /path/to/python/repo --output ./output
```

典型输出：

```text
Scanned 36 Python files
Generated 5 findings
Validated 5 actionable findings
Profiled 28 modules
Output written to ./output
```

示例报告：[docs/sample-output/requests-summary.md](docs/sample-output/requests-summary.md)

## 为什么需要它

重构真正危险的地方，通常不是“代码难看”，而是耦合看不见：

- handler/controller 里直接访问数据库
- 同一个环境变量散落在多个业务模块里读取
- `utils` 模块变成事实上的跨领域公共 API
- 可变全局状态在函数里被修改
- import 循环让初始化顺序变脆
- 大文件/大类混进太多职责

这个工具把这些直觉变成可复核的证据：

- 给出精确文件和扫描信号，而不是泛泛建议
- 先按产品代码热点排序，降低测试/文档噪音
- finding 有 confirmed / needs_review / rejected 状态
- JSON 方便自动化，Markdown 方便人审查
- 可选测试门禁、策略门禁、运行门禁，适合受控迭代

## 快速开始

### 1. 安装

```bash
git clone https://github.com/Lling0000/code-decoupling-agent.git
cd code-decoupling-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

确定性运行链路只依赖 Python 标准库。`requirements.txt` 主要给开发和测试工具链使用。

### 2. 扫描一个仓库

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py \
  --repo /path/to/your/python/repo \
  --output ./output
```

### 3. 打开人类报告

```bash
open ./output/summary.md
```

### 4. 查看结构化产物

```bash
ls ./output/artifacts
```

```text
findings.json
validated_findings.json
action_plan.json
critic_review.json
import_graph.json
call_graph.json
definitions.json
env_usage.json
db_usage.json
utils_usage.json
global_state.json
```

## 能检测什么

| 规则 | 耦合味道 | 为什么重要 |
|------|----------|------------|
| `RULE_A` | Handler/controller/router 文件直接访问 DB/ORM | 请求层和数据访问层难以分开测试 |
| `RULE_B` | 同一个环境变量在多个业务文件中直接读取 | 配置入口分散，修改和排查成本上升 |
| `RULE_C` | `utils/common/helper` 被大量跨包依赖 | 便利模块变成隐式公共 API |
| `RULE_D` | 模块级可变全局变量在函数内被修改 | 行为依赖调用顺序，副作用难追踪 |
| `RULE_E` | 静态 import 图里出现循环依赖 | 初始化顺序和模块边界变脆 |
| `RULE_F` | 大文件/大类叠加结构性信号 | 多个职责堆在一个位置 |
| `RULE_G` | 非 handler、非数据访问层出现跨层 DB 操作 | 持久化细节泄漏到业务层 |

每条 finding 都包含涉及文件、证据、严重级别、复核状态、置信度、解释和具体整改建议。

## 真实仓库验证

项目已经用 [`psf/requests`](https://github.com/psf/requests) 做过确定性 dogfood。

```bash
git clone --depth 1 https://github.com/psf/requests.git /tmp/requests-dogfood
ENABLE_LIVE_AGENTS=0 python3 main.py \
  --repo /tmp/requests-dogfood \
  --output /tmp/requests-dogfood-output
```

实际观测：

| 指标 | 数值 |
|------|------|
| 扫描 Python 文件数 | `36` |
| 生成 findings 数 | `5` |
| 复核后可行动 findings 数 | `5` |
| 典型热点模块 | `src/requests/utils.py`, `src/requests/models.py`, `src/requests/sessions.py` |

这不是说 `requests` 代码差。它是一个成熟真实仓库，足以证明这个工具不是只会跑玩具 fixture，而是能在真实项目上给出保守、可复核的诊断结果。

## Finding 示例

```text
### 共享 Utils 模块被过度依赖

- 严重级别：中
- 确认状态：已确认
- 置信度：中
- 文件：app/feature_a/consumer.py, app/feature_b/consumer.py, ...
- 证据：app.common.helpers 被 5 个文件依赖，覆盖 5 个包
- 解释：共享 helper 模块正在变成横跨多个领域的隐式依赖。
- 建议：按领域边界拆分 helper，只保留真正通用的能力。
```

## 安全模型

这个项目最重要的边界是：

> Agent 可以解释和规划；事实、门禁、停止条件必须由确定性工具决定。

工具会做：

- 用 AST 扫描本地 Python 文件
- 生成 JSON 产物和 Markdown 报告
- 先复核 raw finding，再把它当成可行动结论
- 产出文件级、有边界的重构计划
- 可选执行测试/运行命令作为门禁

工具不会做：

- 自动编辑源码
- 自动应用 patch
- 跳过已配置测试
- 覆盖受保护路径策略
- 在硬门禁失败后继续推进
- 声称自己能精确理解所有动态运行时行为

## 带门禁运行

当你希望报告里包含测试、策略、运行三类硬检查时：

```bash
python3 main.py \
  --repo /path/to/your/python/repo \
  --output ./output \
  --run-gates \
  --target-test-command "pytest" \
  --runtime-command "python app.py"
```

门禁决定：

| 决定 | 含义 |
|------|------|
| `allow_next_iteration` | 测试、策略、运行检查都通过 |
| `hold_for_review` | 检查通过，但风险需要人工复核 |
| `blocked` | 至少一个硬门禁失败 |

门禁产物：

- `output/iteration_human_report.md`
- `output/artifacts/iteration_agent_report.json`

## LLM 可选

默认走确定性模式：

```bash
ENABLE_LIVE_AGENTS=0 python3 main.py --repo ./my-repo --output ./output
```

也可以启用 DashScope / 百炼兼容 API，让 LLM 参与复核和规划：

```bash
export DASHSCOPE_API_KEY="..."
export ENABLE_LIVE_AGENTS=1
python3 main.py --repo ./my-repo --output ./output
```

检查配置：

```bash
python3 main.py --check-llm-config
python3 main.py --check-llm-config --output ./output
```

相关环境变量：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `ENABLE_LIVE_AGENTS` | `1` 启用 LLM agent，`0` 走确定性回退 | `0` |
| `DASHSCOPE_API_KEY` | DashScope / 百炼兼容 API Key | 无 |
| `DASHSCOPE_BASE_URL` | 兼容 API base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `DASHSCOPE_MODEL` | 轻量任务默认模型 | `qwen3.5-flash` |
| `PLANNER_MODEL` | Planner、Critic、Validator、Governor 模型 | `deepseek-v3.2` |
| `CODER_MODEL` | 代码类模型分配 | `qwen3-coder-flash` |

历史别名 `BAILIAN_BASE_URL` 和 `BAILIAN_MODEL` 仍可用。

## 产物地图

| 路径 | 用途 |
|------|------|
| `summary.md` | 人类可读的诊断报告 |
| `artifacts/findings.json` | 规则引擎原始 findings |
| `artifacts/validated_findings.json` | 复核后的 findings |
| `artifacts/action_plan.json` | 有边界的重构计划 |
| `artifacts/critic_review.json` | 计划风险审查 |
| `artifacts/import_graph.json` | 本地 import 图 |
| `artifacts/call_graph.json` | 近似调用图 |
| `artifacts/definitions.json` | 类、函数、方法定义 |
| `artifacts/env_usage.json` | 环境变量读取位置 |
| `artifacts/db_usage.json` | DB/ORM 访问信号 |
| `artifacts/utils_usage.json` | 共享工具依赖统计 |
| `artifacts/global_state.json` | 可变全局状态候选 |
| `module_reports/lightweight/*.md` | 模块速览卡片 |
| `module_reports/heavyweight/*.md` | 模块深度报告 |

原始扫描产物会保留比最终诊断更多的细节。测试和文档可能出现在原始 artifact 中，但在面向诊断的视图里会被过滤或降权。

## 架构

```text
目标 Python 仓库
        |
        v
Governor
        |
        +--> Tool Runner
        |       |
        |       +--> imports / definitions / calls / envs
        |       +--> db signals / utils usage / globals
        |       +--> rules engine
        |
        +--> Validator Agent
        +--> Module Report Agent
        +--> Planner Agent
        +--> Critic Agent
        +--> Policy + Gate Runner
        |
        v
summary.md + artifacts/*.json
```

核心分工：

| 职责 | 所属 |
|------|------|
| AST 扫描、规则执行、策略约束、门禁决定 | 确定性模块 |
| 复核、分诊、规划、解释、风险审查 | Agent 模块，并带确定性回退 |

## 配置文件

| 文件 | 用途 |
|------|------|
| `config/agent_models.json` | 按 agent 角色配置模型路由 |
| `config/policy_config.json` | 受保护路径、单步最大文件数、计划范围 |
| `config/priority_weights.json` | 模块优先级评分 |
| `config/gate_spec.json` | 门禁定义和必需检查 |
| `config/module_registry.json` | 模块元数据注册表 |

模型解析优先级：内置回退值 < 配置文件 < 环境变量。

## 已知限制

- AST 分析是近似的；动态 import、monkey patch、运行时反射、元编程无法完整解析。
- DB 检测基于信号匹配，可能漏掉非常规持久化层。
- 调用图是近似调用图，不捕获所有间接调用。
- 目前只扫描 Python `.py` 文件。
- findings 更偏向产品代码信号；测试和文档会保留在原始 artifact 中，但在诊断阶段过滤或降权。
- LLM agent 目前面向 DashScope / 百炼兼容 API。

## 路线图

- 更强的装饰器和跨文件数据流理解
- 针对高风险重构的 characterization test 建议
- 受控 patch plan 预览，但不自动应用
- 可恢复的迭代状态
- 支持更多 LLM provider
- 支持 TypeScript / JavaScript

## 项目结构

```text
code-decoupling-agent/
  main.py                  # CLI 入口
  agents/                  # governor、validator、planner、critic、模块报告
  scanner/                 # AST 扫描器
  rules_engine/            # RULE_A 到 RULE_G
  policy/                  # 受保护路径和范围约束
  iteration/               # 测试/策略/运行门禁
  llm/                     # 可选 provider 健康检查和模型路由
  report/                  # Markdown 渲染
  config/                  # 路由、策略、优先级、门禁配置
  tests/                   # smoke、golden、reporting、gate、validator 测试
```

## 设计文档

| 文档 | 内容 |
|------|------|
| `ARCHITECTURE.md` | 系统架构、分层、硬约束 |
| `MODULE_SPEC.md` | 模块契约、测试、报告规范 |
| `ITERATION_LOOP.md` | 门禁和受控迭代设计 |
| `MULTI_AGENT.md` | Agent 角色、模型路由、阶段边界 |
| `AGENTS.md` | 产品范围和明确非目标 |

## 许可证

MIT。见 [LICENSE](LICENSE)。
