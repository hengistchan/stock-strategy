# Strategy Lab backend

Python 后端包含 FastAPI 服务、Futu/OpenD 数据适配、回测运行时、测试与验收脚本。仓库根目录的 `examples/`、`strategies/`、`data/` 和 `runs/` 是工作区数据，不属于后端源码。

从仓库根目录安装并验证：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e './backend[opend,web,test]'
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

构建包含当前 React 生产资源的 wheel，并检查不存在陈旧哈希文件：

```bash
make package
```
