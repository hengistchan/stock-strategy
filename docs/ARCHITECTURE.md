# Architecture

## 目标

Strategy Lab 是本机优先、面向开源协作的 OpenD 量化策略工作台。核心边界是：OpenD 提供历史行情，Python 运行策略与撮合，React 提供策略迭代和结果检查界面。

```text
frontend/                 React 工程
backend/
├── pyproject.toml        Python 项目配置
├── stock_strategy/       API、OpenD 适配与回测引擎
├── tests/                后端测试
└── scripts/              后端验收脚本
examples/                 只读策略工作区
strategies/               用户策略工作区
data/ · runs/             行情缓存与回测产物
```

```text
React + TypeScript (frontend/)
        │  /api
        ▼
FastAPI (backend/stock_strategy/web.py)
   ├── StrategyRepository ── examples/ (只读)
   │                      └─ strategies/ (可写、原子保存)
   └── JobStore ── Python 子进程 ── Backtest Runtime
                                  │
                                  ├─ Futu OpenD history API
                                  ├─ data/opend/web/*.csv
                                  └─ runs/web/* artifacts
```

## 前端

- React 19、TypeScript、Vite。
- TanStack Query 管理服务端状态、作业轮询和缓存失效。
- CodeMirror 6 提供 Python 语法编辑。
- Canvas 绘制 OpenD OHLC、成交量、MA20/MA60 和进出场标记。
- `npm run build` 输出到 `backend/stock_strategy/web_dist/`，由 FastAPI 在单进程生产模式下提供。

## 后端

- Python 项目配置、包源码、测试与验收脚本统一位于 `backend/`；仓库第一层只保留跨端编排和工作区数据。
- FastAPI 提供健康检查、配置、策略仓库、异步回测作业和结果 API。
- `StrategyRepository` 只读取 `examples/*.py` 和 `strategies/*.py`；只有后者可以写入。
- 保存前用 `ast.parse` 校验 Python 语法和 `Strategy` 类，使用 revision 做乐观并发控制，并通过临时文件原子替换。
- `JobStore` 将每次回测放到独立 Python 子进程，设置超时，并持久化 `job.json`。
- 行情命令固定使用 `--opend`；没有网页行情或模拟行情回退。
- `ktype`、`session` 和 `autype` 会贯穿 OpenD 请求、作业记录、执行上下文与结果；Futu 行情/指标接口对不一致输入 fail-fast。
- `engine_contract` 为回测语义提供版本边界；缺少版本的历史结果只作为 legacy 工程证据展示。

## 信任模型

策略文件是可执行 Python 代码，不是安全沙箱。编辑 API 只防止目录越界和意外覆盖，不防止恶意策略代码。服务默认绑定本机，不能直接作为多用户公网服务。
