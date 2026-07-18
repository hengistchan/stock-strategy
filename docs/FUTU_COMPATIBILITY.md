# Futu 股票代码策略兼容契约

本项目以 `量化使用手冊.md` 的代码策略环境为接口边界，模拟股票历史回测。运行时契约版本为 `3`。期货、期权、窝轮、牛熊证和其他衍生品不在本项目范围内。

## OpenD 数据边界

- 历史行情来自 OpenD `request_history_kline()`，保留 `code`、`time_key`、OHLCV、`turnover`、`turnover_rate`、`change_rate` 和 `last_close`。
- 股票名称、每手股数、最小价差、停牌和品类等静态信息来自 OpenD `get_market_snapshot()`。
- 单次回测只交易一个触发标的；不做组合资金分配。
- 美股历史时间保留 OpenD 返回的美东市场时间。`device_time()` 可按手册转换到指定 `TimeZone`，包含夏令时。
- Futu K 线和指标接口采用前复权语义，因此要求 `QFQ`。非复权数据仍可供完全自定义、且不调用这些接口的策略使用。

## 多周期历史回测

策略可以同时使用 `K_1M`、`K_3M`、`K_5M`、`K_10M`、`K_15M`、`K_30M`、`K_60M`、`K_120M`、`K_180M`、`K_240M`、`K_DAY` 和 `K_WEEK`。

- OpenD 只需要读取策略声明的最细周期，Web 会自动选择该周期作为驱动周期。
- 更粗周期由已到达的驱动 K 线增量聚合；当前未完成 K 线只包含历史时点已经发生的数据。
- `select=1` 表示当前周期 K 线，`select=2` 表示上一根 K 线。不会用目标周期最终收盘价填充尚未结束的 K 线。
- 不能由较粗数据反推较细数据；选择错误时会在创建任务前明确阻止。
- 同一次美股回测必须统一使用一个 `THType`，Web 会按策略声明自动选择 `RTH`、`ETH` 或 `ALL`。

## 已实现的股票环境

### 生命周期与基础环境

- `StrategyBase`、`initialize()`、`handle_data()`
- `declare_strategy_type()`、`declare_trig_symbol()`、`show_variable()`
- `device_time()`、`is_the_time()`、`is_the_day()`、`is_the_week()`、`is_the_month()`、`is_the_year()`
- `APIException` / `ErrCode`；参数错误和点时数据缺失可按手册错误码捕获
- 手册中的股票相关枚举、数学辅助函数与标准 Python 策略写法
- `quit_strategy()`、`alert()`、`add_to_watchlist()`；回测中写入运行日志，不发送外部消息

### 股票行情

- `current_price()`、`bar_open()`、`bar_high()`、`bar_low()`、`bar_close()`、`bar_volume()`、`bar_custom()`
- `amplitude()`、`bar_chg()`、`bar_chg_rate()`、`bar_turnover()`、`bar_turnover_rate()`、`volume_ratio()`
- `get_symbol_name()`、`get_symbol_code()`、`get_symbol_market()`、`get_symbol_type()`、`get_symbol_currency()`
- `lot_size()`、`min_tick()`、`is_suspended()`、`market_status()`、`USmarket_status()`
- `bid()`、`ask()`、`bid_qty()`、`ask_qty()`、`bid_order_qty()`、`ask_order_qty()`、`rate_ratio()`、`mid_price()`

历史 K 线不包含逐档盘口。盘口函数采用确定性的回测报价模型：当前收盘价为中间价，买卖价按最小价差展开，数量使用当前 K 线成交量。结果属于撮合假设，不是历史 Level 2 重放。

### 技术指标

- MA、EMA 及多头/空头排列
- SAR 及趋势/反转判断
- ATR、历史波动率、MACD、KDJ、RSI、VWAP、BOLL、神奇九转
- MACD、KDJ、RSI 的交叉和背离接口
- `register_indicator()` / `get_MyLang_indicator()`：支持常用向量运算、MA、EMA、SMA、REF、SUM、HHV、LLV、STD、ABS、MAX、MIN、IF、CROSS
- `register_indicator_Python()` / `get_Python_indicator()`：支持手册的 `close().sma()`、输入参数和 `output_parameter()` 运行模型

自定义指标解释器不执行磁盘、网络或第三方包访问。使用解释器未覆盖的麦语言语法时会给出具体表达式错误，不会伪造指标值。

### 股票订单与撮合

- 限价、市价、止损限价、止损市价、触及限价、触及市价、跟踪止损限价和跟踪止损市价
- `modify_order()`、按订单/标的/全部撤单、`liquidate()`、`cancel_and_liquidate()`、`close_positions()`、`reverse_positions()`
- 数量按 OpenD `lot_size` 自动下舍入；美股默认一股，A 股默认一百股，港股从 OpenD 读取
- `handle_data()` 在当前驱动 K 线收盘后执行；新订单最早在下一根驱动 K 线成交
- 市价单使用下一根开盘价和滑点；条件单使用下一根 OHLC 区间；手续费、最低佣金和滑点进入现金、盈亏与净值
- OHLC 与订单价比较允许 `1e-8` 的序列化噪声，避免前复权小数尾差导致本应触价的条件单漏成交
- `DAY` 订单按交易日失效，`GTC` 保留；待成交买单冻结现金，待成交卖单冻结可卖持仓
- 默认只做多；启用 `allow_short` 后支持 `SELL_SHORT` / `BUY_BACK`
- 当前采用整笔成交模型，不模拟部分成交、队列位置、涨跌停、历史逐笔流动性和成交量上限

### 账户、持仓、订单与成交查询

- 资产净值、现金、可用/冻结资金、证券/长仓/短仓市值、已实现/未实现盈亏与购买力
- 持仓方向、数量、成本、盈亏、可用数量、当日成交量与成交额
- 最大现金可买、保证金可买、持仓可卖、空仓可回补和可卖空数量
- `request_orderid()` 及全部订单字段查询
- `request_executionid()` 及全部成交字段查询
- 股票融资融券能力、保证金比例、风险状态和沽空池查询

账户是单标的、单资金池模拟账户。`currency` 参数保留手册签名，但不会自动引入历史外汇转换；初始资金和所有结果使用同一个账户记账单位。

## 明确排除

- 期货、期权、窝轮、牛熊证、界内证及相关筛选、希腊值、转仓和合约保证金接口
- 多标的组合和跨品种订单
- Tick、每 N 秒和定时实时触发；历史回测由 K 线驱动
- 实时消息推送、真实自选列表写入和真实落盘
- 历史 Level 2、部分成交、订单队列、交易所涨跌停与流动性重放
- 拆股、分红、精确交易日历和历史外汇换算；应在输入数据或后续专用数据层处理

任何不在股票契约内的名称会在任务创建前被兼容性预检阻止。需要额外点时数据但 OpenD 输入缺失的接口会抛出 `DataUnavailableError`，不会返回看似合理的假值。
