# Strategy Lab · OpenD 量化策略工作台

一个本机优先、面向开源协作的 Futu OpenD 量化策略创建与回测项目。你可以在 React 工作台中创建、编辑和保存 Python 策略，直接读取 OpenD 历史行情进行回测，并检查价格、成交位置、资金曲线、回撤、费用和逐笔交易。

项目不会读取交易账户，也不会发送真实订单。

## 功能

- React + TypeScript + Vite 工程化前端，支持响应式回测工作台。
- 简体中文 / English 双语界面，自动检测浏览器语言、持久化选择，并本地化日期和数字。
- CodeMirror Python 策略编辑器，支持新建、复制示例、语法校验和保存。
- 声明式策略参数、单次参数覆盖、批量参数矩阵、目标指标排名和三组结果并排比较。
- 回测档案按“标的 → 策略 → 回测批次”分层浏览，新建配置与历史结果互不堆叠。
- Python + FastAPI API，策略在独立子进程中运行并设置超时。
- OpenD `request_history_kline()` 直连、分页、确定性共享缓存、缓存清理和分钟级时间戳。
- OHLC 蜡烛图、成交量、MA20/MA60、策略进出场标记和悬停价格。
- 回测指标、基准、回撤、成交账簿和可复查的 JSON/CSV/SVG 产物。
- Python/React 自动化测试、GitHub Actions、Dependabot、Docker 和 MIT License。

## 快速开始

要求 Python 3.11+、Node.js 22+、npm 11+，并确保 OpenD 正在监听 `127.0.0.1:11111`。

```bash
make install
make serve
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。`make serve` 会先构建 React，再由 FastAPI 提供前端和 API。

右上角的 `文/A` 可随时切换简体中文和 English。选择保存在浏览器本地；翻译资源和新增语言说明见 [docs/I18N.md](docs/I18N.md)。策略脚本定义的参数标签、说明以及后端返回的原始错误会保持作者原文。

## CLI 回测

不启动 Web 也可以直接运行回测：

```bash
.venv/bin/python -m stock_strategy \
  --strategy examples/ma_cross.py \
  --sample
```

`--sample` 使用确定性的模拟行情，只用来验证完整流程。使用自己的数据：

```bash
.venv/bin/python -m stock_strategy \
  --strategy strategies/my_strategy.py \
  --data data/US.AAPL-day.csv \
  --symbol US.AAPL \
  --initial-cash 100000 \
  --commission-bps 3 \
  --slippage-bps 5
```

如果 CSV 来自 OpenD，`--symbol` 会从 `code` 自动识别；只有文件包含多只标的时才需要显式指定。

## OpenD 输出格式

OpenD `request_history_kline()` 成功时返回 `pd.DataFrame`。可以直接保存，不需要修改列名：

字段定义以 [Futu OpenD 官方历史 K 线文档](https://openapi.futunn.com/futu-api-doc/quote/request-history-kline.html) 为准。

```python
from futu import OpenQuoteContext, RET_OK

quote_ctx = OpenQuoteContext(host="127.0.0.1", port=11111)
ret, data, page_req_key = quote_ctx.request_history_kline(
    "US.AAPL",
    start="2024-01-01",
    end="2025-12-31",
    max_count=None,
)
if ret == RET_OK:
    data.to_csv("data/US.AAPL-opend.csv", index=False)
else:
    raise RuntimeError(data)
quote_ctx.close()
```

然后运行：

```bash
.venv/bin/python -m stock_strategy \
  --strategy examples/ma_cross.py \
  --data data/US.AAPL-opend.csv
```

也可以从正在运行的 OpenD 直接拉取、缓存并回测。直连功能使用可选依赖，建议安装在项目虚拟环境中：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e './backend[opend]'

.venv/bin/python -m stock_strategy \
  --strategy examples/ma_cross.py \
  --opend \
  --symbol US.AAPL \
  --start 2024-01-01 \
  --end 2025-12-31 \
  --ktype K_DAY \
  --autype QFQ \
  --session ALL \
  --parameter fast_period=10 \
  --parameter slow_period=60 \
  --opend-cache data/opend/US.AAPL-K_DAY-2024-2025.csv
```

