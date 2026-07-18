"""Futu-style moving-average crossover example."""

import math

from stock_strategy.futu import *


STRATEGY_PARAMETERS = {
    "fast_period": {
        "label": "短均线周期",
        "description": "用于产生快速趋势信号的移动平均周期。",
        "type": "int",
        "default": 20,
        "min": 2,
        "max": 120,
        "step": 1,
        "candidates": [10, 20],
    },
    "slow_period": {
        "label": "长均线周期",
        "description": "用于过滤长期趋势的移动平均周期。",
        "type": "int",
        "default": 60,
        "min": 5,
        "max": 240,
        "step": 1,
        "candidates": [40, 60],
    },
    "capital_fraction": {
        "label": "资金使用比例",
        "description": "开仓时使用可买数量的比例。",
        "type": "float",
        "default": 0.9,
        "min": 0.1,
        "max": 1.0,
        "step": 0.05,
        "candidates": [0.8, 0.9],
    },
}


class Strategy(StrategyBase):
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.global_variables()

    def trigger_symbols(self):
        self.symbol = declare_trig_symbol()

    def global_variables(self):
        self.fast_period = strategy_parameter("fast_period")
        self.slow_period = strategy_parameter("slow_period")
        self.capital_fraction = strategy_parameter("capital_fraction")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be smaller than slow_period")

    def handle_data(self):
        fast_now = ma(self.symbol, period=self.fast_period, bar_type=BarType.K_DAY, select=1)
        slow_now = ma(self.symbol, period=self.slow_period, bar_type=BarType.K_DAY, select=1)
        fast_previous = ma(self.symbol, period=self.fast_period, bar_type=BarType.K_DAY, select=2)
        slow_previous = ma(self.symbol, period=self.slow_period, bar_type=BarType.K_DAY, select=2)

        if any(math.isnan(value) for value in (fast_now, slow_now, fast_previous, slow_previous)):
            return

        crossed_up = fast_now > slow_now and fast_previous <= slow_previous
        crossed_down = fast_now < slow_now and fast_previous >= slow_previous

        if crossed_up and position_side(self.symbol) == PositionSide.NONE:
            cash_quantity = max_qty_to_buy_on_cash(
                self.symbol,
                order_type=OrdType.MKT,
                price=current_price(self.symbol),
            )
            quantity = math.floor(cash_quantity * self.capital_fraction)
            if quantity > 0:
                place_market(self.symbol, qty=quantity, side=OrderSide.BUY)

        elif crossed_down and position_side(self.symbol) == PositionSide.LONG:
            close_positions(self.symbol)
