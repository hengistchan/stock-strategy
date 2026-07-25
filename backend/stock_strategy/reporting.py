from __future__ import annotations

import csv
import json
from dataclasses import asdict, fields
from datetime import datetime
from html import escape
from pathlib import Path

from .models import (
    BacktestArtifacts,
    BacktestResult,
    DailyReturn,
    EquityPoint,
    Fill,
    LogEntry,
    Order,
    Trade,
)


def write_artifacts(
    result: BacktestResult,
    base_dir: str | Path = "runs",
    *,
    create_chart: bool = True,
) -> BacktestArtifacts:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(base_dir).resolve() / f"{timestamp}-{result.strategy_name}"
    output_dir.mkdir(parents=True, exist_ok=False)

    summary_path = output_dir / "summary.json"
    orders_path = output_dir / "orders.csv"
    fills_path = output_dir / "fills.csv"
    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity_curve.csv"
    daily_returns_path = output_dir / "daily_returns.csv"
    logs_path = output_dir / "logs.csv"
    logs_jsonl_path = output_dir / "logs.jsonl"
    html_path = output_dir / "report.html"
    chart_path = output_dir / "report.svg" if create_chart else None

    summary = {
        "strategy": result.strategy_name,
        "symbol": result.symbol,
        "period": {"start": result.start_date, "end": result.end_date, "bars": result.bar_count},
        "settings": result.settings,
        "metrics": result.metrics.to_dict(),
        "artifacts": {
            "orders": orders_path.name,
            "fills": fills_path.name,
            "trades": trades_path.name,
            "equity_curve": equity_path.name,
            "daily_returns": daily_returns_path.name,
            "logs": logs_path.name,
            "logs_jsonl": logs_jsonl_path.name,
            "html": html_path.name,
            "chart": chart_path.name if chart_path else None,
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(orders_path, result.orders, Order)
    _write_csv(fills_path, result.fills, Fill)
    _write_csv(trades_path, result.trades, Trade)
    _write_csv(equity_path, result.equity_curve, EquityPoint)
    _write_csv(daily_returns_path, result.daily_returns, DailyReturn)
    _write_csv(logs_path, result.logs, LogEntry)
    logs_jsonl_path.write_text(
        "".join(
            json.dumps(asdict(log), ensure_ascii=False) + "\n"
            for log in result.logs
        ),
        encoding="utf-8",
    )
    if chart_path:
        _write_chart(result, chart_path)
    _write_report_html(result, html_path, chart_path)

    artifacts = BacktestArtifacts(
        output_dir=str(output_dir),
        summary_path=str(summary_path),
        orders_path=str(orders_path),
        fills_path=str(fills_path),
        trades_path=str(trades_path),
        equity_path=str(equity_path),
        daily_returns_path=str(daily_returns_path),
        logs_path=str(logs_path),
        logs_jsonl_path=str(logs_jsonl_path),
        html_path=str(html_path),
        chart_path=str(chart_path) if chart_path else None,
    )
    result.artifacts = artifacts
    return artifacts


def print_summary(result: BacktestResult) -> None:
    metrics = result.metrics
    profit_factor = "∞" if metrics.profit_factor is None else f"{metrics.profit_factor:.2f}"
    annualized_return = (
        "N/A"
        if metrics.annualized_return_pct is None
        else f"{metrics.annualized_return_pct:+.2f}%"
    )
    rows = [
        ("策略", result.strategy_name),
        ("标的 / 区间", f"{result.symbol} · {result.start_date} → {result.end_date}"),
        ("期末权益", f"{metrics.final_equity:,.2f}"),
        ("策略收益", f"{metrics.total_return_pct:+.2f}%"),
        ("买入持有", f"{metrics.benchmark_return_pct:+.2f}%"),
        ("年化收益", annualized_return),
        ("最大回撤", f"{metrics.max_drawdown_pct:.2f}%"),
        ("Sharpe", f"{metrics.sharpe_ratio:.2f}"),
        ("胜率 / 交易", f"{metrics.win_rate_pct:.1f}% / {metrics.total_trades}"),
        ("Profit factor", profit_factor),
        ("资金使用率", f"{metrics.exposure_pct:.1f}%"),
        ("总费用", f"{metrics.total_fees:,.2f}"),
    ]
    width = max(len(label) for label, _ in rows)
    print("\nBACKTEST RESULT")
    print("─" * 54)
    for label, value in rows:
        print(f"{label:<{width}}  {value}")
    print("─" * 54)
    if result.artifacts:
        print(f"报告目录  {result.artifacts.output_dir}")


def _write_csv(path: Path, rows: list[object], model: type[object]) -> None:
    fieldnames = [field.name for field in fields(model)]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_chart(result: BacktestResult, path: Path) -> None:
    width, height = 1200, 840
    left, right = 92, 34
    chart_width = width - left - right
    equity_top, equity_bottom = 112, 460
    drawdown_top, drawdown_bottom = 505, 635
    trade_top, trade_bottom = 686, 792
    equity = [point.equity for point in result.equity_curve]
    benchmark = [point.benchmark for point in result.equity_curve]
    drawdown = [point.drawdown * 100 for point in result.equity_curve]
    combined = equity + benchmark
    equity_min, equity_max = min(combined), max(combined)
    equity_padding = max((equity_max - equity_min) * 0.08, 1)
    equity_min -= equity_padding
    equity_max += equity_padding

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;fill:#233941}.label{font-size:12px;fill:#61747b}.title{font-size:22px;font-weight:700}.metric{font-size:13px;font-weight:600}.grid{stroke:#ced8d9;stroke-width:1}.axis{stroke:#829398;stroke-width:1}</style>",
        f'<rect width="{width}" height="{height}" fill="#eef2f2"/>',
        f'<rect x="{left}" y="{equity_top}" width="{chart_width}" height="{equity_bottom-equity_top}" fill="#f9fbfa"/>',
        f'<rect x="{left}" y="{drawdown_top}" width="{chart_width}" height="{drawdown_bottom-drawdown_top}" fill="#f9fbfa"/>',
        f'<rect x="{left}" y="{trade_top}" width="{chart_width}" height="{trade_bottom-trade_top}" fill="#f9fbfa"/>',
        f'<text x="{left}" y="42" class="title">{escape(result.strategy_name)} · {escape(result.symbol)}</text>',
        f'<text x="{left}" y="70" class="metric">Return {result.metrics.total_return_pct:+.2f}%</text>',
        f'<text x="{left+160}" y="70" class="metric">Benchmark {result.metrics.benchmark_return_pct:+.2f}%</text>',
        f'<text x="{left+350}" y="70" class="metric">Max DD {result.metrics.max_drawdown_pct:.2f}%</text>',
        f'<text x="{left+515}" y="70" class="metric">Sharpe {result.metrics.sharpe_ratio:.2f}</text>',
        f'<text x="{left+635}" y="70" class="metric">Trades {result.metrics.total_trades}</text>',
    ]

    for step in range(5):
        ratio = step / 4
        y = equity_bottom - ratio * (equity_bottom - equity_top)
        value = equity_min + ratio * (equity_max - equity_min)
        lines.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="grid"/>')
        lines.append(f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" class="label">{value:,.0f}</text>')

    equity_points = _points(equity, left, width - right, equity_top, equity_bottom, equity_min, equity_max)
    benchmark_points = _points(benchmark, left, width - right, equity_top, equity_bottom, equity_min, equity_max)
    lines.extend(
        [
            f'<polyline points="{equity_points}" fill="none" stroke="#1e6584" stroke-width="3"/>',
            f'<polyline points="{benchmark_points}" fill="none" stroke="#f06a3b" stroke-width="2" opacity="0.9"/>',
            f'<line x1="{width-296}" y1="95" x2="{width-267}" y2="95" stroke="#1e6584" stroke-width="3"/><text x="{width-258}" y="99" class="label">Strategy</text>',
            f'<line x1="{width-170}" y1="95" x2="{width-141}" y2="95" stroke="#f06a3b" stroke-width="2"/><text x="{width-132}" y="99" class="label">Buy &amp; hold</text>',
            f'<text x="{left-12}" y="{drawdown_top+4}" text-anchor="end" class="label">0%</text>',
            f'<text x="{left-12}" y="{drawdown_bottom+4}" text-anchor="end" class="label">{min(drawdown):.1f}%</text>',
            f'<line x1="{left}" y1="{drawdown_top}" x2="{width-right}" y2="{drawdown_top}" class="grid"/>',
        ]
    )
    drawdown_min = min(min(drawdown), -0.01)
    drawdown_points = _points(drawdown, left, width - right, drawdown_top, drawdown_bottom, drawdown_min, 0)
    lines.append(
        f'<polygon points="{left},{drawdown_top} {drawdown_points} {width-right},{drawdown_top}" fill="#b54c3c" opacity="0.72"/>'
    )
    lines.append(f'<text x="{left}" y="{drawdown_top-12}" class="metric">Drawdown</text>')

    tick_count = min(6, len(result.equity_curve))
    for tick in range(tick_count):
        index = round(tick * (len(result.equity_curve) - 1) / max(tick_count - 1, 1))
        x = left + index / max(len(result.equity_curve) - 1, 1) * chart_width
        label = result.equity_curve[index].date[:7]
        lines.append(f'<text x="{x:.1f}" y="{drawdown_bottom+22}" text-anchor="middle" class="label">{label}</text>')

    lines.append(f'<text x="{left}" y="{trade_top-12}" class="metric">Closed trade net P&amp;L</text>')
    pnl = [trade.net_pnl for trade in result.trades]
    if pnl:
        max_abs = max(max(abs(value) for value in pnl), 1)
        zero_y = (trade_top + trade_bottom) / 2
        bar_slot = chart_width / len(pnl)
        bar_width = max(2, min(24, bar_slot * 0.7))
        lines.append(f'<line x1="{left}" y1="{zero_y}" x2="{width-right}" y2="{zero_y}" class="axis"/>')
        for index, value in enumerate(pnl):
            x = left + index * bar_slot + (bar_slot - bar_width) / 2
            bar_height = abs(value) / max_abs * ((trade_bottom - trade_top) / 2 - 5)
            y = zero_y - bar_height if value >= 0 else zero_y
            color = "#23846b" if value >= 0 else "#b54c3c"
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{color}"/>')
    else:
        lines.append(f'<text x="{width/2}" y="{(trade_top+trade_bottom)/2}" text-anchor="middle" class="label">No closed trades</text>')

    lines.extend(
        [
            f'<text x="{width-right}" y="825" text-anchor="end" class="label">Next-bar execution · costs included · research use only</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_report_html(
    result: BacktestResult,
    path: Path,
    chart_path: Path | None,
) -> None:
    metrics = result.metrics
    chart = (
        f'<img src="{escape(chart_path.name)}" alt="Backtest equity, drawdown and trade P&amp;L chart">'
        if chart_path
        else "<p>Static chart was disabled for this run.</p>"
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(result.strategy_name)} · {escape(result.symbol)}</title>
  <style>
    body{{max-width:1200px;margin:40px auto;padding:0 24px;color:#233941;background:#eef2f2;font-family:system-ui,sans-serif}}
    header{{display:flex;justify-content:space-between;gap:24px;border-bottom:1px solid #233941}}
    dl{{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#ccd7d8}}
    dl div{{padding:14px;background:#f9fbfa}}dt{{color:#61747b;font-size:12px}}dd{{margin:5px 0 0;font-size:22px;font-weight:700}}
    img{{display:block;width:100%;margin-top:24px}}footer{{margin-top:24px;color:#61747b;font-size:12px}}
  </style>
</head>
<body>
  <header><div><h1>{escape(result.strategy_name)}</h1><p>{escape(result.symbol)}</p></div><p>{escape(result.start_date)} → {escape(result.end_date)}</p></header>
  <dl>
    <div><dt>Total return</dt><dd>{metrics.total_return_pct:+.2f}%</dd></div>
    <div><dt>Benchmark</dt><dd>{metrics.benchmark_return_pct:+.2f}%</dd></div>
    <div><dt>Max drawdown</dt><dd>{metrics.max_drawdown_pct:.2f}%</dd></div>
    <div><dt>Sharpe</dt><dd>{metrics.sharpe_ratio:.2f}</dd></div>
  </dl>
  {chart}
  <footer>Next-bar execution · costs included · research use only</footer>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def _points(
    values: list[float],
    left: float,
    right: float,
    top: float,
    bottom: float,
    minimum: float,
    maximum: float,
) -> str:
    width = right - left
    height = bottom - top
    span = maximum - minimum or 1
    denominator = max(len(values) - 1, 1)
    return " ".join(
        f"{left + index / denominator * width:.1f},{bottom - (value - minimum) / span * height:.1f}"
        for index, value in enumerate(values)
    )
