# 模块设计规范

## 1. 目的

本文件定义“一个模块在本系统里应该长什么样”。

目标是让每个模块都具备：

- 可运行
- 可测试
- 可解释
- 可替换
- 可被 agent 读取
- 可被人审查

## 2. 模块定义

在本系统中，一个模块是一个**独立能力单元**，而不是任意单个文件。

模块必须满足：

- 有明确职责
- 有稳定输入
- 有稳定输出
- 能独立测试
- 能单独阅读和维护

## 3. 每个模块必须具备的内容

每个模块必须有 6 类内容。

### 3.1 代码

模块的主实现代码。

### 3.2 README

给人看的模块说明。

建议命名：

- `README.md`

### 3.3 Contract

给 agent 和测试系统读的结构化约定。

推荐字段：

- `module_id`
- `module_type`
- `responsibility`
- `inputs`
- `outputs`
- `dependencies`
- `failure_modes`
- `test_entrypoints`

当前阶段可以先写在文档里，后续再落成 JSON/YAML。

### 3.4 测试

每个模块都必须有测试，不允许“只有集成跑通，没有模块测试”。

### 3.5 Agent 报告

给 agent 读的结构化结果。

推荐格式：

- JSON

### 3.6 Human 报告

给人看的可读总结。

推荐格式：

- Markdown

## 4. 模块输出分为两类

### 4.1 给 agent 看

必须结构化、稳定、便于比较。

推荐输出：

```json
{
  "module_id": "validator_agent",
  "status": "passed",
  "inputs_ok": true,
  "outputs_ok": true,
  "tests": {
    "passed": 12,
    "failed": 0
  },
  "artifacts": [
    "validated_findings.json"
  ],
  "risks": [],
  "next_action": "allow_next_stage"
}
```

### 4.2 给人看

必须强调结论、风险和建议。

推荐输出：

```md
# validator_agent 模块结果

- 状态：通过
- 输入：findings + file snippets
- 输出：validated_findings.json
- 风险：无阻断项
- 建议：可以进入 triage 阶段
```

## 5. 模块测试分层

每个模块至少要有以下 5 类测试中的一部分。

### 5.1 单元测试

验证模块内部关键逻辑。

例如：

- `scan_env_usage()` 是否识别 `os.getenv`
- `scan_db_usage()` 是否忽略明显误报

### 5.2 Contract 测试

验证输出结构是否稳定。

例如：

- 是否总是返回 `findings` + `summary`
- 字段名是否变动
- 枚举值是否合法

### 5.3 Golden 测试

验证在固定仓库输入上，结果是否符合预期。

例如：

- 某条规则应该命中
- 某个误报不应该再出现

### 5.4 集成测试

验证模块与上下游模块连接后能否工作。

例如：

- `validator_agent` 能否接收 `findings` 并产出 `validated_findings`

### 5.5 CLI / 端到端测试

验证用户真实入口是否正常。

例如：

- `python main.py --repo ... --output ...`

## 6. 当前模块清单

下面是当前仓库里已经比较明确的模块。

### 6.1 仓库上下文模块

- 实现：`scanner/__init__.py`
- 职责：建立 `RepoContext`
- 输入：仓库路径
- 输出：解析后的文件列表、模块索引、解析错误

### 6.2 Import Scanner

- 实现：`scanner/imports.py`
- 输入：`RepoContext`
- 输出：`import_graph.json`
- 测试重点：
  - 本地依赖识别
  - `TYPE_CHECKING` 过滤
  - cycle 输入正确性

### 6.3 Definitions Scanner

- 实现：`scanner/definitions.py`
- 输出：`definitions.json`
- 测试重点：
  - class/function/method 计数
  - 行号稳定性

### 6.4 Call Scanner

- 实现：`scanner/calls.py`
- 输出：`call_graph.json`
- 测试重点：
  - 常见调用表达式提取
  - 调用边稳定性

### 6.5 Env Scanner

