# MVP 验收结果（2026-07-15）

## 结论

- 自动化工程验收：通过。
- OpenD 直连与分页契约验收：通过。
- 真实历史行情端到端回测：通过。
- 项目 Skill 的 OpenD 直连入口：通过。
- 用户自定义策略验收：未执行；当前使用项目示例 `examples/ma_cross.py`。

## 验收环境

- OpenD：`127.0.0.1:11111`，本机版本 `10.6.6608`。
- Futu Python SDK：项目 `.venv` 中的 `futu-api 10.6.6608`。
- 标的：`US.AAPL`。
- 行情区间：`2024-01-01` 至 `2025-12-31`。
- K 线与复权：`K_DAY`、`QFQ`。
- 策略：20/60 日均线交叉示例。
- 撮合：next-bar execution；3 bps 佣金、最低 1、5 bps 滑点。

## 自动化证据

运行 `python3 backend/scripts/acceptance.py`：

- 18 项测试通过。
- OpenD 同字段结构的构造行情验收通过。
- 四类产物存在且可解析。
- 汇总交易数、资金曲线长度和期末权益一致。

项目 Skill 通过 `quick_validate.py`，并成功用 `--opend` 运行真实历史行情。

## 真实行情证据

- OpenD 原始缓存：[US.AAPL-K_DAY-2024-2025.csv](../data/opend/US.AAPL-K_DAY-2024-2025.csv)
- 回测汇总：[summary.json](../runs/real-acceptance/20260715-225125-ma_cross/summary.json)
- 成交记录：[trades.csv](../runs/real-acceptance/20260715-225125-ma_cross/trades.csv)
- 资金曲线：[equity_curve.csv](../runs/real-acceptance/20260715-225125-ma_cross/equity_curve.csv)
- 图表报告：[report.svg](../runs/real-acceptance/20260715-225125-ma_cross/report.svg)

OpenD 返回 502 根日 K，导入后仍为 502 根；资金曲线也是 502 个点。

| 指标 | 结果 |
| --- | ---: |
| 期末权益 | 152,166.49 |
| 策略收益 | 52.17% |
| 买入持有 | 47.83% |
| 年化收益 | 23.41% |
| 最大回撤 | -12.73% |
| Sharpe | 1.41 |
| 闭合交易 | 3 |
| 胜率 | 66.7% |
| 总费用 | 200.27 |

这些指标仅描述本次历史回测，不构成策略稳健性结论或买卖建议。

## 逐笔撮合核对

3 笔交易均与 20/60 日均线信号序列一致：

1. 信号单在下一根 K 线开盘成交。
2. 买入价等于下一根开盘价加 5 bps 滑点。
3. 信号卖出价等于下一根开盘价减 5 bps 滑点。
4. 测试结束平仓价等于最后收盘价减 5 bps 滑点。
5. 每笔费用等于买卖成交额乘 3 bps，且满足最低佣金规则。
6. 三笔净盈亏之和与期末权益变化一致。

## 尚未签收的范围

只有将用户自己的 `StrategyBase` 脚本替换示例策略后，才算完成用户策略业务验收。多标的组合、公司行动自动处理、真实账户下单、部分成交、订单簿、涨跌停和流动性约束仍不属于 MVP 范围。