直连模式会遍历 OpenD 返回的全部 `page_req_key`，连接始终在成功或失败后关闭。相同缓存文件已存在时会直接复用；传入 `--refresh-opend-cache` 才会重新请求。`--session` 支持 `ALL`、`RTH`、`ETH`，并同时约束 OpenD 历史数据与策略行情接口。它只调用历史行情接口，不读取账户，也不会发送订单。

已适配 OpenD 的 `code`、`time_key`、`open`、`close`、`high`、`low`、`volume` 字段；`name`、`turnover`、`pe_ratio` 等额外字段会安全忽略。也兼容 Pandas 默认写入的索引列。分钟 K 会完整保留 `YYYY-MM-DD HH:MM:SS`，不会按日期去重。

如果已经在 Python 中拿到 DataFrame，也可以直接转换，不依赖 Pandas 类型：

```python
from stock_strategy.data import bars_from_opend_records

market_data = bars_from_opend_records(data.to_dict("records"))
bars = market_data.bars
symbol = market_data.symbol
```

也可以在安装后使用 `stock-backtest` 命令，参数相同。

## CSV 格式

```csv
date,open,high,low,close,volume
2025-01-02,100.0,103.0,99.5,102.5,1200000
2025-01-03,102.7,104.1,101.2,103.6,980000
```

要求：

- 字段名支持英文和常见简体/繁体中文别名；`volume` 可省略。
- 日期支持 `YYYY-MM-DD`；OpenD `time_key` 支持 `YYYY-MM-DD HH:MM:SS`，按完整时间戳排序后去重。
- 至少 30 根 K 线。
- 建议导入已复权、同一时段和同一周期的数据；MVP 不自动处理公司行动。

## 策略脚本

脚本定义一个名为 `Strategy` 的 `StrategyBase` 子类。调用形式与手册保持一致：

```python
from stock_strategy.futu import *

class Strategy(StrategyBase):
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.symbol = declare_trig_symbol()

    def handle_data(self):
        fast = ma(self.symbol, period=20, bar_type=BarType.K_DAY, select=1)
        slow = ma(self.symbol, period=60, bar_type=BarType.K_DAY, select=1)
        if fast > slow and position_side(self.symbol) == PositionSide.NONE:
            place_market(self.symbol, qty=100, side=OrderSide.BUY)
        elif fast < slow and position_side(self.symbol) == PositionSide.LONG:
            close_positions(self.symbol)
```

完整可运行示例见 [examples/ma_cross.py](examples/ma_cross.py)，当前接口与撮合边界见 [docs/FUTU_COMPATIBILITY.md](docs/FUTU_COMPATIBILITY.md)。

### 策略参数与批量实验

策略可在文件顶层声明可调参数。声明必须是字面量字典，后端只通过 AST 读取，不执行策略代码：

```python
STRATEGY_PARAMETERS = {
    "fast_period": {
        "label": "短均线周期",
        "type": "int",
        "default": 20,
        "min": 2,
        "max": 120,
        "candidates": [10, 20, 30],
    },
}

class Strategy(StrategyBase):
    def initialize(self):
        self.fast_period = strategy_parameter("fast_period")
```

Web 的“回测实验”可以覆盖单次参数；“参数实验”会展开候选值笛卡尔积，最多顺序运行 36 组，按收益、Sharpe 或最大回撤排名，并允许固定三组结果并排比较。第一组从 OpenD 获取行情，后续组合复用由标的、区间、周期、复权和时段共同确定的缓存。

这套参数注入是 Strategy Lab 的工程扩展，不冒充 Futu 原生 API。最终使用值和参数定义都会写入 `summary.json`，每个候选仍保留完整独立回测产物。

MVP 一次只加载一种 K 线周期和交易时段。策略传给 `ma()`、`bar_close()` 等 API 的 `BarType` / `THType` 必须与回测输入一致，并且手册行情与指标 API 要求 `QFQ`；不一致时会明确终止回测，不会静默按另一种周期计算。

`warmup_bars` 默认为 `0`，因此默认从第一根 K 线触发策略。只有显式设置为正数时，前 N 根才仅作为指标历史而不执行 `handle_data()`。

## 回测产物

每次运行在 `runs/<时间>-<策略名>/` 下生成：

