from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scripts.monitoring_opend_smoke import (
    DEFAULT_BLOCKED_EXIT_CODE,
    FAILED_EXIT_CODE,
    MARKETS,
    PASSED_EXIT_CODE,
    QuotePushCollector,
    build_parser,
    exit_code_for,
    run_smoke,
    write_evidence,
)

NOW = datetime(2026, 7, 28, 0, 30, tzinfo=timezone(timedelta(hours=8)))


class FakeFrame:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records

    def to_dict(self, orientation: str) -> list[dict[str, Any]]:
        if orientation != "records":
            raise AssertionError(orientation)
        return self.records


class FakeHandler:
    def __init__(self, collector: QuotePushCollector) -> None:
        self.collector = collector

    def emit(self, records: list[dict[str, Any]]) -> None:
        self.collector.ingest(FakeFrame(records))


class FakeQuoteContext:
    def __init__(
        self,
        market: str,
        *,
        market_state: str = "MORNING",
        push_mode: str = "fresh",
        subscribe_error: str | None = None,
        missing_snapshot_field: str | None = None,
        cleanup_error: bool = False,
    ) -> None:
        self.market = market
        self.market_state = market_state
        self.push_mode = push_mode
        self.subscribe_error = subscribe_error
        self.missing_snapshot_field = missing_snapshot_field
        self.cleanup_error = cleanup_error
        self.handler: FakeHandler | None = None
        self.subscribe_calls: list[dict[str, Any]] = []
        self.unsubscribe_calls: list[dict[str, Any]] = []
        self.closed = False
        self.subscribed: list[str] = []

    @property
    def underlying(self) -> str:
        return "US.AAPL" if self.market == "US" else "HK.00700"

    @property
    def call_code(self) -> str:
        return f"{self.underlying}.CALL"

    @property
    def put_code(self) -> str:
        return f"{self.underlying}.PUT"

    def get_global_state(self):
        return 0, {
            "server_ver": "10.6.6608",
            "qot_logined": True,
            "market_us": self.market_state if self.market == "US" else "CLOSED",
            "market_hk": self.market_state if self.market == "HK" else "CLOSED",
            "user_id": "must-not-leak",
        }

    def get_option_expiration_date(self, code: str):
        if code != self.underlying:
            raise AssertionError(code)
        return 0, FakeFrame(
            [
                {"strike_time": "2026-08-07"},
                {"strike_time": "2026-07-31"},
            ]
        )

    def get_option_chain(self, code: str, **kwargs: Any):
        if code != self.underlying:
            raise AssertionError(code)
        if kwargs != {
            "start": "2026-07-31",
            "end": "2026-07-31",
            "option_type": "ALL",
        }:
            raise AssertionError(kwargs)
        return 0, FakeFrame(
            [
                {
                    "code": self.call_code,
                    "stock_owner": code,
                    "option_type": "CALL",
                    "strike_price": 100,
                },
                {
                    "code": f"{self.call_code}.FAR",
                    "stock_owner": code,
                    "option_type": "CALL",
                    "strike_price": 110,
                },
                {
                    "code": self.put_code,
                    "stock_owner": code,
                    "option_type": "PUT",
                    "strike_price": 100,
                },
            ]
        )

    def get_market_snapshot(self, codes: list[str]):
        records = [self._snapshot(code) for code in codes]
        if self.missing_snapshot_field is not None and len(codes) > 1:
            records[1].pop(self.missing_snapshot_field, None)
        return 0, FakeFrame(records)

    def query_subscription(self, is_all_conn: bool = True):
        if not is_all_conn:
            raise AssertionError("query scope must be all connections")
        return 0, {
            "total_used": len(self.subscribed) + 7,
            "own_used": len(self.subscribed),
            "remain": 200 - len(self.subscribed),
            "sub_list": {"QUOTE": ["SHOULD.NOT.LEAK"]},
            "account_id": "must-not-leak",
        }

    def set_handler(self, handler: Any) -> int:
        if not isinstance(handler, FakeHandler):
            raise AssertionError(type(handler))
        self.handler = handler
        return 0

    def subscribe(
        self,
        codes: list[str],
        subtypes: list[str],
        **kwargs: Any,
    ):
        self.subscribe_calls.append(
            {
                "codes": list(codes),
                "subtypes": list(subtypes),
                **kwargs,
            }
        )
        if self.subscribe_error is not None:
            return -1, self.subscribe_error
        self.subscribed = list(codes)
        if self.handler is None:
            raise AssertionError("handler must be set before subscribe")
        self.handler.emit(self._push_records(codes, "10:30:00"))
        if self.push_mode == "fresh":
            self.handler.emit(self._push_records(codes, "10:30:01"))
        return 0, None

    def unsubscribe(
        self,
        codes: list[str],
        subtypes: list[str],
        unsubscribe_all: bool = False,
    ):
        self.unsubscribe_calls.append(
            {
                "codes": list(codes),
                "subtypes": list(subtypes),
                "unsubscribe_all": unsubscribe_all,
            }
        )
        self.subscribed = []
        if self.cleanup_error:
            return -1, "cleanup broke"
        return 0, None

    def close(self) -> None:
        self.closed = True

    def _snapshot(self, code: str) -> dict[str, Any]:
        option = code != self.underlying
        return {
            "code": code,
            "update_time": "2026-07-28 10:30:00",
            "last_price": 101 if not option else 3.5,
            "bid_price": 100 if not option else 3.4,
            "ask_price": 102 if not option else 3.6,
            "volume": 1000 if not option else 50,
            "option_valid": option,
            "option_implied_volatility": 35.5 if option else "N/A",
            "option_open_interest": 100 if option else "N/A",
            "option_delta": 0.52 if option else "N/A",
            "option_gamma": 0.08 if option else "N/A",
            "option_vega": 0.12 if option else "N/A",
            "option_theta": -0.16 if option else "N/A",
            "option_rho": 0.03 if option else "N/A",
            "option_expiry_date_distance": 3 if option else "N/A",
        }

    def _push_records(
        self,
        codes: list[str],
        provider_time: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "code": code,
                "data_date": "2026-07-28",
                "data_time": provider_time,
            }
            for code in codes
        ]


