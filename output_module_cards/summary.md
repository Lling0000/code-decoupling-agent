# 代码解耦诊断报告

仓库路径：`D:\agentAI\code-decoupling-agent\tests\fixtures\repos\gold_repo`

## 扫描概览

- 已扫描 Python 文件数：27
- 跳过的解析失败文件数：0
- 原始 findings 数：5
- 经 Validator 复核后的可行动 findings 数：5
- 生成热点清单数：10

## Import 依赖概览

- `app/config/settings.py` 共有 1 个 import
- `app/cycle_a.py` 共有 1 个 import
- `app/cycle_b.py` 共有 1 个 import
- `app/feature_a/consumer.py` 共有 1 个 import
- `app/feature_b/consumer.py` 共有 1 个 import
- 识别到简单循环依赖：1 组

## 定义与调用概览

- 类定义数：1
- 函数定义数：15
- 方法定义数：1
- 近似调用边数：15

## 环境变量使用

- `SHARED_FLAG` 在 3 个文件中被读取，共 3 次

## 数据库访问信号

- `app/routes/user_handler.py` 命中 3 个数据库/ORM 信号

## 共享 Utils 依赖

- `app.common.helpers` 被 5 个文件依赖，覆盖 5 个包

## 全局状态风险

- `app/state/cache.py` 命中 1 个疑似全局状态风险

## 仓库理解

- `app/routes/user_handler.py` 热点分数 7 (imports=1, db=3, globals=0)
- `app/config/settings.py` 热点分数 2 (imports=1, db=0, globals=0)
- `app/services/service_a.py` 热点分数 2 (imports=1, db=0, globals=0)
- `app/services/service_b.py` 热点分数 2 (imports=1, db=0, globals=0)
- `app/state/cache.py` 热点分数 2 (imports=0, db=0, globals=1)

## Findings

- Validator 生成方式：确定性回退
- 已确认：5，需复核：0，已驳回：0

### 疑似可变全局状态

- 严重级别：高
- 确认状态：已确认
- 置信度：高
- 文件：app/state/cache.py
- 证据：CACHE (mutable_literal，第 1 行，变更次数=1)
- 解释：模块级可变对象在函数作用域中被修改，说明共享状态正在跨函数传播，副作用会更难追踪。
- 建议：建议把共享状态封装到显式对象、工厂或依赖注入边界中，让写入路径更清晰、更易测试。
- 验证说明：模块级可变对象在函数作用域内被修改，共享状态风险较高。

### Handler/Controller 直接访问数据库

- 严重级别：中
- 确认状态：已确认
- 置信度：中
- 文件：app/routes/user_handler.py
- 证据：select（第 5 行，置信度=中）; session.execute（第 5 行，置信度=中）
- 解释：请求层文件中直接出现数据库或 ORM 操作，通常说明业务边界和数据访问边界没有被清晰隔离。
- 建议：建议把数据库访问下沉到显式的 service 或 repository 层，让 handler/controller 只负责请求编排。
- 验证说明：路径命中请求层关键词，且存在数据库访问操作证据。

### 同一环境变量在多个文件中被直接读取

- 严重级别：中
- 确认状态：已确认
- 置信度：中
- 文件：app/services/service_a.py, app/services/service_b.py
- 证据：SHARED_FLAG 在 2 个业务文件中被直接读取; 已忽略 1 个配置或测试文件中的读取
- 解释：同一个环境变量在多个业务文件中被直接读取，会让配置入口分散，增加修改和排查时的耦合成本。
- 建议：建议把环境变量读取集中到专门的配置模块，再把配置对象传入业务代码。
- 验证说明：同一环境变量在多个业务文件中被直接读取，具备稳定配置分散信号。

### 共享 Utils 模块被过度依赖

- 严重级别：中
- 确认状态：已确认
- 置信度：中
- 文件：app/feature_a/consumer.py, app/feature_b/consumer.py, app/feature_c/consumer.py, app/feature_d/consumer.py, app/feature_e/consumer.py
- 证据：app.common.helpers 被 5 个文件依赖，覆盖 5 个包
- 解释：共享 utils/common/helper 模块被多个包横向依赖，通常意味着跨领域的隐式耦合正在累积。
- 建议：建议按领域边界拆分共享工具模块，把真正通用的能力和领域能力分开。
- 验证说明：共享工具模块的依赖范围跨越多个文件或包，存在横向耦合迹象。

### 检测到简单循环 Import

- 严重级别：中
- 确认状态：已确认
- 置信度：中
- 文件：app/cycle_a.py, app/cycle_b.py
- 证据：app/cycle_a.py -> app/cycle_b.py
- 解释：发现了强连通的 import 组件。循环依赖通常会增加初始化脆弱性，并让模块边界更难维护。
- 建议：建议提取稳定的共享接口或中间边界模块，把双向依赖重新拆回单向依赖。
- 验证说明：Import 图中存在强连通组件，循环依赖证据明确。

## 行动计划

- 计划策略：多 Agent 规划，确定性工具负责执行约束
- 当前展开步骤数：5
- Planner 生成方式：确定性
- STEP-01 [P0] 隔离模块级可变状态 负责人=重构 Agent 涉及文件数=1
- STEP-02 [P1] 拆分过载的共享工具依赖 负责人=重构 Agent 涉及文件数=5
- STEP-03 [P1] 集中管理环境变量读取 负责人=规划 Agent 涉及文件数=2
- STEP-04 [P1] 通过提取接口或边界打破循环依赖 负责人=规划 Agent 涉及文件数=2
- STEP-05 [P1] 将数据库访问从请求层抽离出去 负责人=重构 Agent 涉及文件数=1

## 审查结果

- 状态：需要人工复核
- 风险等级：高
- 总结：计划在执行前需要人工复核。
- 必需检查：python -m unittest, targeted regression tests
- Critic 生成方式：确定性
- 风险点：仓库缺少明显测试，任何重构计划都应先补 characterization tests。

## 模型路由

- `总控编排` -> `deepseek-v3.2` via `bailian` (推理)
- `规划与分诊` -> `deepseek-v3.2` via `bailian` (推理)
- `Finding 复核` -> `deepseek-v3.2` via `bailian` (推理)
- `审查` -> `deepseek-v3.2` via `bailian` (推理)
- `重构与测试补全` -> `qwen3-coder-flash` via `bailian` (编码)
- `摘要与说明生成` -> `qwen3.5-flash` via `bailian` (快速生成)
- `向量召回` -> `text-embedding-v4` via `bailian` (检索)
- `重排` -> `qwen3-rerank` via `bailian` (检索)
- Provider `bailian` 的环境变量 `DASHSCOPE_API_KEY` 状态：已配置
- Provider Base URL：`https://dashscope.aliyuncs.com/compatible-mode/v1`

## 局限性

- 当前分析基于 AST，属于有意保持轻量化的近似静态分析。
- 动态 import、运行时 monkey patch、反射和间接调用目前都无法精确解析。
- 数据库访问检测仍然是信号式识别，仍可能存在少量误报或漏报。
- 环境变量检测目前主要覆盖字符串字面量形式的常见读取模式。
- 目前只有 Planner 和 Critic 可以走 live LLM，扫描、规则和策略判断仍然是确定性链路。
- Planner 和 Critic 输出受 schema 约束，调用失败时会回退到确定性结果。
