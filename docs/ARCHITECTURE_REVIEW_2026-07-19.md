# Architecture review — 2026-07-19

## 结论

当前项目已经形成清晰的本机量化工作台边界：React 负责交互，FastAPI 负责本地 API，Python 回测运行时负责 Futu/OpenD 兼容与撮合。核心问题不是技术选型，而是 Web 总控模块持续吸收业务职责。本轮已优先处理这类结构性耦合，现有 HTTP、策略脚本和回测产物契约保持不变。

## 本轮已解决

| 优先级 | 原问题 | 调整结果 |
| --- | --- | --- |
| P0 | `web.py` 同时包含 HTTP 模型、作业执行、CSV 投影和业务校验，接近 1,000 行 | 拆为 `web_models`、`ExecutionService`、`JobStore`、`result_reader`；`web.py` 降为依赖装配和路由映射 |
| P0 | 回测和参数实验分别实现策略兼容性及参数归一化，规则可能漂移 | 统一进入 `ExecutionService.prepare_backtest` |
| P1 | 日期区间在不同路由重复校验 | 移到 `BacktestRequest` 的跨字段模型校验 |
| P1 | `ExperimentStore` 通过 `Any` 依赖作业层 | 改为最小 `JobStoreProtocol` |
| P1 | `App.tsx` 同时承担路由解析与回测作业生命周期 | 使用声明式 `Routes`；回测服务器状态下沉到 `BacktestWorkspace` |
| P1 | TanStack Query 键散落为字符串数组 | 统一到 `api/queryKeys.ts` |
| P2 | 多个页面重复实现通知自动消失逻辑 | 抽取 `useTransientNotice` |

## 保留的架构决策

- JSON 文件存储、单机串行作业和本地绑定符合当前 MVP 与 OpenD 本机运行方式，不引入数据库或消息队列。
- 策略脚本仍是受信任的本地 Python 代码；当前不是多租户安全沙箱。
- 行情和结果采用文件索引、窗口读取及降采样，避免分钟级长周期数据一次性进入 API 和浏览器内存。
- Futu 模拟层与 Web API 保持分离，策略运行时不依赖 FastAPI。

## 后续演进触发条件

1. REST 端点继续增加时，将 `web.py` 按资源拆成 `APIRouter`；当前 350 行仍可维护，不提前制造过多文件。
2. 需要多进程或远程部署时，将 `JobStore` 的任务调度替换为持久队列；JSON 作业格式可以继续作为领域记录。
3. 前后端字段开始频繁漂移时，从 FastAPI OpenAPI 生成 TypeScript 类型，替代手写响应接口。
4. 策略来源不再完全可信时，必须增加独立用户、资源配额和操作系统级沙箱；不能只依赖 AST 校验。
5. 样式继续增长或新增多个产品页面时，再将全局 CSS 拆成页面级样式与设计令牌模块。

## 验证基线

- 后端全量单元/集成测试：71 项。
- 前端测试：33 项。
- TypeScript、ESLint、Vite production build 均通过。
- 仍需在每次 production build 后用真实浏览器验证三条页面深链和 OpenD 在线/离线状态。
