# Contributing

感谢你参与 Strategy Lab。项目接受问题报告、文档修正、OpenD 格式兼容、回测引擎测试和前端工作台改进。

参与项目即表示你同意遵守 [Code of Conduct](CODE_OF_CONDUCT.md)。涉及漏洞或敏感信息时，请按 [SECURITY.md](SECURITY.md) 私密报告，不要创建公开 Issue。

## 本地开发

要求 Python 3.11+、Node.js 22+、npm 11+。首次安装：

```bash
make install
```

开发时分别启动两个终端：

```bash
make dev-api
make dev-web
```

Vite 运行在 `127.0.0.1:5173`，并将 `/api` 代理到 FastAPI `127.0.0.1:8000`。

## 提交前检查

```bash
make test
make acceptance
```

- Python 改动需要覆盖 `backend/tests/` 中的 `unittest`。
- React 组件改动需要通过 ESLint、TypeScript 和 Vitest。
- 关键工作台流程改动需要通过 `cd frontend && npm run test:e2e`；首次运行前执行 `npx playwright install chromium`。
- OpenD 相关改动不得添加网页行情或静默模拟数据回退。
- 策略保存能力必须继续限制在 `strategies/`，示例目录保持只读。

## Pull Request

PR 请说明问题、实现边界、验证命令和仍未验证的外部条件。一个 PR 尽量只解决一个清晰问题；不要提交 `runs/`、OpenD 缓存、虚拟环境、`node_modules/` 或前端构建产物。
