# Composable strategy SDK

`stock_strategy.sdk` separates a Python stock strategy into five replaceable
decisions:

```text
SignalModel → PositionSizer → RiskPolicy → OrderExecutor
                       ↑
                  ExitPolicy
```

The interfaces use plain dataclasses and `Protocol`; they do not introduce a
new strategy language. A Futu-style `Strategy` can still read indicators and
market state through `stock_strategy.futu`, then pass an immutable
`SignalContext`, `AccountState`, and optional `PositionState` into a
`StrategyPipeline`.

```python
self.pipeline = StrategyPipeline(
    signal=MySignal(),
    sizer=FixedRiskSizer(0.0025, max_position_fraction=0.20),
    risk=DailyRiskPolicy(
        max_daily_loss=500,
        max_consecutive_losses=2,
    ),
    exit=MyExit(),
    executor=MyFutuExecutor(),
)

decision = self.pipeline.evaluate(context, account, position)
decision.execute()
```

`PipelineDecision.execute()` is idempotent: an executable decision submits at
most one order. Exit decisions reduce an existing position without being
blocked by entry risk limits. See
[`examples/ma_cross.py`](../examples/ma_cross.py) for a complete strategy that
keeps Futu indicator and order APIs at the adapter edge.
