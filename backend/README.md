# Strategy Lab backend

Python 后端包含 FastAPI 服务、Futu/OpenD 数据适配、回测运行时、测试与验收脚本。仓库根目录的 `examples/`、`strategies/`、`data/` 和 `runs/` 是工作区数据，不属于后端源码。

从仓库根目录安装并验证：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e './backend[opend,web,test]'
.venv/bin/python -m stock_strategy.doctor
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python backend/scripts/acceptance.py
```

启动 API 与生产前端前，需要先构建 React 静态资源。推荐直接在仓库根目录运行：

```bash
make serve
```

等价的手动命令如下：

```bash
cd frontend && npm ci && npm run build
cd ..
.venv/bin/python -m stock_strategy.web
```

如果只安装 Python 后端而未执行前端构建，API 仍可启动，但首页会返回 `503` 并提示构建前端。

生产服务会为 `/backtests`、`/experiments` 和 `/strategies` 返回同一份 SPA 入口，使各工作区可以直接访问和刷新；未知 `/api/*` 路径仍返回 JSON `404`，不会误返回前端 HTML。

服务默认只接受 loopback 连接。绑定 `0.0.0.0` 必须显式增加 `--allow-remote`，并设置至少 32 字符的 `STRATEGY_LAB_API_TOKEN`；远程浏览器首次通过 `#access_token=<token>` 注入会话令牌。该机制不是公网部署或多租户沙箱。

`GET /api/symbols?q=腾讯&limit=8` 会从 OpenD `get_stock_basicinfo()` 读取美股和港股股票代码及名称，并在五分钟缓存内完成后续模糊查询；`GET /api/symbols/resolve?codes=US.AAPL` 用于批量补齐已有回测记录的名称。这些接口只读，不访问交易账户。

`GET /api/diagnostics` 与 `stock-doctor` 共用 `DiagnosticsService`，检查 Python、Futu SDK、工作区目录、OpenD TCP 和股票目录读取权限。Web 状态面板只展示这份真实结果，不自行推断行情权限。

新建 Web 回测时，`JobStore` 会先冻结 `strategy.py`、`request.json` 和 `manifest.json`，执行命令只读取任务内的策略快照。OpenD 数据完成后会复制为任务内的 `market-data.csv` 并校验 SHA-256；共享缓存被清理或原始策略被修改都不会改变既有结果。旧版任务缺少快照字段时仍可按原路径读取。

作业与实验元数据的权威状态保存在 WAL 模式的 `runs/state.sqlite3`。启动时会自动导入已有的 `runs/web/*/job.json` 和 `runs/experiments/*/experiment.json`；实验候选、阶段与 job 关系使用外键表，后续更新仍写出 JSON 兼容镜像，因此旧工作区和外部脚本无需一次性迁移。

`DELETE /api/jobs/{job_id}` 取消 queued/running 作业；`POST /api/jobs/{job_id}/retry` 只接受 failed/cancelled 作业，并从不可变策略快照创建带 `retry_of` 的新任务，不覆盖原结果。

`warmup_bars` 只建立策略历史，不属于回测评估区间。收益、基准、回撤和资金使用率从第一根 evaluation K 线开始计算；Sharpe 统一使用每日收盘权益收益，少于 20 个交易日的结果将 `annualized_return_pct` 记录为 `null`。完整输入/评估边界位于 `summary.settings.data_window`。

费用和滑点通过 `FeeModel` / `SlippageModel` 接口注入 Broker。默认模型继续解释现有的 bps 与最低佣金字段，并将模型名称和参数写入 `summary.settings.execution_models`，以便复核成交假设。

成功运行必须生成 `orders.csv`、`fills.csv`、`trades.csv`、`equity_curve.csv`、`daily_returns.csv`、`logs.csv`、`logs.jsonl`、`report.html` 和 `report.svg`。Web 作业在发布结果前校验这些文件，并将相对路径、字节数和 SHA-256 写入 `manifest.json`。

后端工程门禁：

```bash
make quality
```

该命令执行 Ruff lint/format、mypy、74% branch coverage、Bandit 与 pip-audit；GitHub Actions 同时在 Python 3.11 和 3.12 运行完整 fixture 验收。

构建包含当前 React 生产资源的 wheel，并检查不存在陈旧哈希文件：

```bash
make package
```