- 实现：`scanner/envs.py`
- 输出：`env_usage.json`
- 测试重点：
  - `os.getenv`
  - `os.environ[...]`
  - `os.environ.get`
  - 配置文件豁免规则的上下游影响

### 6.6 DB Usage Scanner

- 实现：`scanner/db_usage.py`
- 输出：`db_usage.json`
- 测试重点：
  - SQLAlchemy/Session 来源证明
  - 常见误报过滤

### 6.7 Utils Usage Scanner

- 实现：`scanner/utils_usage.py`
- 输出：`utils_usage.json`
- 测试重点：
  - 只统计本地模块
  - 外部 `*.utils.*` 误报过滤

### 6.8 Global State Scanner

- 实现：`scanner/globals.py`
- 输出：`global_state.json`
- 测试重点：
  - 模块级可变对象识别
  - 函数内变更证据
  - 常量/`__all__` 误报过滤

### 6.9 Rule Engine

- 实现：`rules_engine/engine.py`
- 输出：`findings.json`
- 测试重点：
  - RULE_A/B/C/D/E 命中
  - 严重级别
  - 误报回归

### 6.10 Validator Agent

- 实现：`agents/validator_agent.py`
- 输入：`findings + file snippets`
- 输出：`validated_findings.json`
- 测试重点：
  - `confirmation_status`
  - `confidence`
  - `validation_reason`
  - `file_snippets`
  - LLM / fallback 双路径

### 6.11 Planner Agent

- 实现：`agents/planner_agent.py`
- 输入：`validated_findings` 的 actionable 子集
- 输出：`triage.json`、`action_plan.json`
- 测试重点：
  - bounded plan
  - file scope 限制
  - step schema

### 6.12 Critic Agent

- 实现：`agents/critic_agent.py`
- 输入：`action_plan`
- 输出：`critic_review.json`
- 测试重点：
  - 状态枚举
  - 风险级别
  - policy 结果一致性

### 6.13 Policy Engine

- 实现：`policy/engine.py`
- 输出：保护路径、超大 step 等约束结果
- 测试重点：
  - protected path 命中
  - oversized step 检测

### 6.14 Report Renderer

- 实现：`report/renderer.py`
- 输出：`summary.md`
- 测试重点：
  - 中文输出
  - finding/validator 字段可见
  - 空结果时仍可读

### 6.15 CLI

- 实现：`main.py`
- 输出：完整 artifacts + summary
- 测试重点：
  - 参数校验
  - 输出文件齐全
  - `--check-llm-config`

## 7. 模块 README 模板

建议每个模块未来补一个 README，结构如下：

```md
# 模块名

## 作用

一句话说明模块职责。

## 输入

- 输入 1
- 输入 2

## 输出

- artifact 1
- artifact 2

## 依赖

- 上游模块
- 下游模块

## 测试

- 单元测试位置
- 金标测试位置
- 集成测试位置

## 已知限制

- 限制 1
- 限制 2
```

## 8. 测试结果双输出规范

未来建议为每个模块都产出两份测试结果。

### 8.1 Agent 测试结果

建议路径：

- `artifacts/module_tests/<module_id>.json`

建议字段：

- `module_id`
- `status`
- `passed`
- `failed`
- `coverage`
- `regressions`
- `gate_decision`

### 8.2 Human 测试结果

建议路径：

- `reports/module_tests/<module_id>.md`

建议内容：

- 本轮修改点
- 测试通过情况
- 回归风险
- 是否允许进入下一轮

## 9. 模块放行条件

一个模块只有在满足以下条件时，才允许被视为“通过”：

1. Contract 没破坏
2. 测试通过
3. 输出稳定
4. 对上游/下游没有引入新的阻断回归
5. 人类可以读懂该模块当前行为

## 10. 一句话总结

模块不是代码碎片，而是：

**有职责、有 contract、有测试、有 README、有双报告输出的独立能力单元。**
