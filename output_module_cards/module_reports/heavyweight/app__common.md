# app.common 模块诊断卡

## 1. 模块职责

- 所属层：shared
- 主要职责：提供共享工具或跨模块复用能力。
- 核心入口：app/common/helpers.py

## 2. 关键组成

- `app/common/__init__.py`
- `app/common/helpers.py`

## 3. 依赖关系

- 上游模块数：5
- 下游模块数：0
- 跨层依赖数：0
- 环境变量接触点：0
- 数据库/ORM 接触点：0
- 全局状态风险点：0

- 上游依赖：app.feature_a, app.feature_b, app.feature_c, app.feature_d, app.feature_e

## 4. 耦合分析

- 高扇入模块，修改可能带来较大影响面。

## 5. 深审增强

- 深审生成方式：deterministic_fallback

### Validator 复核

- 确认状态：needs_review
- 置信度：medium
- 结论：当前模块值得继续观察，但仍建议结合更多上下文确认。
- 证据：当前主要依赖综合风险分排序进入重点观察队列

### Planner 建议

- 是否建议修改：yes
- 调整优先级：medium
- 总结：建议优先针对模块边界和测试薄弱点做受控治理。
- 推荐改法：补测试
- 测试建议：先补最小 characterization tests。

### Critic 审查

- 审查状态：needs_review
- 变更风险：medium
- 审查结论：当前模块值得推进，但必须保持小范围、可验证的改动。
- 风险点：测试映射较弱，改动前应先补最小回归测试。
- 风险点：高扇入模块，改动影响面较大。

## 6. 修改建议

- 是否建议修改：是
- 修改优先级：P1
- 推荐改法：补测试
- 修改风险：中

## 7. 证据

- priority score：17
- 定义数：1
- import 数：0
- 近 200 次提交改动热度：0
- 匹配测试文件数：0
- 相关 findings：无直接命中
