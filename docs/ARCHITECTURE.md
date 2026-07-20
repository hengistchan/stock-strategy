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
  ├── App / React Router ── 页面路由与跨页面选择状态
  ├── BacktestWorkspace ── 回测页面查询与交互
  ├── IterationWorkspace ── 参数实验查询与交互
  ├── StrategyWorkspace ── 策略仓库查询与编辑
  └── api/queryKeys ── 统一服务端缓存键
                  │  /api
                  ▼
FastAPI composition root (backend/stock_strategy/web.py)
  ├── web_models ── HTTP 输入模型与边界校验
  ├── ExecutionService ── 策略兼容性、参数归一化、用例编排
  ├── DiagnosticsService ── CLI / HTTP 共用本机就绪检查
  ├── StrategyRepository ── examples/ (只读)
  │                      └─ strategies/ (可写、原子保存)
  ├── ExperimentStore ── 参数组合 / 排名 ── runs/experiments/
  ├── JobStore ── 作业生命周期 / 串行 Python 子进程
  ├── result_reader ── 大型 CSV 索引、窗口读取、降采样
  └── MarketDataCache ── data/opend/cache/
                       │
                       ▼
              Backtest Runtime ── Futu OpenD history API
                               └─ runs/web/* artifacts
```

## 前端

- React 19、TypeScript、Vite。
- React Router 负责 `/backtests`、`/experiments`、`/strategies` 三个稳定页面入口和浏览器历史记录。
- TanStack Query 管理服务端状态、作业轮询和缓存失效。
- `api/queryKeys.ts` 是查询键的唯一来源，避免跨页面失效规则依赖重复字符串。
- `App.tsx` 只保留应用外壳、共享选择状态与路由装配；回测请求、轮询和结果选择收拢在 `BacktestWorkspace`。
- CodeMirror 6 提供 Python 语法编辑。
- Canvas 绘制 OpenD OHLC、成交量、MA20/MA60 和进出场标记。
- 参数实验工作区展示搜索空间、运行进度、排名、三组结果对比和缓存清单。
- `npm run build` 输出到 `backend/stock_strategy/web_dist/`，由 FastAPI 在单进程生产模式下提供。

## 后端

- Python 项目配置、包源码、测试与验收脚本统一位于 `backend/`；仓库第一层只保留跨端编排和工作区数据。
- `web.py` 是 FastAPI composition root，只负责依赖装配、HTTP 映射和静态资源回退。
- `web_models.py` 定义 HTTP 输入契约；跨字段规则在模型边界校验，日期区间不会进入应用服务后再重复判断。
- `ExecutionService` 是应用服务层，集中处理策略解析、Futu 兼容性、参数默认值与实验搜索空间归一化。
- `DiagnosticsService` 是 `make doctor`、`stock-doctor` 和 `/api/diagnostics` 的唯一诊断来源，统一检查运行时、工作区、OpenD TCP 与股票目录读取权限。
- `JobStore` 只负责作业持久化和子进程生命周期；`result_reader` 负责结果文件读取、行情窗口索引与曲线降采样。
- `StrategyRepository` 只读取 `examples/*.py` 和 `strategies/*.py`；只有后者可以写入。
- `STRATEGY_PARAMETERS` 只通过 `ast.literal_eval` 读取；参数类型、边界、候选值和运行覆盖均在执行前验证。
- 保存前用 `ast.parse` 校验 Python 语法和 `Strategy` 类，使用 revision 做乐观并发控制，并通过临时文件原子替换。
- `JobStore` 将每次回测放到独立 Python 子进程，设置超时，并持久化 `job.json`。
- `ExperimentStore` 将最多 36 个参数组合顺序交给 `JobStore`，失败候选不会中断其余组合，并按选定指标持久化排名。
- `MarketDataCache` 用行情请求的六个维度生成稳定 key；同条件实验只由第一组访问 OpenD。
- 行情命令固定使用 `--opend`；没有网页行情或模拟行情回退。
- `ktype`、`session` 和 `autype` 会贯穿 OpenD 请求、作业记录、执行上下文与结果；Futu 行情/指标接口对不一致输入 fail-fast。
- `engine_contract` 为回测语义提供版本边界；缺少版本的历史结果只作为 legacy 工程证据展示。

## 依赖方向

依赖由外向内保持单向：HTTP 路由依赖应用服务，应用服务依赖仓库和作业接口，作业层依赖回测 CLI 与文件产物。回测运行时不反向依赖 FastAPI 或 React。`ExperimentStore` 通过 `JobStoreProtocol` 使用作业能力，避免绑定具体 Web 实现。

`web.py` 仍暂时承载全部 REST 路由；当 API 继续扩展到删除作业、组合管理或实时交易时，应按 `diagnostics / symbols / strategies / backtests / experiments / cache` 拆分 `APIRouter`，而不是再次向 composition root 堆叠业务校验。

## 信任模型

策略文件是可执行 Python 代码，不是安全沙箱。编辑 API 只防止目录越界和意外覆盖，不防止恶意策略代码。服务默认绑定本机，不能直接作为多用户公网服务。
