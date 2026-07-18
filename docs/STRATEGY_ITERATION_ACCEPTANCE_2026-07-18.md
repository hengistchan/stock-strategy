# 策略迭代能力 v0.3 验收记录（2026-07-18）

## 结论

第二阶段策略迭代闭环通过自动化、真实 OpenD 和浏览器验收。策略参数由声明式 schema 驱动；单次回测和批量实验使用同一套运行时注入、行情、撮合、费用和结果契约。

## 功能范围

- 策略顶层 `STRATEGY_PARAMETERS` 字面量声明与 AST 安全解析。
- `strategy_parameter()` 运行时注入，以及 CLI `--parameter NAME=JSON_VALUE` 覆盖。
- Web 单次回测参数表单和 `summary.json` 参数快照。
- 最多 36 组参数笛卡尔积、顺序执行、失败隔离和持久化进度。
- 按策略收益、Sharpe 或最大回撤排名。
- 最多三组成功结果并排比较，并可跳转完整回测证据。
- OpenD 行情确定性共享缓存、库存展示、手动刷新和删除。

## 自动化结果

| 检查项 | 结果 |
| --- | --- |
| Python 单元与 API 测试 | 47 passed |
| Frontend ESLint | passed，无 warning |
| Frontend TypeScript | passed |
| Frontend Vitest | 10 passed |
| Vite production build | passed |
| Python wheel 前端内容校验 | passed |
| Docker Compose 配置解析 | passed |

## 真实 OpenD 参数实验

- 实验 ID：`exp-20260718-142909-a56ba8`
- 标的：`US.AAPL`
- 区间：`2024-01-01` 至 `2025-12-31`
- 行情：`K_DAY / QFQ / ALL`
- 参数：`fast_period=[10,20]`、`slow_period=[40,60]`、`capital_fraction=[0.8,0.9]`
- 组合：8，全部成功；每组 502 根 K 线。
- 排名目标：Sharpe。
- OpenD 请求：第一组 1 页；后续 7 组 `cache_hit=true`、`pages=0`。
- 缓存：`data/opend/cache/5a68b5ea4727a71b.csv`，502 rows，82,590 bytes。

排名第一：

- 参数：`fast_period=20 / slow_period=60 / capital_fraction=0.9`
- 作业：`20260718-142910-8af62e`
- 策略收益：`+52.28%`
- Sharpe：`1.41`
- 最大回撤：`-12.73%`
- 闭合交易：2

排名第二：

- 参数：`fast_period=20 / slow_period=60 / capital_fraction=0.8`
- 策略收益：`+45.93%`
- Sharpe：`1.41`
- 最大回撤：`-11.39%`

这些结果只验证参数实验机制，不构成策略有效性或投资建议。

## 浏览器验收

- 参数定义在单次回测和参数实验工作区正确渲染。
- 8 组结果按 Sharpe 排名，收益、Sharpe、最大回撤、交易数完整可见。
- 勾选前三名后显示 `3 / 3` 并排比较栏。
- 桌面中等宽度下排名表 `clientWidth == scrollWidth`，无需横向滚动；页面无横向溢出。
- 390 px 视口无页面级横向溢出。
- OpenD 缓存卡显示请求条件、实际 502 bars、大小和更新时间。
- 页面无错误遮罩，浏览器控制台无 error 日志。

## 数据与安全边界

- 参数 schema 只允许字面量字典和标量值，不执行声明代码。
- 未声明、越界、类型错误或超过 36 组的请求明确失败。
- 参数作为独立子进程参数传递，不经过 shell。
- 缓存 key 包含标的、开始/结束日期、K 线周期、复权和交易时段。
- 策略本身仍是可信本地 Python 代码，尚未提供不可信代码沙箱。
