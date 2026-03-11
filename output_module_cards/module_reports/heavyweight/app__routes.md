# app.routes 模块诊断卡

## 1. 模块职责

- 所属层：interface
- 主要职责：对外暴露请求处理或控制层能力。
- 核心入口：app/routes/user_handler.py

## 2. 关键组成

- `app/routes/__init__.py`
- `app/routes/user_handler.py`

## 3. 依赖关系

- 上游模块数：0
- 下游模块数：0
- 跨层依赖数：0
- 环境变量接触点：0
- 数据库/ORM 接触点：3
- 全局状态风险点：0


## 4. 耦合分析

- 控制层直接接触数据库或 ORM 信号，边界下沉不够。

## 5. 深审增强

- 深审生成方式：deterministic_fallback

### Validator 复核

- 确认状态：confirmed
- 置信度：high
- 结论：当前模块已具备进入重点审查的证据。
- 证据：数据库/ORM 接触点 3 个

### Planner 建议

- 是否建议修改：yes
- 调整优先级：high
- 总结：建议优先针对模块边界和测试薄弱点做受控治理。
- 推荐改法：下沉依赖
- 推荐改法：补测试
- 测试建议：先补最小 characterization tests。
- 测试建议：补接口层到服务层边界的回归测试。

### Critic 审查

- 审查状态：needs_review
- 变更风险：high
- 审查结论：当前模块值得推进，但必须保持小范围、可验证的改动。
- 风险点：测试映射较弱，改动前应先补最小回归测试。

## 6. 修改建议

- 是否建议修改：是
- 修改优先级：P0
- 推荐改法：下沉依赖, 补测试
- 修改风险：高

## 7. 证据

- priority score：19
- 定义数：1
- import 数：1
- 近 200 次提交改动热度：0
- 匹配测试文件数：0
- 相关 findings：
  - Handler/Controller 直接访问数据库 / medium / confirmed / medium
