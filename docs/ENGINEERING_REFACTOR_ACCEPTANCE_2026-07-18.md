# 工程化重构验收记录（2026-07-18）

> 后续兼容性审计说明：本页记录产生于 `engine_contract v2` 之前。下述 `K_5M / HFQ / 312` 笔结果使用了声明 `K_DAY` 的示例均线策略，旧引擎未校验周期与复权口径，因此只能作为 OpenD 读取和图表链路证据，不能作为策略回测证据。Web 现在会把此类历史任务标记为 `LEGACY RESULT`。

## 结论

本次重构通过 MVP 工程验收。项目现由 React + TypeScript + Vite 前端和 Python + FastAPI 后端组成，保留 OpenD 历史行情回测能力，并完成策略新建、编辑、校验、保存和回测选择的闭环。

Python 项目配置、源码、测试和验收脚本统一位于 `backend/`；仓库第一层保留前端、策略工作区、文档和跨端工程配置。

## 自动化验证

| 检查项 | 结果 |
| --- | --- |
| Python 单元与 API 测试 | 25 passed |
| Frontend ESLint | passed |
| Frontend TypeScript | passed |
| Frontend Vitest | 5 passed |
| Vite production build | passed |
| OpenD 同字段结构端到端验收 | passed，300 bars，1 closed trade |
| Production npm audit | 0 vulnerabilities |
| Docker Compose 配置解析 | passed |
| Docker 镜像构建 | 未执行：本机 Docker/OrbStack daemon 未运行 |

## 浏览器验收

在 FastAPI 提供的 production build 上完成以下检查：

- 桌面宽度 `1440 × 1000`：页面、OpenD 状态、价格图和策略编辑器正常，无控制台错误、Vite overlay 或水平溢出。
- 移动宽度 `390 × 844`：回测工作台和策略编辑器水平溢出均为 0；长策略路径可以安全换行。
- 通过页面创建临时策略，修改 CodeMirror 内容，保存后显示 Python 语法校验成功；刷新页面并重新选择策略后，磁盘内容保持一致。
- 临时验收策略在测试完成后已删除，没有写入项目交付内容。

## 真实 OpenD 结果回读

页面成功恢复并绘制已有真实 OpenD 作业：

- 标的：`US.AAPL`
- 周期与复权：`K_5M` / `HFQ`
- 区间：`2023-01-03 09:35:00` 至 `2025-12-31 16:00:00`
- OpenD 页数：59
- K 线：58,368
- 闭合交易：312
- 图表：OHLC、成交量、MA20、MA60、进出场位置及悬停读数均正常显示

这项结果只证明真实 OpenD 数据读取和前端展示链路可用，不代表策略具有投资有效性。

## 安全边界

- `examples/*.py` 只读，只有 `strategies/*.py` 可以通过 API 写入。
- 保存前执行 Python AST 与顶层 `Strategy` 类检查，revision 冲突返回 409，写入使用原子替换。
- 回测使用独立 Python 子进程和超时，但策略代码不是安全沙箱。
- Web 默认只监听 `127.0.0.1`；在增加身份认证、隔离执行和多租户权限前，不应直接暴露到公网。
