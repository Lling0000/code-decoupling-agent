# TASK.md

请基于本仓库中的 `README.md` 和 `AGENTS.md`，实现一个“代码解耦诊断 agent”的最小 MVP。

你的任务不是做完整平台，而是完成一个最小、可运行、可测试的第一版 CLI 工具。

## 一、目标

实现一个本地 Python CLI 工具：

输入一个 Python 仓库路径，输出该仓库的静态扫描结果、规则诊断结果，以及 markdown/json 报告。

第一版只做“扫描 + 诊断 + 报告”，不做自动改代码。

## 二、命令行目标

```bash
python main.py --repo /path/to/repo --output ./output
```

## 三、必须实现的能力

1. import 扫描
2. definitions 扫描
3. 近似 call graph 扫描
4. 环境变量使用扫描
5. 数据库 / ORM 使用痕迹扫描
6. utils/common/helper 依赖扫描
7. 全局状态初步扫描
8. 规则引擎与 findings 生成

## 四、输出要求

```text
output/
  summary.md
  artifacts/
    import_graph.json
    definitions.json
    call_graph.json
    env_usage.json
    db_usage.json
    utils_usage.json
    global_state.json
    findings.json
```

## 五、summary.md 的内容要求

至少包含：

1. Scan Overview
2. Import Dependency Overview
3. Definitions and Call Overview
4. Environment Variable Usage
5. Database Access Signals
6. Shared Utils Dependency
7. Global State Risks
8. Findings
9. Limitations

## 六、测试要求

至少添加基础测试，覆盖：

1. import 扫描
2. env 扫描
3. 至少一条规则命中逻辑

## 七、实现原则

优先顺序：

1. 先保证 CLI 可运行
2. 再保证扫描器可产出 artifact
3. 再实现规则引擎
4. 再生成 markdown 报告
5. 最后补充测试和 README

实现时优先选择简单、可运行、可读、可扩展，不要过度工程化。
