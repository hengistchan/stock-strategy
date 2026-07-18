"""Futu-style moving-average crossover example."""

import math

from stock_strategy.futu import *


class Strategy(StrategyBase):
    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.global_variables()

    def trigger_symbols(self):
        self.symbol = declare_trig_symbol()

    def global_variables(self):
        self.fast_period = 20
        self.slow_period = 60
        self.capital_fraction = 0.90

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
