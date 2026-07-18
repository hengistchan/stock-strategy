from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Bar, BarType, Contract, LogEntry, Order, OrderSide, Position, TimeInForce, Trade


@dataclass(slots=True)
class Fill:
    order_id: str
    date: str
    price: float
    quantity: float
    side: OrderSide
    fee: float


class Broker:
    """Single-symbol, next-bar broker with market, limit and stop orders."""

    def __init__(
        self,
        initial_cash: float,
        commission_bps: float,
        min_commission: float,
        slippage_bps: float,
        allow_short: bool,
        bar_type: BarType | str = BarType.K_DAY,
    ) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.commission_rate = commission_bps / 10_000
        self.min_commission = float(min_commission)
        self.slippage_rate = slippage_bps / 10_000
        self.allow_short = allow_short
        self.bar_type = BarType(bar_type)
        self.position = Position()
        self.pending_orders: list[Order] = []
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []
        self.logs: list[LogEntry] = []
        self.total_fees = 0.0
        self._next_order_id = 1
        self._next_trade_id = 1

    def submit(
        self,
        *,
        symbol: Contract,
        side: OrderSide,
        quantity: float,
        order_type: str,
        current_index: int,
        current_date: str,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: float | None = None,
        stop_price: float | None = None,
        exit_reason: str = "signal",
        current_price: float | None = None,
    ) -> str:
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("order quantity must be a positive finite number")
        if limit_price is not None and (not math.isfinite(limit_price) or limit_price <= 0):
            raise ValueError("limit price must be positive")
        if stop_price is not None and (not math.isfinite(stop_price) or stop_price <= 0):
            raise ValueError("stop price must be positive")

        reserved_cash = self._estimate_reserved_cash(
            side=side,
            quantity=quantity,
            order_type=order_type,
            current_price=current_price,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        if reserved_cash > self.available_cash + 1e-9:
            raise ValueError("order exceeds cash available after pending buy orders")
        if side == OrderSide.SELL and quantity > self.max_sell_quantity() + 1e-9:
            raise ValueError("order exceeds position available after pending sell orders")

        order_id = f"SIM-{self._next_order_id:06d}"
        self._next_order_id += 1
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=float(quantity),
            order_type=order_type,
            submitted_index=current_index,
            submitted_date=current_date,
            time_in_force=time_in_force,
            limit_price=limit_price,
            stop_price=stop_price,
            exit_reason=exit_reason,
            active_date=(
                self._trading_date(current_date)
                if time_in_force == TimeInForce.DAY
                and self.bar_type not in {BarType.K_DAY, BarType.K_WEEK}
                else None
            ),
            reserved_cash=reserved_cash,
        )
        self.pending_orders.append(order)
        self._log(current_date, "INFO", f"submitted {order_type} {side.value} {quantity:g} {symbol}")
        return order_id

    def process_bar(self, bar: Bar, index: int) -> None:
        remaining: list[Order] = []
        trading_date = self._trading_date(bar.date)
        for order in self.pending_orders:
            if index <= order.submitted_index:
                remaining.append(order)
                continue
            if order.active_date is None:
                order.active_date = trading_date
            elif (
                order.time_in_force == TimeInForce.DAY
                and trading_date != order.active_date
            ):
                self._log(bar.date, "INFO", f"expired {order.order_id} at trading-day boundary")
                continue
            price = self._fill_price(order, bar)
            if price is None:
                remaining.append(order)
                continue
            self._execute(order, bar.date, index, price)
        self.pending_orders = remaining

    def cancel_all(self, current_date: str) -> None:
        if self.pending_orders:
            self._log(current_date, "INFO", f"cancelled {len(self.pending_orders)} pending order(s)")
        self.pending_orders.clear()

    def liquidate(self, symbol: Contract, bar: Bar, index: int) -> None:
        self.cancel_all(bar.date)
        if self.position.quantity == 0:
            return
        side = OrderSide.SELL if self.position.quantity > 0 else OrderSide.BUY_BACK
        order = Order(
            order_id=f"SIM-{self._next_order_id:06d}",
            symbol=symbol,
            side=side,
            quantity=abs(self.position.quantity),
            order_type="MARKET",
            submitted_index=index,
            submitted_date=bar.date,
            exit_reason="end-of-test",
        )
        self._next_order_id += 1
        price = self._apply_slippage(bar.close, side)
        self._execute(order, bar.date, index, price)

    def equity(self, mark_price: float) -> float:
        return self.cash + self.position.quantity * mark_price

    def max_cash_buy_quantity(self, mark_price: float) -> int:
        effective_price = mark_price * (1 + self.slippage_rate + self.commission_rate)
        available = max(0.0, self.available_cash - self.min_commission)
        return max(0, math.floor(available / effective_price))

    @property
    def reserved_buy_cash(self) -> float:
        return sum(order.reserved_cash for order in self.pending_orders)

    @property
    def available_cash(self) -> float:
        return max(0.0, self.cash - self.reserved_buy_cash)

    @property
    def pending_sell_quantity(self) -> float:
        return sum(
            order.quantity
            for order in self.pending_orders
            if order.side == OrderSide.SELL
        )

    def max_sell_quantity(self) -> float:
        return max(0.0, self.position.quantity - self.pending_sell_quantity)

    def _estimate_reserved_cash(
        self,
        *,
        side: OrderSide,
        quantity: float,
        order_type: str,
        current_price: float | None,
        limit_price: float | None,
        stop_price: float | None,
    ) -> float:
        if side not in (OrderSide.BUY, OrderSide.BUY_BACK):
            return 0.0
        reference_price = limit_price or stop_price or current_price
        if reference_price is None:
            return 0.0
        if not math.isfinite(reference_price) or reference_price <= 0:
            raise ValueError("current price must be positive when reserving order cash")
        if order_type != "LIMIT":
            reference_price *= 1 + self.slippage_rate
        fee = max(self.min_commission, quantity * reference_price * self.commission_rate)
        return quantity * reference_price + fee

    @staticmethod
    def _trading_date(value: str) -> str:
        # OpenD emits ISO-like values (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        # Keeping the calendar component is deliberate: DAY validity is tied to
        # the first executable bar's exchange date in this next-bar simulator.
        return value.strip()[:10]

    def _fill_price(self, order: Order, bar: Bar) -> float | None:
        if order.order_type == "MARKET":
            return self._apply_slippage(bar.open, order.side)
        if order.order_type == "LIMIT":
            assert order.limit_price is not None
            price = self._limit_base_price(order, bar)
            if price is None:
                return None
            slipped = self._apply_slippage(price, order.side)
            if order.side in (OrderSide.BUY, OrderSide.BUY_BACK):
                return min(slipped, order.limit_price)
            return max(slipped, order.limit_price)
        if order.order_type == "STOP":
            assert order.stop_price is not None
            price = self._stop_base_price(order, bar)
            return None if price is None else self._apply_slippage(price, order.side)
        raise ValueError(f"unsupported order type: {order.order_type}")

    @staticmethod
    def _limit_base_price(order: Order, bar: Bar) -> float | None:
        assert order.limit_price is not None
        if order.side in (OrderSide.BUY, OrderSide.BUY_BACK):
            if bar.open <= order.limit_price:
                return bar.open
            return order.limit_price if bar.low <= order.limit_price else None
        if bar.open >= order.limit_price:
            return bar.open
        return order.limit_price if bar.high >= order.limit_price else None

    @staticmethod
    def _stop_base_price(order: Order, bar: Bar) -> float | None:
        assert order.stop_price is not None
        if order.side in (OrderSide.BUY, OrderSide.BUY_BACK):
            if bar.open >= order.stop_price:
                return bar.open
            return order.stop_price if bar.high >= order.stop_price else None
        if bar.open <= order.stop_price:
            return bar.open
        return order.stop_price if bar.low <= order.stop_price else None

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        if side in (OrderSide.BUY, OrderSide.BUY_BACK):
            return price * (1 + self.slippage_rate)
        return price * (1 - self.slippage_rate)

    def _execute(self, order: Order, date: str, index: int, price: float) -> None:
        if not self._validate_position_change(order, date, price):
            return

        fee = max(self.min_commission, order.quantity * price * self.commission_rate)
        signed_delta = order.quantity if order.side in (OrderSide.BUY, OrderSide.BUY_BACK) else -order.quantity
        old_quantity = self.position.quantity

        if signed_delta > 0:
            self.cash -= order.quantity * price + fee
        else:
            self.cash += order.quantity * price - fee
        self.total_fees += fee

        if old_quantity == 0 or old_quantity * signed_delta > 0:
            self._increase_position(signed_delta, price, fee, date, index)
        else:
            self._decrease_position(order, signed_delta, price, fee, date, index)

        self.fills.append(Fill(order.order_id, date, price, order.quantity, order.side, fee))
        self._log(date, "FILL", f"filled {order.order_id} at {price:.4f}; fee {fee:.2f}")

    def _validate_position_change(self, order: Order, date: str, price: float) -> bool:
        position = self.position.quantity
        quantity = order.quantity
        reason: str | None = None
        if order.side == OrderSide.BUY:
            if position < 0:
                reason = "BUY cannot cover a short position; use BUY_BACK"
            else:
                estimated_fee = max(self.min_commission, quantity * price * self.commission_rate)
                if quantity * price + estimated_fee > self.cash + 1e-9:
                    reason = "insufficient cash"
        elif order.side == OrderSide.SELL:
            if position <= 0 or quantity > position + 1e-9:
                reason = "insufficient long position"
        elif order.side == OrderSide.SELL_SHORT:
            if not self.allow_short:
                reason = "short selling disabled"
            elif position > 0:
                reason = "close long position before selling short"
        elif order.side == OrderSide.BUY_BACK:
            if position >= 0 or quantity > abs(position) + 1e-9:
                reason = "insufficient short position"

        if reason:
            self._log(date, "REJECT", f"rejected {order.order_id}: {reason}")
            return False
        return True

    def _increase_position(
        self,
        signed_delta: float,
        price: float,
        fee: float,
        date: str,
        index: int,
    ) -> None:
        old_abs = abs(self.position.quantity)
        delta_abs = abs(signed_delta)
        new_abs = old_abs + delta_abs
        if old_abs == 0:
            self.position.entry_date = date
            self.position.entry_index = index
        self.position.average_price = (
            self.position.average_price * old_abs + price * delta_abs
        ) / new_abs
        self.position.quantity += signed_delta
        self.position.entry_fees += fee

    def _decrease_position(
        self,
        order: Order,
        signed_delta: float,
        price: float,
        exit_fee: float,
        date: str,
        index: int,
    ) -> None:
        old_quantity = self.position.quantity
        close_quantity = abs(signed_delta)
        old_abs = abs(old_quantity)
        entry_fee = self.position.entry_fees * (close_quantity / old_abs)
        if old_quantity > 0:
            gross = (price - self.position.average_price) * close_quantity
            side = "LONG"
        else:
            gross = (self.position.average_price - price) * close_quantity
            side = "SHORT"
        net = gross - entry_fee - exit_fee
        cost_basis = self.position.average_price * close_quantity + entry_fee
        trade = Trade(
            trade_id=self._next_trade_id,
            symbol=str(order.symbol),
            side=side,
            entry_date=self.position.entry_date,
            exit_date=date,
            entry_price=self.position.average_price,
            exit_price=price,
            quantity=close_quantity,
            gross_pnl=gross,
            fees=entry_fee + exit_fee,
            net_pnl=net,
            return_pct=(net / cost_basis * 100) if cost_basis else 0.0,
            bars_held=max(0, index - self.position.entry_index),
            exit_reason=order.exit_reason,
        )
        self._next_trade_id += 1
        self.trades.append(trade)
        self.position.quantity += signed_delta
        self.position.entry_fees -= entry_fee
        if abs(self.position.quantity) < 1e-9:
            self.position = Position()

    def _log(self, date: str, level: str, message: str) -> None:
        self.logs.append(LogEntry(date=date, level=level, message=message))
