# Futu 兼容契约 v2 验收记录（2026-07-18）

## 结论

`engine_contract v2` 通过工程验收和真实 OpenD 单标的验收。新契约禁止静默忽略 K 线周期、交易时段和复权类型，修正 DAY 订单生命周期，并将期末强平改为显式选项。

本记录证明数据、策略执行、撮合、产物和 Web 展示链路符合当前项目契约，不证明策略具有投资有效性，也不代表完整复制 Futu 平台。

## 自动化结果

| 检查项 | 结果 |
| --- | --- |
| Python 单元与 API 测试 | 38 passed |
| Frontend ESLint | passed |
| Frontend TypeScript | passed |
| Frontend Vitest | 8 passed |
| Vite production build | passed |
| OpenD 同字段结构端到端 | passed，300 bars，1 closed trade |
| Docker Compose 配置解析 | passed |
| Python wheel | passed，前端 6 个文件与当前 `web_dist` 精确一致 |

端到端构造数据产物位于：

- `runs/acceptance-contract-v2/20260718-135908-ma_cross/`

## 真实 OpenD 验收

运行条件：

- 标的：`US.AAPL`
- 区间：`2024-01-01` 至 `2025-12-31`
- K 线：`K_DAY`
- 复权：`QFQ`
- 交易时段：`ALL`
- 策略：`examples/ma_cross.py`，MA20 / MA60
- warmup：`0`
- 期末政策：保留持仓并按末价盯市

OpenD 与产物核对：

- OpenD 分页：1 页
- CSV 数据行：502
- 回测 K 线：502
- 资金曲线数据行：502
- 闭合交易：2
- 期末持仓：`LONG 513`
- 期末标记价：`271.355839436`
- 未实现盈亏：`31,558.75`
- 期末权益：`152,277.83`
- 策略收益：`+52.28%`
- 最大回撤：`-12.73%`
- Sharpe：`1.41`
- 总费用：`158.53`

产物：

- `data/opend/contract-v2/US.AAPL-K_DAY-QFQ-ALL-2024-2025.csv`
- `runs/opend-contract-v2/20260718-135436-ma_cross/summary.json`
- `runs/opend-contract-v2/20260718-135436-ma_cross/trades.csv`
- `runs/opend-contract-v2/20260718-135436-ma_cross/equity_curve.csv`
- `runs/opend-contract-v2/20260718-135436-ma_cross/report.svg`

## Web / 浏览器验收

通过 Web API 创建真实 OpenD 回测任务 `20260718-135915-aa355e`，成功产出：

- `runs/web/20260718-135915-aa355e/output/20260718-135915-ma_cross/`

浏览器核对结果：

- 页面显示 `OPEND CONTRACT V2`、`K_DAY / QFQ / ALL` 与 502 根 K 线。
- 页面显示期末未强平持仓 `LONG 513`、持仓均价、期末标记价和未实现盈亏。
- 价格图显示 OHLC、成交量、MA20、MA60 和入场/出场位置；末根 K 线价格为 `O 272.55 / H 273.17 / L 271.25 / C 271.36`。
- `3M` 区间切换后，图表从默认一年 252 根缩放为 63 根，再切回 `1Y` 成功。
- 页面无错误遮罩，浏览器控制台无 error 级别日志。

## 契约检查

- 策略声明 `BarType.K_DAY` 时，输入必须为 `K_DAY`；传入 `K_5M` 会明确失败，不再按 5 分钟数据静默计算“日线”均线。
- Futu 行情与指标 API 要求 `QFQ`；`HFQ` / `NONE` 会明确失败。
- 对美股，策略 `THType` 必须与 OpenD `session` 一致。
- `bar_custom(TURNOVER)` 在 OHLCV 模型尚不支持成交额时抛出 `UnsupportedAPIError`，不再返回收盘价。
- 分钟 DAY 单在当日持续有效，尾盘未成交单不会顺延到次日；日线 next-bar 订单从第一根可执行日开始生效。
- 待成交买单冻结估算现金，待成交卖单冻结可卖持仓。
- 期末默认不强平；Web 会展示期末持仓、标记价和未实现盈亏。显式选择“末根 K 线强制平仓”后才产生 `end-of-test` 平仓交易。
- 新结果写入 `settings.engine_contract.version = 2`；旧结果在 Web 中标记为 `LEGACY RESULT`。

## 仍未覆盖

- 证券 lot size / 期货合约手数自动下舍入
- 部分成交、流动性、涨跌停和订单簿
- 多标的、组合资金分配、Tick / N 秒 / 定时触发
- 完整账户、保证金、订单查询、期权与期货接口
- Futu 自定义指标运行环境和受限 Python 沙箱

完整边界见 `docs/FUTU_COMPATIBILITY.md`。
