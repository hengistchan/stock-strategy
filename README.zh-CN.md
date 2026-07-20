# Strategy Lab

**一个本机优先、基于 Futu OpenD 的股票策略编辑、参数实验与量化回测工作台。**

[English](README.md) · [架构说明](docs/ARCHITECTURE.md) · [Futu 兼容性](docs/FUTU_COMPATIBILITY.md)

[![CI](https://github.com/hengistchan/stock-strategy/actions/workflows/ci.yml/badge.svg)](https://github.com/hengistchan/stock-strategy/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![Strategy Lab 回测工作台](docs/assets/strategy-lab-workbench.jpg)

Strategy Lab 直接连接本机 OpenD，以独立 Python 子进程运行股票策略，并通过 JSON、CSV 和 SVG 产物保留可复查的回测结果。项目不会读取交易账户，也不会发送真实订单。

## 核心能力

| | 能力 | 说明 |
| --- | --- | --- |
| 📈 | **股票回测** | 使用 OpenD OHLCV 行情，计算费用、滑点、回撤和逐笔交易结果。 |
| 🧪 | **参数实验** | 复用行情缓存批量比较参数，并按收益、Sharpe 或回撤排序。 |
| ✍️ | **策略编辑** | 在浏览器中创建、编辑、校验、保存和复用 Python 策略。 |
| 🔌 | **OpenD 直连** | 模糊搜索美股和港股，获取名称与分页历史 K 线，不使用网页行情回退。 |

## 快速开始

需要 Python 3.11+、Node.js 22+、npm 11+，以及监听 `127.0.0.1:11111` 的 OpenD。

```bash
git clone https://github.com/hengistchan/stock-strategy.git
cd stock-strategy
make install
make doctor
make serve
```

打开 [http://127.0.0.1:8000/backtests](http://127.0.0.1:8000/backtests)。参数实验和策略管理分别位于 `/experiments` 与 `/strategies`。

无需 OpenD 也可以运行确定性的工程示例：

```bash
.venv/bin/python -m stock_strategy \
  --strategy examples/ma_cross.py \
  --sample
```

## 开发与贡献

```bash
make test
make acceptance
cd frontend && npx playwright install chromium && npm run test:e2e
```

欢迎提交 Issue 和 Pull Request。参与前请阅读 [贡献指南](CONTRIBUTING.md) 与 [行为准则](CODE_OF_CONDUCT.md)，漏洞请按照 [安全策略](SECURITY.md) 私密报告。

Strategy Lab 仅用于研究，不构成投资建议。Web 服务默认只在本机运行，策略文件应视为受信任的可执行 Python 代码。

## License

[MIT](LICENSE)
