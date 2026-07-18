# MVP 验收标准

本项目把验收分成两个层级，避免把模拟或构造数据的通过误认为真实策略有效。

## A. 自动化工程验收

运行：

```bash
.venv/bin/python backend/scripts/acceptance.py
```

脚本会自动寻找 Python 3.11+，并执行：

1. 全部单元测试通过。
2. 使用 OpenD `request_history_kline()` 同字段结构的数据运行单标的回测。
3. 从 `code` 自动识别标的，完整保留 `time_key`，确认输入格式记录为 `opend`。
4. 使用示例 Futu 风格策略产生至少一笔闭合交易。
5. 生成并校验 `summary.json`、`trades.csv`、`equity_curve.csv`、`report.svg`。
6. 校验汇总交易数与成交文件一致，期末权益与资金曲线一致，SVG 可被解析。

验收报告保存在 `runs/acceptance/<时间>-ma_cross/`。构造行情只验证工程链路，不代表任何真实标的表现。

## B. 真实标的业务验收

正式签收前还必须使用用户指定策略和真实 OpenD 历史数据完成一次回测，并核对：

- 标的、K 线周期、复权方式、开始和结束时间符合预期。
- OpenD 原始行数与导入后的 bar 数一致，或能解释去重差异。
- 策略请求的周期、交易时段和复权口径与 OpenD 输入一致；不一致必须明确失败。
- 策略信号、next-bar 成交、费用、滑点和期末持仓政策符合抽样人工核对。
- 交易数大于零；零交易必须解释原因，不能作为策略验收通过。
- 收益、回撤和基准只作为研究输出，不构成买卖建议。

本机 OpenD 可用时，可以直接运行：

```bash
.venv/bin/python -m stock_strategy \
  --strategy examples/ma_cross.py \
  --opend \
  --symbol US.AAPL \
  --start 2024-01-01 \
  --end 2025-12-31 \
  --ktype K_DAY \
  --autype QFQ \
  --session ALL \
  --opend-cache data/opend/US.AAPL-K_DAY-2024-2025.csv
```

MVP 不验收多标的组合、公司行动自动处理、真实账户下单、部分成交、订单簿、涨跌停和流动性约束。

## C. Web 工作台验收

启动 `.venv/bin/python -m stock_strategy.web` 后，必须验证：

- 服务只绑定 `127.0.0.1`，首页可加载且 OpenD 状态正确。
- 页面只能选择 `examples/` 或 `strategies/` 下的脚本。
- 提交后返回独立作业 ID；回测在子进程中运行，失败原因可见。
- 市场数据命令固定使用 `--opend`，不会退化为模拟数据或网页行情。
- 完成后页面展示的指标、交易数和报告与对应 `summary.json` 一致。
- 新作业包含 `engine_contract.version = 2`；旧作业在页面明确标为 `LEGACY RESULT`。
- 价格图读取该作业的 OpenD 缓存，展示 OHLC、成交量、MA20/MA60 和进出场位置；悬停数值与缓存 CSV 一致。
- 刷新页面后仍能从 `runs/web/` 恢复历史记录。
- 桌面与移动宽度内容可读，键盘焦点可见，减少动态效果设置生效。

## D. 工程化与策略编辑验收

- 前端源码位于 `frontend/`，使用 React、TypeScript 和 Vite；`npm run lint`、`npm run typecheck`、`npm run test`、`npm run build` 全部通过。
- FastAPI 同时提供前端构建产物与 `/api`，Vite 开发服务器只负责开发态代理。
- 页面可以读取示例策略、创建 `strategies/*.py`、编辑并保存用户策略。
- `examples/` 保持只读；路径越界和覆盖示例的请求必须被拒绝。
- 保存前验证 Python 语法和顶层 `Strategy` 类，失败时不改变磁盘文件。
- 保存使用 revision 做乐观并发控制；旧 revision 返回冲突，不静默覆盖。
- GitHub Actions 同时运行 Python 验收与前端 lint/typecheck/test/build。
- 仓库包含 MIT License、贡献指南、安全说明、Dockerfile 和架构文档。