- `summary.json`：参数、区间和核心指标
- `trades.csv`：逐笔闭合交易、费用、净盈亏和退出原因
- `equity_curve.csv`：策略净值、买入持有基准和回撤
- `report.svg`：资金曲线、回撤与逐笔盈亏图（浏览器或系统预览可直接打开）

回测采用 next-bar execution：当前收盘产生的订单最早在下一根 K 线成交。`DAY` 订单在第一根可执行 K 线所属交易日内有效；挂单会冻结估算现金或可卖持仓。期末默认保留持仓、按末价盯市，并在 `summary.json` 的 `ending_position` 中记录；只有显式传入 `--liquidate-on-end` 才会强制平仓。默认费用为 3 bps、最低 1 元，滑点为 5 bps；这些参数都可通过 CLI 修改。

## 验证

```bash
make test
make acceptance
```

验收脚本会自动寻找 Python 3.11+，运行全部测试，并使用 OpenD 同字段结构的数据完成一次端到端回测；报告保存在 `runs/acceptance/`。详细门槛见 [docs/MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md)。构造数据的通过只代表工程链路正确，真实标的仍需使用真实 OpenD 数据单独验收。

2026-07-15 的真实 OpenD 验收记录见 [docs/ACCEPTANCE_RESULT_2026-07-15.md](docs/ACCEPTANCE_RESULT_2026-07-15.md)；前后端工程化重构记录见 [docs/ENGINEERING_REFACTOR_ACCEPTANCE_2026-07-18.md](docs/ENGINEERING_REFACTOR_ACCEPTANCE_2026-07-18.md)；修正周期、时段、DAY 订单与期末持仓语义后的最新结果见 [Futu 兼容契约 v2 验收](docs/FUTU_CONTRACT_V2_ACCEPTANCE_2026-07-18.md)。

第二阶段参数声明、批量实验、排名对比和共享缓存的真实 OpenD 验收见 [策略迭代能力 v0.3 验收](docs/STRATEGY_ITERATION_ACCEPTANCE_2026-07-18.md)。

这是研究工具，不提供交易建议，也不会向 Futu 或任何券商发送订单。

## 前后端开发

分别启动两个终端：

```bash
make dev-api
make dev-web
```

前端位于 `frontend/`，Python 后端完整收拢在 `backend/`。Vite 将 `/api` 代理到 FastAPI；生产构建输出到 `backend/stock_strategy/web_dist/`，该目录是生成物，不提交到 Git。

Web 持久化目录：

- `runs/web/`：单次回测作业和产物。
- `runs/experiments/`：参数实验定义、进度、排名与候选作业引用。
- `data/opend/cache/`：确定性命名的共享行情 CSV 和元数据；可在参数实验页查看或删除。

策略文件的规则：

- `examples/*.py` 是只读示例。
- `strategies/*.py` 可以通过页面创建和保存，也适合纳入 Git 版本管理。
- 保存前检查 Python AST 和 `Strategy` 类，并使用 revision 防止无提示覆盖其他修改。

## Docker

```bash
docker compose up --build
```

Compose 仍只在宿主机 `127.0.0.1:8000` 暴露页面，并通过 `host.docker.internal:11111` 访问宿主机 OpenD。可以使用 `OPEND_HOST`、`OPEND_PORT` 或 Web 启动参数覆盖连接地址。

## 项目结构

```text
frontend/                         React + TypeScript + Vite
backend/                          Python 后端工程根目录
backend/stock_strategy/           回测引擎与 FastAPI 包源码
backend/tests/                    Python 单元与 API 测试
backend/scripts/                  后端验收脚本
examples/                         只读策略示例
strategies/                       用户策略
docs/                             架构、兼容性和验收记录
.github/                          CI 与依赖更新配置
```

详细边界见 [架构说明](docs/ARCHITECTURE.md)、[Futu 兼容性](docs/FUTU_COMPATIBILITY.md) 和 [MVP 验收门槛](docs/MVP_ACCEPTANCE.md)。

## 开源协作与安全

项目使用 [MIT License](LICENSE)。提交代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)；漏洞请按 [SECURITY.md](SECURITY.md) 私密报告。

当前 Web 服务没有认证、沙箱和多租户隔离，默认只绑定 `127.0.0.1`。策略是可执行 Python 代码，只运行你信任的文件，不要把服务直接暴露到公网。
