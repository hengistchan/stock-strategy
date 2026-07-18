# Futu 脚本兼容范围（MVP）

本项目参考 `量化使用手冊.md` 中的代码策略运行框架：`initialize()` 只运行一次，默认从第一根 K 线开始触发 `handle_data()`。目标是让常用的 Futu 风格策略可在本地回测，而不是完整复制 Futu 平台。

## OpenD 行情输入

- 原生识别 `request_history_kline()` DataFrame 导出的 `code`、`time_key`、OHLCV 列。
- 单标的文件自动采用 `code`；多标的文件必须通过 `--symbol` 选择，否则明确报错。
- 完整保留分钟 K 的 `time_key`。美股时间按 OpenD 返回的美东时间保存，港股与 A 股按默认北京时间保存，不做隐式转换。
- OpenD 直连会显式传入 `session`；`ALL` / `ETH` 请求扩展时段，`RTH` 只请求盘中行情。
- `name`、`turnover`、`turnover_rate`、`pe_ratio`、`change_rate`、`last_close` 等非撮合字段可存在但不会进入 MVP 撮合。

## 已支持

| 类别 | API |
| --- | --- |
| 策略框架 | `StrategyBase`、`initialize()`、`handle_data()`、`declare_strategy_type()`、`declare_trig_symbol()`、`show_variable()` |
| 行情 | `current_price()`、`bar_open()`、`bar_high()`、`bar_low()`、`bar_close()`、`bar_volume()`、`bar_custom()` |
| 指标 | `ma()`、`ema()`、`rsi()`、`historical_volatility()`、`macd_dif()`、`macd_dea()`、`macd_macd()`、MACD 金叉/死叉 |
| 订单 | `place_market()`、`place_limit()`、`place_stop()`、`close_positions()`、`cancel_order_all()` |
| 持仓 | `position_holding_qty()`、`position_side()`、`max_qty_to_buy_on_cash()`、`max_qty_to_sell()` |
| 常用类型 | `Contract`、`BarType`、`CustomType`、`DataType`、`BarDataType`、`THType`、`TSType`、`OrderSide`、`PositionSide`、`TimeInForce`、`OrdType`、`AlgoStrategyType`、`GlobalType` |

## 单周期兼容契约

一次回测只持有一套 OpenD K 线。所选 `ktype`、`session` 和 `autype` 会进入执行上下文，并遵循以下规则：

- Futu `bar_*` 和指标 API 请求的 `BarType` 必须与输入 `ktype` 一致；MVP 不做隐式重采样。
- 对美股，API 请求的 `THType` 必须与 OpenD 输入时段一致；非美股沿用手册“该参数不生效”的约定。
- 手册中的 `bar_*` 和指标是前复权语义，因此这些 API 只接受 `QFQ` 输入。`HFQ` / `NONE` 仍可用于不调用这些接口的自定义策略。
- 不一致或尚未支持的组合会抛出 `UnsupportedAPIError`，不会忽略参数或伪造返回值。
- `bar_custom()` 当前可靠支持聚合 OHLCV；`TURNOVER` 等尚未进入 `Bar` 模型的字段会明确报错。
- `warmup_bars` 默认为 `0`，与手册逐 K 线触发生命周期一致。显式设置为正数时，前 N 根只建立行情历史、不调用 `handle_data()`；这是本项目的可选扩展，不是 Futu 接口语义。
- 新结果写入 `settings.engine_contract.version = 2`。缺少该版本的历史任务会在 Web 中标记为 `LEGACY RESULT`，需要重新运行后再比较。

## Strategy Lab 参数扩展

- `STRATEGY_PARAMETERS` 和 `strategy_parameter()` 是本项目为策略迭代提供的扩展，不属于 Futu 原生脚本 API。
- 参数声明必须是顶层字面量字典；编辑保存、Web API、CLI 和运行时会重复验证类型、上下界和可选值。
- `--parameter NAME=JSON_VALUE` 或 Web 参数表单只覆盖声明过的参数，未知参数会明确失败。
- 参数实验只改变策略参数，行情、费用、撮合和回测区间保持一致；每组都生成独立结果，排名不是额外回测模型。

## 撮合约定

- `handle_data()` 在当前 K 线收盘后运行。
- 在 `handle_data()` 中提交的市价单，下一根 K 线开盘成交并计入滑点。
- 限价单和止损单从下一根 K 线开始，根据 OHLC 区间判断是否触发。
- `DAY` 从第一根可执行 K 线所属交易日开始生效，在该交易日内持续等待，跨交易日后失效；`GTC` 会继续保留。
- 待成交买单会冻结估算现金，待成交卖单会冻结可卖持仓；可买、可卖查询会扣除冻结部分。
- 回测结束默认保留持仓并按最后收盘价盯市，`summary.json` 记录 `ending_position`。只有显式启用 `--liquidate-on-end`（或 Web 中的“末根 K 线强制平仓”）才会按最后收盘价加滑点平仓。
- 手续费和滑点均进入净值与成交盈亏。
- 分钟级 Sharpe 与历史波动率依据输入数据中实际观察到的每日 K 线数量年化，不假定固定的美股 RTH 时长。
- 默认只允许多头；启用 `--allow-short` 后可使用 `SELL_SHORT` / `BUY_BACK`。

这些约定保证收盘信号不会使用同一根 K 线的开盘价成交，从而避免明显的未来函数。

## 暂不支持

- 多标的、组合级资金分配和跨品种订单
- Tick / 每 N 秒 / 定时触发
- 复权、拆股、分红与交易日历处理（应在导入数据前处理）
- `register_indicator()`、`get_MyLang_indicator()`、`register_indicator_Python()`
- 跟踪止损、触及单、改单、期权、期货转仓、融资融券与完整账户 API
- 证券 `lot_size` / 期货合约手数自动下舍入
- 部分成交、订单簿、涨跌停、流动性和成交量限制

未支持的自定义指标注册会抛出 `UnsupportedAPIError`，不会返回伪造数据。
