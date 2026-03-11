# {{ module_id }}

## 作用

用一句话说明这个模块的核心职责。

## 当前状态

- 状态：`implemented | partially_implemented | planned`
- 模块类型：`scanner | rules_engine | agent | guardrail | reporting | entrypoint | llm_support`

## 输入

- 输入 1
- 输入 2

## 输出

- 输出 1
- 输出 2

## 依赖

- 上游模块
- 下游模块

## 测试

- 单元测试：`tests/...`
- 金标测试：`tests/...`
- 集成测试：`tests/...`
- CLI 测试：`tests/...`

## 给 Agent 的结果

- 结构化结果路径：`artifacts/...`
- 关键字段：
  - `status`
  - `passed`
  - `failed`
  - `gate_decision`

## 给人的结果

- 可读报告路径：`reports/...` 或 `summary.md`
- 建议包含：
  - 这轮变了什么
  - 有哪些风险
  - 是否允许进入下一轮

## 已知限制

- 限制 1
- 限制 2

## 后续演进

- 下一步计划 1
- 下一步计划 2
