# 解耦迭代系统总架构

## 1. 目标

本项目的目标不是做一个“会自己到处改代码的自动 agent”，而是做一个**受控的仓库解耦迭代系统**：

- 输入：一个待治理的本地仓库
- 输出：结构化诊断、复核后的 finding、受控的改造计划、双报告结果
- 约束：任何进入下一轮的改动，必须同时满足
  - 通过测试
  - 通过策略
  - 仓库可运行

核心原则：

> 只有“通过测试 + 通过策略 + 可运行”的改动，才允许进入下一轮。  
> 否则它不是解耦系统，而是自动破坏系统。

## 2. 当前系统定位

当前仓库已经实现的是“诊断 + 复核 + 规划 + 审查”的前半段系统。

已经存在的能力：

- Python 仓库静态扫描
- 规则引擎诊断
- Validator Agent 二次复核
- Planner Agent 生成整改计划
- Critic Agent 审查整改计划
- Markdown + JSON 双输出
- LLM 配置自检
- 金标回归测试

还没有开放的能力：

- 自动改代码落盘
- 自动提交 patch
- 自动执行重构
- 自动合并

因此，当前项目仍然是**受控规划系统**，不是自动执行系统。

## 3. 总体分层

系统按职责分为 6 层。

### 3.1 仓库输入层

职责：

- 读取目标仓库
- 建立 `RepoContext`
- 收集 `.py` 文件
- 记录解析失败文件

当前实现：

- `scanner/__init__.py`
- `models/schema.py`

### 3.2 确定性扫描层

职责：

- 扫描 import 关系
- 扫描 definitions
- 扫描 calls
- 扫描 env 使用
- 扫描 db/orm 信号
- 扫描 utils/common/helper 依赖
- 扫描 global state 风险

当前实现：

- `scanner/imports.py`
- `scanner/definitions.py`
- `scanner/calls.py`
- `scanner/envs.py`
- `scanner/db_usage.py`
- `scanner/utils_usage.py`
- `scanner/globals.py`

这层必须保持**确定性优先**，不能让 LLM 代替基础扫描。

### 3.3 确定性诊断层

职责：

- 基于扫描 artifacts 运行规则
- 产出原始 findings
- 检测 simple import cycles

当前实现：

- `rules_engine/engine.py`
- `rules/config.py`

这层产出的是**候选问题**，不是最终可信结论。

### 3.4 Agent 复核与规划层

职责：

- 对原始 findings 做二次确认
- 过滤明显误报
- 给 finding 打确认状态与置信度
- 基于可信 finding 生成 triage 与 action plan
- 对 action plan 做风险审查

当前角色：

- `Governor`：总控编排
- `Validator Agent`：复核 finding
- `Planner Agent`：生成行动计划
- `Critic Agent`：审查行动计划

当前实现：

- `agents/governor.py`
- `agents/validator_agent.py`
- `agents/planner_agent.py`
- `agents/critic_agent.py`

这层允许用 LLM，但必须满足：

- 只读上下文
- 只输出结构化结果
- 不直接改代码
- 调用失败时回退到确定性逻辑

### 3.5 策略与验证层

职责：

- 限定允许的作用范围
- 检查 protected paths
- 检查 step 是否过大
- 阻止危险计划进入执行阶段

当前实现：

- `policy/engine.py`

未来要补强的验证器：

- 目标仓库测试执行器
- 入口运行验证器
- 类型检查器
- 格式/静态检查器

这层必须是**硬门禁**，不能交给 agent 主观判断。

### 3.6 报告与产物层

职责：

- 输出给 agent 的结构化 JSON
- 输出给人的 Markdown 报告
- 保证结果可复查、可回归、可比较

当前实现：

- `report/renderer.py`
- `main.py`

## 4. 当前核心链路

当前主流程如下：

```text
目标仓库
  -> RepoContext
  -> 确定性扫描 artifacts
  -> 原始 findings
  -> Validator Agent
  -> validated_findings
  -> triage
  -> action_plan
  -> Critic Review
  -> summary.md + artifacts/*.json
```

当前真实输出包括：

- `import_graph.json`
- `definitions.json`
- `call_graph.json`
- `env_usage.json`
- `db_usage.json`
- `utils_usage.json`
- `global_state.json`
- `findings.json`
- `validated_findings.json`
- `repo_inventory.json`
- `triage.json`
- `action_plan.json`
- `critic_review.json`
- `planner_agent.json`
- `critic_agent.json`
- `model_routing.json`
- `summary.md`

## 5. Agent 与确定性模块边界

这是本系统最重要的边界。

### 5.1 Agent 负责什么

- 理解
- 复核
- 分诊
- 规划
- 审查
- 解释

### 5.2 确定性模块负责什么

- 扫描
- 规则判断
- 策略门禁
- 测试执行
- 可运行性验证
- 最终放行

### 5.3 明确禁止

以下能力不能由 agent 单独决定：

- 是否跳过测试
- 是否跳过 policy
- 是否允许改 protected files
- 是否在仓库不可运行时继续推进
- 是否把失败改动带进下一轮

## 6. 模块化设计原则

系统中的每个独立能力都定义为一个模块。

每个模块必须具备：

- 独立职责
- 明确输入
- 明确输出
- 独立测试
- 模块 README
- 可被 agent 读取的结构化 contract

模块不是“任意一个文件”，而是“一个完整能力单元”。

例如：

- `scanner.imports`
- `scanner.envs`
- `rules_engine`
- `validator_agent`
- `planner_agent`
- `critic_agent`
- `policy.engine`
- `report.renderer`

## 7. 目标演进方向

系统最终将从“诊断系统”演进为“受控解耦迭代系统”。

目标形态：

```text
诊断
  -> 复核
  -> 规划
  -> 审查
  -> 受控 patch plan
  -> 受控执行
  -> 测试/运行验证
  -> 双报告
  -> 进入下一轮
```

但进入执行阶段前，必须先补齐：

- 目标仓库运行验证
- 补丁执行器
- 回滚策略
- 每轮迭代门禁
- 模块级 README 与 contract 完整化

## 8. 架构中的硬约束

所有未来设计都必须遵守以下约束：

1. 扫描必须确定性优先
2. finding 必须先复核，再进入规划
3. 计划必须经过 Critic 与 Policy 审查
4. 执行前必须有测试与运行验证
5. 不允许未验证改动进入下一轮
6. 每轮必须同时产出 agent 可读结果和人类可读结果

## 9. 当前推荐工作顺序

建议后续按这个顺序推进：

1. 强化模块 contract 与 README
2. 为每个模块补齐更系统的测试
3. 建立“测试 + 策略 + 可运行”三段式 gate
4. 再引入 Refactor Agent 的 patch plan
5. 最后才考虑受控写文件

## 10. 一句话总结

这个项目的本质不是“多 agent 自动改代码”，而是：

**一个以确定性扫描和硬验证为底座、以 agent 负责复核与规划的受控解耦迭代系统。**
