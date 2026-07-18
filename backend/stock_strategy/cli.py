from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .data import bars_from_opend_records, generate_sample_bars, load_market_data
from .opend import fetch_history_kline, fetch_stock_metadata, write_history_csv
from .reporting import print_summary, write_artifacts
from .runtime import BacktestConfig, run_backtest
from .strategy_parameters import parse_parameter_assignment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-backtest",
        description="Run a Futu-style Python strategy against OHLCV data.",
    )
    parser.add_argument("--strategy", required=True, help="Path to the Python strategy script")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", help="OHLCV CSV path")
    source.add_argument("--sample", action="store_true", help="Use deterministic synthetic data")
    source.add_argument(
        "--opend",
        action="store_true",
        help="Fetch history from a running Futu OpenD instance",
    )
    parser.add_argument(
        "--symbol",
        help="Futu symbol; inferred from OpenD code when the file contains one symbol",
    )
    parser.add_argument("--initial-cash", type=float, default=100_000)
    parser.add_argument("--commission-bps", type=float, default=3.0)
    parser.add_argument("--min-commission", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument(
        "--warmup-bars",
        type=int,
        default=0,
        help="Skip handle_data for the first N bars (project-specific; default follows Futu lifecycle)",
    )
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--sample-bars", type=int, default=880)
    parser.add_argument("--start", help="OpenD history start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="OpenD history end date (YYYY-MM-DD)")
    parser.add_argument("--ktype", default="K_DAY", help="OpenD KLType value")
    parser.add_argument(
        "--autype",
        choices=("QFQ", "HFQ", "NONE"),
        default="QFQ",
        help="OpenD adjustment type",
    )
    parser.add_argument(
        "--session",
        choices=("ALL", "RTH", "ETH"),
        default="ALL",
        help="OpenD market session used by history and strategy APIs",
    )
    parser.add_argument("--opend-host", default="127.0.0.1")
    parser.add_argument("--opend-port", type=int, default=11111)
    parser.add_argument("--opend-cache", help="Save the raw OpenD response as CSV")
    parser.add_argument(
        "--refresh-opend-cache",
        action="store_true",
        help="Ignore an existing OpenD cache file and fetch the requested history again",
    )
    parser.add_argument(
        "--parameter",
        action="append",
        default=[],
        metavar="NAME=JSON_VALUE",
        help="Override one declared STRATEGY_PARAMETERS value; may be repeated",
    )
    parser.add_argument("--output", default="runs", help="Artifact output directory")
    parser.add_argument("--no-chart", action="store_true", help="Skip report.svg generation")
    parser.add_argument(
        "--liquidate-on-end",
        action="store_true",
        help="Close remaining positions on the final bar (disabled by default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        history = None
        market_metadata = {}
        cache_path = None
        cache_hit = False
        strategy_parameters = {}
        for assignment in args.parameter:
            name, value = parse_parameter_assignment(assignment)
            if name in strategy_parameters:
                raise ValueError(f"strategy parameter {name!r} was supplied more than once")
            strategy_parameters[name] = value
        if args.data:
            market_data = load_market_data(args.data, args.symbol)
            bars = market_data.bars
        elif args.opend:
            if not args.symbol:
                raise ValueError("--symbol is required with --opend")
            if not args.start or not args.end:
                raise ValueError("--start and --end are required with --opend")
            requested_cache = (
                Path(args.opend_cache).expanduser().resolve() if args.opend_cache else None
            )
            if requested_cache and requested_cache.is_file() and not args.refresh_opend_cache:
                cache_path = requested_cache
                market_data = load_market_data(cache_path, args.symbol)
                bars = market_data.bars
                cache_hit = True
            else:
                history = fetch_history_kline(
                    args.symbol,
                    start=args.start,
                    end=args.end,
                    ktype=args.ktype,
                    autype=args.autype.lower(),
                    session=args.session,
                    host=args.opend_host,
                    port=args.opend_port,
                )
                if requested_cache:
                    cache_path = write_history_csv(history, requested_cache)
                market_data = bars_from_opend_records(
                    history.records,
                    symbol=args.symbol,
                    fieldnames=history.fieldnames,
                )
                bars = market_data.bars
            market_metadata = fetch_stock_metadata(
                args.symbol,
                host=args.opend_host,
                port=args.opend_port,
            )
        else:
            market_data = None
            bars = generate_sample_bars(args.sample_bars)
        symbol = args.symbol or (market_data.symbol if market_data else "US.AAPL")
        if not symbol:
            raise ValueError("CSV has no code column; pass --symbol explicitly")
        config = BacktestConfig(
            strategy_path=Path(args.strategy),
            symbol=symbol,
            initial_cash=args.initial_cash,
            commission_bps=args.commission_bps,
            min_commission=args.min_commission,
            slippage_bps=args.slippage_bps,
            warmup_bars=args.warmup_bars,
            allow_short=args.allow_short,
            bar_type=args.ktype,
            session_type=args.session,
            autype=args.autype,
            liquidate_on_end=args.liquidate_on_end,
            strategy_parameters=strategy_parameters,
            market_metadata=market_metadata,
        )
        result = run_backtest(config, bars)
        result.settings["data_source_format"] = (
            market_data.source_format if market_data else "synthetic"
        )
        if args.opend:
            result.settings["opend"] = {
                "host": args.opend_host,
                "port": args.opend_port,
                "ktype": args.ktype,
                "autype": args.autype,
                "session": args.session,
                "extended_time": args.session != "RTH",
                "pages": history.pages if history else 0,
                "cache_path": str(cache_path) if cache_path else None,
                "cache_hit": cache_hit,
            }
        write_artifacts(result, args.output, create_chart=not args.no_chart)
        print_summary(result)
        if market_data and market_data.source_format == "opend":
            print(f"OpenD 输入：已识别 {symbol}，保留 {len(bars)} 根 K 线及 time_key 时间戳。")
            if cache_hit:
                print(f"OpenD 缓存：复用 {cache_path}。")
            elif history:
                print(f"OpenD 直连：读取 {history.pages} 页；原始缓存：{cache_path or '未保存'}。")
        if args.sample:
            print("提示：本次使用确定性模拟行情，只用于验证回测流程。")
        return 0
    except Exception as error:
        print(f"回测失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