class MonitoringOpenDSmokeTest(unittest.TestCase):
    def test_passes_both_markets_and_cleans_only_exact_owned_codes(self) -> None:
        contexts = [FakeQuoteContext("US"), FakeQuoteContext("HK")]

        evidence = _run(contexts)

        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(
            evidence["summary"],
            {"passed": 2, "blocked": 0, "failed": 0},
        )
        for result, context in zip(evidence["markets"], contexts, strict=True):
            expected = [
                context.underlying,
                context.call_code,
                context.put_code,
            ]
            self.assertEqual(result["opend_version"], "10.6.6608")
            self.assertEqual(result["expiration"], "2026-07-31")
            self.assertEqual(result["atm_contracts"]["call"]["strike_price"], 100)
            self.assertEqual(result["atm_contracts"]["put"]["strike_price"], 100)
            self.assertEqual(context.subscribe_calls[0]["codes"], expected)
            self.assertEqual(context.subscribe_calls[0]["subtypes"], ["QUOTE"])
            self.assertTrue(context.subscribe_calls[0]["is_first_push"])
            self.assertTrue(context.subscribe_calls[0]["subscribe_push"])
            self.assertEqual(
                context.unsubscribe_calls,
                [
                    {
                        "codes": expected,
                        "subtypes": ["QUOTE"],
                        "unsubscribe_all": False,
                    }
                ],
            )
            self.assertEqual(
                result["push"]["pending_codes"],
                [],
            )
            self.assertTrue(context.closed)

        serialized = json.dumps(evidence)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("account_id", serialized)
        self.assertNotIn("SHOULD.NOT.LEAK", serialized)
        usage = evidence["markets"][0]["generic_subscription_usage"]["before"]
        self.assertEqual(
            set(usage),
            {
                "generic_total_used",
                "generic_own_used",
                "generic_remaining",
            },
        )

    def test_cached_first_push_alone_is_blocked_not_passed(self) -> None:
        contexts = [
            FakeQuoteContext("US", push_mode="cached_only"),
            FakeQuoteContext("HK", push_mode="cached_only"),
        ]

        evidence = _run(contexts)

        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(evidence["summary"]["blocked"], 2)
        for result, context in zip(evidence["markets"], contexts, strict=True):
            self.assertEqual(
                result["reason"],
                "fresh_provider_timestamp_timeout",
            )
            self.assertEqual(
                sorted(result["push"]["cached_first_push_provider_timestamps"]),
                sorted([context.underlying, context.call_code, context.put_code]),
            )
            self.assertEqual(result["push"]["fresh_provider_timestamps"], {})
            self.assertTrue(context.closed)

    def test_closed_market_is_blocked_without_subscribing(self) -> None:
        contexts = [
            FakeQuoteContext("US", market_state="CLOSED"),
            FakeQuoteContext("HK", market_state="REST"),
        ]

        evidence = _run(contexts)

        self.assertEqual(evidence["status"], "blocked")
        for result, context in zip(evidence["markets"], contexts, strict=True):
            self.assertEqual(result["stage"], "market_state")
            self.assertTrue(
                result["reason"].startswith("market_not_in_regular_trading:")
            )
            self.assertEqual(context.subscribe_calls, [])
            self.assertEqual(context.unsubscribe_calls, [])
            self.assertTrue(context.closed)

    def test_permission_block_is_distinct_and_still_uses_exact_cleanup(self) -> None:
        contexts = [
            FakeQuoteContext("US", subscribe_error="No quote authority"),
            FakeQuoteContext("HK", subscribe_error="No quote authority"),
        ]

        evidence = _run(contexts)

        self.assertEqual(evidence["status"], "blocked")
        for result, context in zip(evidence["markets"], contexts, strict=True):
            self.assertEqual(result["reason"], "quote_permission_unavailable")
            self.assertEqual(len(context.unsubscribe_calls), 1)
            self.assertFalse(context.unsubscribe_calls[0]["unsubscribe_all"])
            self.assertTrue(context.closed)

    def test_field_mapping_and_cleanup_errors_are_failed(self) -> None:
        contexts = [
            FakeQuoteContext(
                "US",
                missing_snapshot_field="option_implied_volatility",
            ),
            FakeQuoteContext("HK", cleanup_error=True),
        ]

        evidence = _run(contexts)

        self.assertEqual(evidence["status"], "failed")
        us, hk = evidence["markets"]
        self.assertEqual(us["status"], "failed")
        self.assertEqual(us["stage"], "field_mapping")
        self.assertEqual(hk["status"], "failed")
        self.assertEqual(hk["stage"], "cleanup")
        self.assertIn("unsubscribe_failed", hk["reason"])
        self.assertTrue(contexts[0].closed)
        self.assertTrue(contexts[1].closed)

    def test_unreachable_opend_is_safe_and_never_opens_a_context(self) -> None:
        opened = False

        def context_factory(**_kwargs: Any):
            nonlocal opened
            opened = True
            raise AssertionError("context must not be opened")

        evidence = run_smoke(
            context_factory=context_factory,
            handler_factory=FakeHandler,
            success_code=0,
            sdk_version="10.6.6608",
            now=lambda: NOW,
            preflight=lambda _host, _port: False,
            market_specs=(MARKETS[0],),
        )

        self.assertFalse(opened)
        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(evidence["summary"]["blocked"], 1)
        self.assertEqual(
            [result["market"] for result in evidence["markets"]],
            ["US"],
        )
        self.assertTrue(
            all(
                result["reason"] == "opend_unreachable"
                for result in evidence["markets"]
            )
        )

    def test_run_smoke_rejects_an_empty_market_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one market"):
            run_smoke(
                context_factory=lambda **_kwargs: FakeQuoteContext("US"),
                handler_factory=FakeHandler,
                success_code=0,
                sdk_version="10.6.6608",
                market_specs=(),
            )

    def test_each_market_can_pass_as_an_independent_gate(self) -> None:
        for spec in MARKETS:
            with self.subTest(market=spec.market):
                context = FakeQuoteContext(spec.market)

                evidence = _run(
                    [context],
                    market_specs=(spec,),
                )

                self.assertEqual(evidence["status"], "passed")
                self.assertEqual(
                    evidence["summary"],
                    {"passed": 1, "blocked": 0, "failed": 0},
                )
                self.assertEqual(
                    [result["market"] for result in evidence["markets"]],
                    [spec.market],
                )

    def test_all_market_mode_remains_a_cross_market_diagnostic(self) -> None:
        evidence = _run(
            [
                FakeQuoteContext("US"),
                FakeQuoteContext("HK", market_state="CLOSED"),
            ],
            market_specs=MARKETS,
        )

        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(
            evidence["summary"],
            {"passed": 1, "blocked": 1, "failed": 0},
        )
        self.assertEqual(
            [result["market"] for result in evidence["markets"]],
            ["US", "HK"],
        )

    def test_cli_defaults_to_all_markets_and_sixty_second_push_window(self) -> None:
        defaults = build_parser().parse_args([])
        us = build_parser().parse_args(["--market", "US"])
        hk = build_parser().parse_args(["--market", "HK"])

        self.assertEqual(defaults.market, "all")
        self.assertEqual(defaults.push_timeout, 60.0)
        self.assertEqual(us.market, "US")
        self.assertEqual(hk.market, "HK")

    def test_successful_subscription_holds_until_exact_cleanup_is_allowed(
        self,
    ) -> None:
        contexts = [
            FakeQuoteContext("US"),
            FakeQuoteContext("HK", market_state="CLOSED"),
        ]
        clock = [100.0]
        waits: list[float] = []

        def monotonic_clock() -> float:
            return clock[0]

        def sleep(seconds: float) -> None:
            waits.append(seconds)
            clock[0] += seconds

        evidence = _run(
            contexts,
            monotonic_clock=monotonic_clock,
            sleep=sleep,
            minimum_subscription_seconds=60.5,
        )

        self.assertEqual(evidence["status"], "blocked")
        self.assertEqual(waits, [60.5])
        self.assertEqual(
            evidence["markets"][0]["cleanup"]["waited_before_unsubscribe_seconds"],
            60.5,
        )
        self.assertEqual(len(contexts[0].unsubscribe_calls), 1)
        self.assertFalse(contexts[0].unsubscribe_calls[0]["unsubscribe_all"])

    def test_evidence_file_and_exit_codes_are_machine_readable(self) -> None:
        evidence = _run([FakeQuoteContext("US"), FakeQuoteContext("HK")])
        with tempfile.TemporaryDirectory() as directory:
            path = write_evidence(
                evidence,
                Path(directory),
                now=lambda: NOW,
            )
            stored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(stored, evidence)
        self.assertTrue(path.name.endswith("-monitoring-opend-smoke.json"))
        self.assertEqual(
            exit_code_for("passed", blocked_exit_code=DEFAULT_BLOCKED_EXIT_CODE),
            PASSED_EXIT_CODE,
        )
        self.assertEqual(
            exit_code_for("blocked", blocked_exit_code=DEFAULT_BLOCKED_EXIT_CODE),
            DEFAULT_BLOCKED_EXIT_CODE,
        )
        self.assertEqual(
            exit_code_for("blocked", blocked_exit_code=0),
            PASSED_EXIT_CODE,
        )
        self.assertEqual(
            exit_code_for("failed", blocked_exit_code=DEFAULT_BLOCKED_EXIT_CODE),
            FAILED_EXIT_CODE,
        )


def _run(
    contexts: list[FakeQuoteContext],
    *,
    monotonic_clock=None,
    sleep=None,
    minimum_subscription_seconds: float = 0,
    market_specs=None,
) -> dict[str, Any]:
    remaining = list(contexts)

    def context_factory(**kwargs: Any) -> FakeQuoteContext:
        self_expected = {
            "host": "127.0.0.1",
            "port": 11111,
            "is_async_connect": True,
        }
        if kwargs != self_expected:
            raise AssertionError(kwargs)
        return remaining.pop(0)

    return run_smoke(
        context_factory=context_factory,
        handler_factory=FakeHandler,
        success_code=0,
        sdk_version="10.6.6608",
        push_timeout_seconds=0,
        now=lambda: NOW,
        preflight=lambda _host, _port: True,
        monotonic_clock=monotonic_clock,
        sleep=sleep,
        minimum_subscription_seconds=minimum_subscription_seconds,
        market_specs=market_specs,
    )


if __name__ == "__main__":
    unittest.main()
