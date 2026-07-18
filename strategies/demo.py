# V1.5 Balanced Entry + Measured Move + Multi-stage Profit Protection
# US/HK market-time schedule + 15M context/support + 5M signal + 1M execution
# Exit: structural stop + 0.6R/1.0R protection + important-low trailing + measured move
class Strategy(StrategyBase):

    def initialize(self):
        declare_strategy_type(AlgoStrategyType.SECURITY)
        self.trigger_symbols()
        self.custom_indicator()
        self.global_variables()

    def trigger_symbols(self):
        self.symbol = declare_trig_symbol()
        self.market = get_symbol_market(self.symbol)
        self.account_currency = get_symbol_currency(self.symbol)
        if self.market not in (Market.US, Market.HK):
            raise ValueError("demo strategy currently supports US and HK stocks")

    def custom_indicator(self):
        pass

    def global_variables(self):
        # ============================================================
        # 周期配置
        # ============================================================
        self.EXEC_BAR = BarType.K_1M
        self.SIGNAL_BAR = BarType.K_5M
        self.CONTEXT_BAR = BarType.K_15M
        self.DAY_BAR = BarType.K_DAY
        self.SESSION = THType.RTH

        # 当前回测环境已验证：select=2 对应稳定的已完成 K 线。
        self.CLOSED_SHIFT = 2

        # ============================================================
        # 状态编号
        # ============================================================
        self.WAIT_H1 = 0
        self.WAIT_H1_FAILURE = 1
        self.WAIT_SECOND_BOTTOM = 2

        self.ENTRY_ACTIVE = 10
        self.ENTRY_CANCEL_PENDING = 11
        self.ENTRY_SYNC_VALID = 12
        self.ENTRY_SYNC_LATE = 13

        self.HOLDING = 20
        self.STOP_REPLACE_CANCEL = 21
        self.STOP_FILL_SYNC = 22

        self.EXIT_CANCEL_STOP = 30
        self.EXIT_SUBMIT = 31
        self.EXIT_WAIT_FILL = 32

        # ============================================================
        # 价格行为参数
        # ============================================================
        self.MR_LOOKBACK = 20
        self.MIN_MR_VALID_BARS = 10

        self.LEG1_MIN_BARS = 2
        # V1.5：恢复必要的价格行为质量，但不回到极端稀疏版本。
        self.LEG1_MAX_BARS = 8
        self.LEG1_MIN_DISTANCE_MR = 1.20
        self.LEG1_STRONG_TWO_BAR_MR = 1.60

        # H1 是第一次反转尝试，不要求收盘必须越过前一根最高价；
        # 只要求本根最高价突破前高并且收盘质量合格。
        self.H1_CLOSE_LOCATION_MIN = 0.62
        self.H1_RANGE_MIN_MR = 0.45
        self.H1_RANGE_MAX_MR = 2.00
        self.H1_MIN_SEPARATION_MR = 0.60
        self.H1_MAX_WAIT_BARS = 10

        self.SECOND_BOTTOM_MAX_WAIT_BARS = 12
        self.BOTTOM_ZONE_MR = 0.50
        self.MAX_UNDERCUT_MR = 0.50
        self.LEG2_MAX_VS_LEG1 = 1.15

        self.SIGNAL_CLOSE_LOCATION_MIN = 0.60
        self.SIGNAL_STRONG_CLOSE_LOCATION = 0.70
        self.SIGNAL_RANGE_MIN_MR = 0.45
        self.SIGNAL_RANGE_MAX_MR = 1.80
        self.SIGNAL_LOWER_TAIL_MIN = 0.15
        self.PA_SCORE_MIN = 2

        # 默认要求关键支撑。若不在支撑附近，只有强假跌破收回形态才可绕过。
        self.REQUIRE_CONTEXT_SUPPORT = True

        # ============================================================
        # 仓位、风险及目标
        # ============================================================
        self.RISK_PER_TRADE_PCT = 0.0025
        # 原 20% 市值上限会使中小账户无法买入一手港股。
        # 风险预算仍由 RISK_PER_TRADE_PCT 控制，市值上限放宽至 50%。
        self.MAX_POSITION_VALUE_PCT = 0.50

        self.MIN_R_TICKS = 3
        self.MIN_R_MR = 0.20
        self.MAX_R_MR = 2.00

        self.NECKLINE_MIN_SPACE_R = 0.40
        self.MEASURED_TARGET_MIN_R = 1.20
        self.MAX_ENTRY_SLIPPAGE_R = 0.25

        # 两级利润保护：0.6R 先缩小结构风险，1.0R 后至少锁到成本上方一档。
        self.PROTECT_SIGNAL_ARM_R = 0.60
        self.BREAKEVEN_ARM_R = 1.00
        self.BREAKEVEN_BUFFER_TICKS = 1

        # 浮盈达到 0.6R 后，允许使用确认的重要 Higher Low 继续上移止损。
        self.IMPORTANT_LOW_ARM_R = 0.60
        self.IMPORTANT_LOW_MAX_PULLBACK_BARS = 4

        # 快速失败只针对几乎没有正向跟进的交易。
        self.FAST_FAIL_MAX_BARS = 2
        self.FAST_FAIL_MFE_R = 0.30
        # Measured Move 需要发展时间，无进展检查延后至 25 分钟。
        self.NO_PROGRESS_BARS = 5
        self.NO_PROGRESS_MFE_R = 0.35
        # 最长持有约 80 分钟。
        self.MAX_HOLD_5M_BARS = 16

        self.MAX_SIGNAL_ATTEMPTS = 3
        self.MAX_DAILY_TRADES = 2
        self.MAX_DAILY_LOSS_R = -2.00
        self.MAX_CONSECUTIVE_LOSSES = 2

        self.CANCEL_WARNING_BARS = 3
        self.POSITION_SYNC_WARNING_BARS = 3
        self.STOP_PARTIAL_SYNC_GRACE = 2

        # ============================================================
        # 调试
        # ============================================================
        self.DEBUG_EVERY_MINUTE = False
        self.DEBUG_EVERY_5M = False
        self.PRINT_DAILY_DIAGNOSTICS = True

        # ============================================================
        # 基础运行状态
        # ============================================================
        self.state = self.WAIT_H1
        self.base_holding_qty = -1.0
        self.tick = 0.0
        self.lot = 0.0

        self.last_minute_key = ""
        self.last_5m_key = ""
        self.current_day_key = ""
        self.session_low = 0.0
        self.mr5 = 0.0

        # ============================================================
        # 每日风控
        # ============================================================
        self.daily_trade_count = 0
        self.daily_realized_r = 0.0
        self.consecutive_losses = 0
        self.operational_error_today = False

        # ============================================================
        # 形态状态
        # ============================================================
        self.first_bottom_low = 0.0
        self.h1_high = 0.0
        self.h1_low = 0.0
        self.h1_midpoint = 0.0
        self.neckline_high = 0.0

        self.leg1_start_high = 0.0
        self.leg1_distance = 0.0
        self.leg1_avg_bear_body = 0.0
        self.leg1_bars = 0

        self.h1_wait_bars = 0
        self.h1_separated = False
        self.second_leg_bars = 0
        self.signal_attempts = 0

        self.signal_high = 0.0
        self.signal_low = 0.0
        self.signal_midpoint = 0.0
        self.second_bottom_low = 0.0
        self.measured_move_target = 0.0

        # ============================================================
        # 入场计划及订单
        # ============================================================
        self.planned_entry = 0.0
        self.planned_stop = 0.0
        self.planned_r = 0.0
        self.planned_qty = 0.0

        self.entry_order_id = ""
        self.entry_expire_minute = -1
        self.entry_fill_valid = False
        self.entry_expired = False
        self.entry_cancel_wait_count = 0

        # ============================================================
        # 当前交易
        # ============================================================
        self.trade_active = False
        self.trade_entry_price = 0.0
        self.trade_entry_qty = 0.0
        self.trade_initial_r = 0.0
        self.trade_risk_value = 0.0
        self.trade_realized_pnl = 0.0

        self.entry_5m_key = ""
        self.hold_5m_bars = 0
        self.mfe_price = 0.0
        # 0=未保护，1=已启动信号K低点保护，2=已启动成本保护。
        self.profit_protection_stage = 0

        self.active_stop = 0.0
        self.stop_order_id = ""
        self.stop_target_qty = 0.0
        self.stop_accounted_fill = 0.0
        self.stop_partial_mismatch_count = 0
        self.stop_sync_wait_count = 0

        self.pending_stop_price = 0.0
        self.stop_replace_wait_count = 0
        # 移动止损撤单期间若触及 Measured Move，撤单完成后直接退出而不重挂止损。
        self.stop_replace_exit_pending = False

        # V1.4 不再使用固定 T1/T2 或单手 1.5R 止盈。
        # 全部仓位以双底 Measured Move 为主动止盈目标。
        self.multi_lot_trade = False
        self.t1_done = False
        self.t1_price = 0.0
        self.t1_qty = 0.0
        self.t2_price = 0.0
        self.single_target_price = 0.0
        self.measured_target_price = 0.0

        # 重要底部跟踪状态。
        self.important_low_armed = False
        self.important_low_count = 0
        self.last_important_low = 0.0
        self.pullback_active = False
        self.pullback_bars = 0
        self.pullback_low = 0.0

        # ============================================================
        # 软件协调退出
        # ============================================================
        self.exit_reason = ""
        self.exit_target_remaining_qty = 0.0
        self.exit_mark_t1 = False
        self.exit_order_id = ""
        self.exit_submitted_qty = 0.0
        self.exit_position_before = 0.0
        self.exit_accounted_fill = 0.0
        self.exit_wait_count = 0
        self.exit_cancel_wait_count = 0
        self.exit_stop_terminal_wait_count = 0

        self.force_exit_pending = False

        # ============================================================
        # 信号漏斗诊断计数
        # ============================================================
        self.diag_5m_bars = 0
        self.diag_h1_basic = 0
        self.diag_leg1_pass = 0
        self.diag_h1_failure = 0
        self.diag_second_scans = 0
        self.diag_context_pass = 0
        self.diag_signal_basic = 0
        self.diag_pa_pass = 0
        self.diag_risk_pass = 0
        self.diag_space_pass = 0
        self.diag_budget_pass = 0
        self.diag_orders = 0

    def handle_data(self):
        # ============================================================
        # 0. 当前时间和运行节拍
        # ============================================================
        # 所有日内时间规则都按标的市场时区计算，避免美股被转换到
        # 北京时间后永远落在入场窗口之外。
        now = device_time(TimeZone.MARKET_TIME_ZONE)
        minute_of_day = now.hour * 60 + now.minute

        minute_key = (
            str(now.year) + "-" + str(now.month) + "-" + str(now.day)
            + " " + str(now.hour) + ":" + str(now.minute)
        )

        if self.last_minute_key == minute_key:
            return

        self.last_minute_key = minute_key

        day_key = str(now.year) + "-" + str(now.month) + "-" + str(now.day)

        if self.current_day_key != day_key:
            if self.current_day_key != "" and self.PRINT_DAILY_DIAGNOSTICS:
                print(
                    "昨日信号漏斗：",
                    "day=", self.current_day_key,
                    "5m=", self.diag_5m_bars,
                    "h1_basic=", self.diag_h1_basic,
                    "leg1=", self.diag_leg1_pass,
                    "h1_fail=", self.diag_h1_failure,
                    "second_scan=", self.diag_second_scans,
                    "context=", self.diag_context_pass,
                    "signal_basic=", self.diag_signal_basic,
                    "pa=", self.diag_pa_pass,
                    "risk=", self.diag_risk_pass,
                    "space=", self.diag_space_pass,
                    "budget=", self.diag_budget_pass,
                    "orders=", self.diag_orders
                )

            self.current_day_key = day_key
            self.daily_trade_count = 0
            self.daily_realized_r = 0.0
            self.consecutive_losses = 0
            self.operational_error_today = False
            self.session_low = 0.0

            self.diag_5m_bars = 0
            self.diag_h1_basic = 0
            self.diag_leg1_pass = 0
            self.diag_h1_failure = 0
            self.diag_second_scans = 0
            self.diag_context_pass = 0
            self.diag_signal_basic = 0
            self.diag_pa_pass = 0
            self.diag_risk_pass = 0
            self.diag_space_pass = 0
            self.diag_budget_pass = 0
            self.diag_orders = 0

            # 只有在无仓位、无活动订单时才能跨日重置形态。
            if (
                not self.trade_active
                and self.entry_order_id == ""
                and self.stop_order_id == ""
                and self.exit_order_id == ""
            ):
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                self.signal_high = 0.0
                self.signal_low = 0.0
                self.signal_midpoint = 0.0
                self.second_bottom_low = 0.0
                self.measured_move_target = 0.0
                self.planned_entry = 0.0
                self.planned_stop = 0.0
                self.planned_r = 0.0
                self.planned_qty = 0.0

            print("新交易日：", day_key)

        # ============================================================
        # 1. 初始化标的信息与策略仓位
        # ============================================================
        if self.tick <= 0:
            try:
                self.tick = min_tick(self.symbol)
            except Exception as error:
                print("获取最小变动价格失败：", error)
                return

        if self.lot <= 0:
            try:
                self.lot = lot_size(self.symbol)
            except Exception as error:
                print("获取每手股数失败：", error)
                return

        try:
            holding_qty = position_holding_qty(self.symbol)
        except Exception as error:
            print("获取持仓失败：", error)
            return

        if self.base_holding_qty < 0:
            self.base_holding_qty = holding_qty
            print("记录策略启动前基础持仓：", self.base_holding_qty)

        strategy_qty = holding_qty - self.base_holding_qty

        if strategy_qty < 0:
            print("警告：持仓低于基础持仓，按策略仓位 0 处理")
            strategy_qty = 0.0

        five_bucket = int(now.minute / 5)
        current_5m_key = (
            str(now.year) + "-" + str(now.month) + "-" + str(now.day)
            + " " + str(now.hour) + ":" + str(five_bucket)
        )
        is_new_5m = current_5m_key != self.last_5m_key

        if is_new_5m:
            self.last_5m_key = current_5m_key

        if self.market == Market.US:
            # 美股 RTH 没有午休；尾盘前 25 分钟停止寻找新形态。
            in_entry_window = (
                minute_of_day >= 9 * 60 + 45
                and minute_of_day < 15 * 60 + 35
            )
            force_flat_time = minute_of_day >= 15 * 60 + 55
            flat_pattern_block = (
                minute_of_day < 9 * 60 + 45
                or minute_of_day >= 15 * 60 + 35
            )
        else:
            # 港股采用上午、下午两个连续交易时段。
            morning_entry = (
                minute_of_day >= 9 * 60 + 45
                and minute_of_day < 11 * 60 + 35
            )
            afternoon_entry = (
                minute_of_day >= 13 * 60 + 15
                and minute_of_day < 15 * 60 + 35
            )
            in_entry_window = morning_entry or afternoon_entry
            force_flat_time = (
                (minute_of_day >= 11 * 60 + 55 and minute_of_day < 13 * 60)
                or minute_of_day >= 15 * 60 + 55
            )
            flat_pattern_block = (
                minute_of_day < 9 * 60 + 45
                or (
                    minute_of_day >= 11 * 60 + 35
                    and minute_of_day < 13 * 60 + 15
                )
                or minute_of_day >= 15 * 60 + 35
            )

        can_open = (
            in_entry_window
            and not self.operational_error_today
            and self.daily_trade_count < self.MAX_DAILY_TRADES
            and self.daily_realized_r > self.MAX_DAILY_LOSS_R
            and self.consecutive_losses < self.MAX_CONSECUTIVE_LOSSES
        )

        if force_flat_time and strategy_qty > 0:
            self.force_exit_pending = True

        if self.DEBUG_EVERY_MINUTE:
            print(
                "1M DEBUG：",
                "time=", now,
                "state=", self.state,
                "qty=", strategy_qty,
                "entry=", self.entry_order_id,
                "stop=", self.stop_order_id,
                "exit=", self.exit_order_id
            )

        # ============================================================
        # 2. 入场订单生命周期
        # ============================================================
        if self.state in (
            self.ENTRY_ACTIVE,
            self.ENTRY_CANCEL_PENDING,
            self.ENTRY_SYNC_VALID,
            self.ENTRY_SYNC_LATE
        ):
            entry_status = None
            entry_total_qty = 0.0
            entry_filled_qty = 0.0

            if self.entry_order_id != "":
                try:
                    entry_status = order_status(self.entry_order_id)
                except Exception as error:
                    print("查询入场订单状态失败：", error)

                try:
                    entry_total_qty = order_qty(self.entry_order_id)
                except Exception as error:
                    print("查询入场订单数量失败：", error)

                try:
                    entry_filled_qty = order_filled_qty(self.entry_order_id)
                except Exception as error:
                    print("查询入场订单成交数量失败：", error)

            entry_cancel_terminal = (
                entry_status == OrderStatus.CANCELLED_PART
                or entry_status == OrderStatus.CANCELLED_ALL
                or entry_status == OrderStatus.FAILED
                or entry_status == OrderStatus.DISABLED
            )

            entry_fully_filled = (
                entry_status == OrderStatus.FILLED_ALL
                or (
                    entry_total_qty > 0
                    and entry_filled_qty >= entry_total_qty
                )
            )

            # 时段结束强制取消未成交入场单。
            if (
                force_flat_time
                and self.state in (self.ENTRY_ACTIVE, self.ENTRY_CANCEL_PENDING)
                and strategy_qty <= 0
            ):
                self.entry_expired = True
                self.entry_fill_valid = False
                try:
                    cancel_order_by_orderid(self.entry_order_id)
                except Exception as error:
                    print("时段结束撤入场单失败：", error)
                self.state = self.ENTRY_CANCEL_PENDING

            if self.state == self.ENTRY_ACTIVE:
                if entry_filled_qty > 0 or strategy_qty > 0:
                    self.entry_fill_valid = minute_of_day <= self.entry_expire_minute

                    if entry_fully_filled:
                        if self.entry_fill_valid:
                            self.state = self.ENTRY_SYNC_VALID
                            print("Buy Stop 在有效窗口内全部成交")
                        else:
                            self.operational_error_today = True
                            self.state = self.ENTRY_SYNC_LATE
                            print("Buy Stop 过期后成交，准备退出")
                    else:
                        try:
                            cancel_order_by_orderid(self.entry_order_id)
                        except Exception as error:
                            print("撤销部分成交买单失败：", error)
                        self.entry_cancel_wait_count = 0
                        self.state = self.ENTRY_CANCEL_PENDING

                    return

                if entry_cancel_terminal:
                    self.entry_order_id = ""
                    self.entry_expire_minute = -1
                    self.entry_fill_valid = False
                    self.entry_expired = False
                    self.entry_cancel_wait_count = 0

                    if self.signal_attempts >= self.MAX_SIGNAL_ATTEMPTS:
                        self.state = self.WAIT_H1
                        self.first_bottom_low = 0.0
                        self.h1_high = 0.0
                        self.h1_low = 0.0
                        self.h1_midpoint = 0.0
                        self.neckline_high = 0.0
                        self.leg1_start_high = 0.0
                        self.leg1_distance = 0.0
                        self.leg1_avg_bear_body = 0.0
                        self.leg1_bars = 0
                        self.h1_wait_bars = 0
                        self.h1_separated = False
                        self.second_leg_bars = 0
                        self.signal_attempts = 0
                    else:
                        self.state = self.WAIT_SECOND_BOTTOM

                    return

                if minute_of_day >= self.entry_expire_minute:
                    self.entry_expired = True
                    self.entry_fill_valid = False
                    try:
                        cancel_order_by_orderid(self.entry_order_id)
                    except Exception as error:
                        print("撤销过期 Buy Stop 失败：", error)
                    self.entry_cancel_wait_count = 0
                    self.state = self.ENTRY_CANCEL_PENDING
                    print("下一根 5 分钟 K 未触发，发送撤单")
                    return

                return

            if self.state == self.ENTRY_CANCEL_PENDING:
                self.entry_cancel_wait_count += 1

                if entry_filled_qty > 0 or strategy_qty > 0:
                    if not self.entry_expired:
                        self.entry_fill_valid = True

                if entry_fully_filled:
                    if self.entry_fill_valid:
                        self.state = self.ENTRY_SYNC_VALID
                    else:
                        self.operational_error_today = True
                        self.state = self.ENTRY_SYNC_LATE
                    return

                if entry_cancel_terminal:
                    if entry_filled_qty > 0 or strategy_qty > 0:
                        if self.entry_fill_valid:
                            self.state = self.ENTRY_SYNC_VALID
                        else:
                            self.operational_error_today = True
                            self.state = self.ENTRY_SYNC_LATE
                    else:
                        self.entry_order_id = ""
                        self.entry_expire_minute = -1
                        self.entry_fill_valid = False
                        self.entry_expired = False
                        self.entry_cancel_wait_count = 0

                        if self.signal_attempts >= self.MAX_SIGNAL_ATTEMPTS:
                            self.state = self.WAIT_H1
                            self.first_bottom_low = 0.0
                            self.h1_high = 0.0
                            self.h1_low = 0.0
                            self.h1_midpoint = 0.0
                            self.neckline_high = 0.0
                            self.leg1_start_high = 0.0
                            self.leg1_distance = 0.0
                            self.leg1_avg_bear_body = 0.0
                            self.leg1_bars = 0
                            self.h1_wait_bars = 0
                            self.h1_separated = False
                            self.second_leg_bars = 0
                            self.signal_attempts = 0
                        else:
                            self.state = self.WAIT_SECOND_BOTTOM
                    return

                try:
                    cancel_order_by_orderid(self.entry_order_id)
                except Exception as error:
                    print("重复确认撤入场单失败：", error)

                if self.entry_cancel_wait_count >= self.CANCEL_WARNING_BARS:
                    print("警告：Buy Stop 撤单长时间未确认：", self.entry_order_id)

                return

            if self.state in (self.ENTRY_SYNC_VALID, self.ENTRY_SYNC_LATE):
                if strategy_qty <= 0:
                    return

                entry_avg_price = 0.0
                try:
                    entry_avg_price = order_filled_avg_price(self.entry_order_id)
                except Exception as error:
                    print("查询入场成交均价失败：", error)

                if entry_avg_price <= 0:
                    entry_avg_price = self.planned_entry

                actual_r = entry_avg_price - self.planned_stop
                late_or_bad_entry = self.state == self.ENTRY_SYNC_LATE

                if actual_r <= 0:
                    late_or_bad_entry = True

                if (
                    entry_avg_price
                    > self.planned_entry + self.MAX_ENTRY_SLIPPAGE_R * self.planned_r
                ):
                    late_or_bad_entry = True
                    self.operational_error_today = True
                    print("实际成交滑点超过限制")

                self.trade_active = True
                self.trade_entry_price = entry_avg_price
                self.trade_entry_qty = strategy_qty
                self.trade_initial_r = actual_r
                self.trade_risk_value = actual_r * strategy_qty
                self.trade_realized_pnl = 0.0
                self.entry_5m_key = current_5m_key
                self.hold_5m_bars = 0
                self.mfe_price = entry_avg_price
                self.profit_protection_stage = 0
                self.active_stop = self.planned_stop
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.stop_accounted_fill = 0.0
                self.stop_partial_mismatch_count = 0
                self.stop_replace_exit_pending = False
                self.multi_lot_trade = False
                self.t1_done = False
                self.t1_price = 0.0
                self.t1_qty = 0.0
                self.t2_price = 0.0
                self.single_target_price = 0.0

                self.measured_target_price = self.measured_move_target - self.tick
                self.important_low_armed = False
                self.important_low_count = 0
                self.last_important_low = 0.0
                self.pullback_active = False
                self.pullback_bars = 0
                self.pullback_low = 0.0
                self.daily_trade_count += 1

                # 实际成交出现滑点后，Measured Move 仍须提供至少 1.2R 的空间。
                if (
                    self.measured_target_price
                    < entry_avg_price + self.MEASURED_TARGET_MIN_R * actual_r
                ):
                    late_or_bad_entry = True

                self.entry_order_id = ""
                self.entry_expire_minute = -1
                self.entry_fill_valid = False
                self.entry_expired = False
                self.entry_cancel_wait_count = 0

                if late_or_bad_entry or force_flat_time:
                    self.exit_reason = "LATE_OR_BAD_ENTRY"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = strategy_qty
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    self.state = self.EXIT_SUBMIT
                    return

                try:
                    stop_id = place_stop(
                        symbol=self.symbol,
                        aux_price=self.active_stop,
                        qty=strategy_qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC
                    )
                except Exception as error:
                    print("提交保护性止损失败：", error)
                    stop_id = ""

                if stop_id == "":
                    self.operational_error_today = True
                    self.exit_reason = "STOP_SUBMIT_FAILED"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.state = self.EXIT_SUBMIT
                    return

                self.stop_order_id = stop_id
                self.stop_target_qty = strategy_qty
                self.stop_accounted_fill = 0.0
                self.state = self.HOLDING

                print(
                    "建立交易：",
                    "entry=", self.trade_entry_price,
                    "qty=", strategy_qty,
                    "R=", self.trade_initial_r,
                    "stop=", self.active_stop,
                    "measured_target=", self.measured_target_price,
                    "protect_R=", self.PROTECT_SIGNAL_ARM_R,
                    "breakeven_R=", self.BREAKEVEN_ARM_R,
                    "important_low_arm_R=", self.IMPORTANT_LOW_ARM_R
                )
                return

        # ============================================================
        # 3. 软件协调退出：先撤止损，再市价卖出
        # ============================================================
        if self.state == self.EXIT_CANCEL_STOP:
            stop_status = None
            stop_total_qty = 0.0
            stop_filled_qty = 0.0
            stop_avg_price = 0.0

            if self.stop_order_id != "":
                try:
                    stop_status = order_status(self.stop_order_id)
                except Exception as error:
                    print("查询止损状态失败：", error)
                try:
                    stop_total_qty = order_qty(self.stop_order_id)
                except Exception as error:
                    print("查询止损数量失败：", error)
                try:
                    stop_filled_qty = order_filled_qty(self.stop_order_id)
                except Exception as error:
                    print("查询止损成交数量失败：", error)
                try:
                    stop_avg_price = order_filled_avg_price(self.stop_order_id)
                except Exception:
                    stop_avg_price = 0.0

            if stop_filled_qty > self.stop_accounted_fill and stop_avg_price > 0:
                delta_fill = stop_filled_qty - self.stop_accounted_fill
                self.trade_realized_pnl += (
                    stop_avg_price - self.trade_entry_price
                ) * delta_fill
                self.stop_accounted_fill = stop_filled_qty

            if strategy_qty <= self.exit_target_remaining_qty:
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.state = self.EXIT_SUBMIT
                return

            stop_cancel_terminal = (
                stop_status == OrderStatus.CANCELLED_PART
                or stop_status == OrderStatus.CANCELLED_ALL
                or stop_status == OrderStatus.FAILED
                or stop_status == OrderStatus.DISABLED
            )

            if stop_status == OrderStatus.FILLED_ALL:
                return

            if stop_cancel_terminal:
                expected_qty = stop_total_qty - stop_filled_qty
                if expected_qty < 0:
                    expected_qty = 0.0

                if stop_filled_qty > 0 and strategy_qty > expected_qty:
                    self.exit_stop_terminal_wait_count += 1
                    if self.exit_stop_terminal_wait_count < self.POSITION_SYNC_WARNING_BARS:
                        return

                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.exit_stop_terminal_wait_count = 0
                self.state = self.EXIT_SUBMIT
                return

            try:
                cancel_order_by_orderid(self.stop_order_id)
            except Exception as error:
                print("协调退出撤止损失败：", error)

            self.exit_cancel_wait_count += 1
            if self.exit_cancel_wait_count >= self.CANCEL_WARNING_BARS:
                print("警告：协调退出撤止损长时间未确认")
            return

        if self.state == self.EXIT_SUBMIT:
            qty_to_sell = strategy_qty - self.exit_target_remaining_qty

            if qty_to_sell <= 0:
                if strategy_qty <= 0:
                    # 交易完成。
                    trade_r = 0.0
                    if self.trade_risk_value > 0:
                        trade_r = self.trade_realized_pnl / self.trade_risk_value
                    self.daily_realized_r += trade_r
                    if trade_r < 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0
                    print("交易结束：", self.exit_reason, "R=", trade_r)

                    self.trade_active = False
                    self.state = self.WAIT_H1
                    self.first_bottom_low = 0.0
                    self.h1_high = 0.0
                    self.h1_low = 0.0
                    self.h1_midpoint = 0.0
                    self.neckline_high = 0.0
                    self.leg1_start_high = 0.0
                    self.leg1_distance = 0.0
                    self.leg1_avg_bear_body = 0.0
                    self.leg1_bars = 0
                    self.h1_wait_bars = 0
                    self.h1_separated = False
                    self.second_leg_bars = 0
                    self.signal_attempts = 0
                    self.signal_high = 0.0
                    self.signal_low = 0.0
                    self.signal_midpoint = 0.0
                    self.second_bottom_low = 0.0
                    self.measured_move_target = 0.0
                    self.planned_entry = 0.0
                    self.planned_stop = 0.0
                    self.planned_r = 0.0
                    self.planned_qty = 0.0
                    self.trade_entry_price = 0.0
                    self.trade_entry_qty = 0.0
                    self.trade_initial_r = 0.0
                    self.trade_risk_value = 0.0
                    self.trade_realized_pnl = 0.0
                    self.entry_5m_key = ""
                    self.hold_5m_bars = 0
                    self.mfe_price = 0.0
                    self.active_stop = 0.0
                    self.stop_order_id = ""
                    self.stop_target_qty = 0.0
                    self.stop_accounted_fill = 0.0
                    self.stop_partial_mismatch_count = 0
                    self.multi_lot_trade = False
                    self.t1_done = False
                    self.t1_price = 0.0
                    self.t1_qty = 0.0
                    self.t2_price = 0.0
                    self.single_target_price = 0.0
                    self.measured_target_price = 0.0
                    self.important_low_armed = False
                    self.important_low_count = 0
                    self.last_important_low = 0.0
                    self.pullback_active = False
                    self.pullback_bars = 0
                    self.pullback_low = 0.0
                    self.pending_stop_price = 0.0
                    self.stop_replace_exit_pending = False
                    self.exit_reason = ""
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = 0.0
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    self.force_exit_pending = False
                    return

                if self.exit_mark_t1:
                    self.t1_done = True

                self.exit_reason = ""
                self.exit_target_remaining_qty = 0.0
                self.exit_mark_t1 = False
                self.exit_order_id = ""
                self.exit_submitted_qty = 0.0
                self.exit_position_before = 0.0
                self.exit_accounted_fill = 0.0
                self.exit_wait_count = 0
                self.exit_cancel_wait_count = 0
                self.exit_stop_terminal_wait_count = 0
                self.state = self.HOLDING

                try:
                    stop_id = place_stop(
                        symbol=self.symbol,
                        aux_price=self.active_stop,
                        qty=strategy_qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC
                    )
                except Exception as error:
                    print("退出后重挂止损失败：", error)
                    stop_id = ""

                if stop_id == "":
                    self.operational_error_today = True
                    self.exit_reason = "STOP_RESUBMIT_FAILED"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.state = self.EXIT_SUBMIT
                    return

                self.stop_order_id = stop_id
                self.stop_target_qty = strategy_qty
                self.stop_accounted_fill = 0.0
                return

            try:
                exit_id = place_market(
                    symbol=self.symbol,
                    qty=qty_to_sell,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
            except Exception as error:
                print("提交退出市价单失败：", error)
                exit_id = ""

            if exit_id == "":
                self.operational_error_today = True
                return

            self.exit_order_id = exit_id
            self.exit_submitted_qty = qty_to_sell
            self.exit_position_before = strategy_qty
            self.exit_accounted_fill = 0.0
            self.exit_wait_count = 0
            self.state = self.EXIT_WAIT_FILL
            print("提交退出订单：", self.exit_reason, qty_to_sell)
            return

        if self.state == self.EXIT_WAIT_FILL:
            exit_status = None
            exit_filled_qty = 0.0
            exit_avg_price = 0.0

            try:
                exit_status = order_status(self.exit_order_id)
            except Exception as error:
                print("查询退出订单状态失败：", error)
            try:
                exit_filled_qty = order_filled_qty(self.exit_order_id)
            except Exception as error:
                print("查询退出成交数量失败：", error)
            try:
                exit_avg_price = order_filled_avg_price(self.exit_order_id)
            except Exception:
                exit_avg_price = 0.0

            if exit_filled_qty > self.exit_accounted_fill and exit_avg_price > 0:
                delta_fill = exit_filled_qty - self.exit_accounted_fill
                self.trade_realized_pnl += (
                    exit_avg_price - self.trade_entry_price
                ) * delta_fill
                self.exit_accounted_fill = exit_filled_qty

            if strategy_qty <= self.exit_target_remaining_qty:
                if strategy_qty <= 0:
                    trade_r = 0.0
                    if self.trade_risk_value > 0:
                        trade_r = self.trade_realized_pnl / self.trade_risk_value
                    self.daily_realized_r += trade_r
                    if trade_r < 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0
                    print("交易结束：", self.exit_reason, "R=", trade_r)

                    self.trade_active = False
                    self.state = self.WAIT_H1
                    self.first_bottom_low = 0.0
                    self.h1_high = 0.0
                    self.h1_low = 0.0
                    self.h1_midpoint = 0.0
                    self.neckline_high = 0.0
                    self.leg1_start_high = 0.0
                    self.leg1_distance = 0.0
                    self.leg1_avg_bear_body = 0.0
                    self.leg1_bars = 0
                    self.h1_wait_bars = 0
                    self.h1_separated = False
                    self.second_leg_bars = 0
                    self.signal_attempts = 0
                    self.signal_high = 0.0
                    self.signal_low = 0.0
                    self.signal_midpoint = 0.0
                    self.second_bottom_low = 0.0
                    self.measured_move_target = 0.0
                    self.planned_entry = 0.0
                    self.planned_stop = 0.0
                    self.planned_r = 0.0
                    self.planned_qty = 0.0
                    self.trade_entry_price = 0.0
                    self.trade_entry_qty = 0.0
                    self.trade_initial_r = 0.0
                    self.trade_risk_value = 0.0
                    self.trade_realized_pnl = 0.0
                    self.entry_5m_key = ""
                    self.hold_5m_bars = 0
                    self.mfe_price = 0.0
                    self.active_stop = 0.0
                    self.stop_order_id = ""
                    self.stop_target_qty = 0.0
                    self.stop_accounted_fill = 0.0
                    self.stop_partial_mismatch_count = 0
                    self.multi_lot_trade = False
                    self.t1_done = False
                    self.t1_price = 0.0
                    self.t1_qty = 0.0
                    self.t2_price = 0.0
                    self.single_target_price = 0.0
                    self.measured_target_price = 0.0
                    self.important_low_armed = False
                    self.important_low_count = 0
                    self.last_important_low = 0.0
                    self.pullback_active = False
                    self.pullback_bars = 0
                    self.pullback_low = 0.0
                    self.pending_stop_price = 0.0
                    self.stop_replace_exit_pending = False
                    self.exit_reason = ""
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = 0.0
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    self.force_exit_pending = False
                    return

                if self.exit_mark_t1:
                    self.t1_done = True

                self.exit_reason = ""
                self.exit_target_remaining_qty = 0.0
                self.exit_mark_t1 = False
                self.exit_order_id = ""
                self.exit_submitted_qty = 0.0
                self.exit_position_before = 0.0
                self.exit_accounted_fill = 0.0
                self.exit_wait_count = 0
                self.exit_cancel_wait_count = 0
                self.exit_stop_terminal_wait_count = 0
                self.state = self.HOLDING

                try:
                    stop_id = place_stop(
                        symbol=self.symbol,
                        aux_price=self.active_stop,
                        qty=strategy_qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC
                    )
                except Exception as error:
                    print("退出后重挂止损失败：", error)
                    stop_id = ""

                if stop_id == "":
                    self.operational_error_today = True
                    self.exit_reason = "STOP_RESUBMIT_FAILED"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.state = self.EXIT_SUBMIT
                    return

                self.stop_order_id = stop_id
                self.stop_target_qty = strategy_qty
                self.stop_accounted_fill = 0.0
                return

            exit_cancel_terminal = (
                exit_status == OrderStatus.CANCELLED_PART
                or exit_status == OrderStatus.CANCELLED_ALL
                or exit_status == OrderStatus.FAILED
                or exit_status == OrderStatus.DISABLED
            )

            exit_fully_filled = (
                exit_status == OrderStatus.FILLED_ALL
                or (
                    self.exit_submitted_qty > 0
                    and exit_filled_qty >= self.exit_submitted_qty
                )
            )

            if exit_fully_filled:
                self.exit_wait_count += 1
                if self.exit_wait_count >= self.POSITION_SYNC_WARNING_BARS:
                    print("警告：退出订单已成交但持仓尚未同步")
                return

            if exit_cancel_terminal:
                self.exit_wait_count += 1
                if exit_filled_qty > 0 and self.exit_wait_count < self.POSITION_SYNC_WARNING_BARS:
                    return

                self.exit_order_id = ""
                self.exit_submitted_qty = 0.0
                self.exit_accounted_fill = 0.0
                self.exit_wait_count = 0
                self.state = self.EXIT_SUBMIT
                return

            return

        # ============================================================
        # 4. 保护性止损替换及止损成交同步
        # ============================================================
        if self.state == self.STOP_REPLACE_CANCEL:
            stop_status = None
            stop_filled_qty = 0.0
            stop_avg_price = 0.0

            try:
                stop_status = order_status(self.stop_order_id)
            except Exception as error:
                print("查询移动止损状态失败：", error)
            try:
                stop_filled_qty = order_filled_qty(self.stop_order_id)
            except Exception:
                stop_filled_qty = 0.0
            try:
                stop_avg_price = order_filled_avg_price(self.stop_order_id)
            except Exception:
                stop_avg_price = 0.0

            # 移动止损撤单确认期间仍监控最终目标，避免因状态切换漏掉 Measured Move。
            if not self.stop_replace_exit_pending:
                replace_one_minute_high = 0.0
                try:
                    replace_one_minute_high = bar_high(
                        self.symbol,
                        bar_type=self.EXEC_BAR,
                        select=self.CLOSED_SHIFT,
                        session_type=self.SESSION
                    )
                except Exception:
                    replace_one_minute_high = 0.0

                if (
                    self.measured_target_price > 0
                    and replace_one_minute_high >= self.measured_target_price
                ):
                    self.stop_replace_exit_pending = True
                    self.exit_reason = "MEASURED_MOVE"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    print("移动止损撤单期间触及 Measured Move，撤单后直接退出")
                elif self.force_exit_pending:
                    self.stop_replace_exit_pending = True
                    self.exit_reason = "SESSION_FORCE_FLAT"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False

            if stop_filled_qty > self.stop_accounted_fill and stop_avg_price > 0:
                delta_fill = stop_filled_qty - self.stop_accounted_fill
                self.trade_realized_pnl += (
                    stop_avg_price - self.trade_entry_price
                ) * delta_fill
                self.stop_accounted_fill = stop_filled_qty

            if strategy_qty <= 0:
                trade_r = 0.0
                if self.trade_risk_value > 0:
                    trade_r = self.trade_realized_pnl / self.trade_risk_value
                self.daily_realized_r += trade_r
                if trade_r < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                print("交易结束：STOP_DURING_REPLACE R=", trade_r)
                self.trade_active = False
                self.state = self.WAIT_H1
                self.stop_order_id = ""
                self.force_exit_pending = False
                return

            stop_cancel_terminal = (
                stop_status == OrderStatus.CANCELLED_PART
                or stop_status == OrderStatus.CANCELLED_ALL
                or stop_status == OrderStatus.FAILED
                or stop_status == OrderStatus.DISABLED
            )

            if stop_status == OrderStatus.FILLED_ALL:
                self.state = self.STOP_FILL_SYNC
                self.stop_sync_wait_count = 0
                return

            if stop_cancel_terminal:
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.stop_replace_wait_count = 0

                if self.stop_replace_exit_pending:
                    self.pending_stop_price = 0.0
                    self.stop_replace_exit_pending = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = strategy_qty
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    self.state = self.EXIT_SUBMIT
                    return

                self.active_stop = self.pending_stop_price
                self.pending_stop_price = 0.0
                self.stop_replace_exit_pending = False

                try:
                    stop_id = place_stop(
                        symbol=self.symbol,
                        aux_price=self.active_stop,
                        qty=strategy_qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC
                    )
                except Exception as error:
                    print("重挂移动止损失败：", error)
                    stop_id = ""

                if stop_id == "":
                    self.operational_error_today = True
                    self.exit_reason = "STOP_REPLACE_FAILED"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.state = self.EXIT_SUBMIT
                    return

                self.stop_order_id = stop_id
                self.stop_target_qty = strategy_qty
                self.stop_accounted_fill = 0.0
                self.state = self.HOLDING
                return

            try:
                cancel_order_by_orderid(self.stop_order_id)
            except Exception as error:
                print("确认撤旧止损失败：", error)

            self.stop_replace_wait_count += 1
            if self.stop_replace_wait_count >= self.CANCEL_WARNING_BARS:
                print("警告：移动止损撤单长时间未确认")
            return

        if self.state == self.STOP_FILL_SYNC:
            stop_filled_qty = 0.0
            stop_avg_price = 0.0
            try:
                stop_filled_qty = order_filled_qty(self.stop_order_id)
            except Exception:
                stop_filled_qty = 0.0
            try:
                stop_avg_price = order_filled_avg_price(self.stop_order_id)
            except Exception:
                stop_avg_price = 0.0

            if stop_filled_qty > self.stop_accounted_fill and stop_avg_price > 0:
                delta_fill = stop_filled_qty - self.stop_accounted_fill
                self.trade_realized_pnl += (
                    stop_avg_price - self.trade_entry_price
                ) * delta_fill
                self.stop_accounted_fill = stop_filled_qty

            if strategy_qty <= 0:
                trade_r = 0.0
                if self.trade_risk_value > 0:
                    trade_r = self.trade_realized_pnl / self.trade_risk_value
                self.daily_realized_r += trade_r
                if trade_r < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                print("交易结束：PROTECTIVE_STOP R=", trade_r)

                self.trade_active = False
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                self.trade_entry_price = 0.0
                self.trade_entry_qty = 0.0
                self.trade_initial_r = 0.0
                self.trade_risk_value = 0.0
                self.trade_realized_pnl = 0.0
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.stop_accounted_fill = 0.0
                self.force_exit_pending = False
                return

            self.stop_sync_wait_count += 1
            if self.stop_sync_wait_count >= self.POSITION_SYNC_WARNING_BARS:
                print("警告：止损已成交但持仓尚未同步")
            return

        # ============================================================
        # 5. 正常持仓管理
        # ============================================================
        if self.state == self.HOLDING:
            if strategy_qty <= 0:
                # 持仓已归零，读取止损成交并结算。
                stop_filled_qty = 0.0
                stop_avg_price = 0.0
                if self.stop_order_id != "":
                    try:
                        stop_filled_qty = order_filled_qty(self.stop_order_id)
                    except Exception:
                        stop_filled_qty = 0.0
                    try:
                        stop_avg_price = order_filled_avg_price(self.stop_order_id)
                    except Exception:
                        stop_avg_price = 0.0
                if stop_filled_qty > self.stop_accounted_fill and stop_avg_price > 0:
                    delta_fill = stop_filled_qty - self.stop_accounted_fill
                    self.trade_realized_pnl += (
                        stop_avg_price - self.trade_entry_price
                    ) * delta_fill
                    self.stop_accounted_fill = stop_filled_qty

                trade_r = 0.0
                if self.trade_risk_value > 0:
                    trade_r = self.trade_realized_pnl / self.trade_risk_value
                self.daily_realized_r += trade_r
                if trade_r < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
                print("交易结束：POSITION_FLAT R=", trade_r)

                self.trade_active = False
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.stop_accounted_fill = 0.0
                self.force_exit_pending = False
                return

            if self.force_exit_pending:
                self.exit_reason = "SESSION_FORCE_FLAT"
                self.exit_target_remaining_qty = 0.0
                self.exit_mark_t1 = False
                self.exit_order_id = ""
                self.exit_submitted_qty = 0.0
                self.exit_position_before = strategy_qty
                self.exit_accounted_fill = 0.0
                self.exit_wait_count = 0
                self.exit_cancel_wait_count = 0
                self.exit_stop_terminal_wait_count = 0

                if self.stop_order_id != "":
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("强制平仓撤止损失败：", error)
                    self.state = self.EXIT_CANCEL_STOP
                else:
                    self.state = self.EXIT_SUBMIT
                return

            # 更新 MFE。
            try:
                one_minute_high = bar_high(
                    self.symbol,
                    bar_type=self.EXEC_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                one_minute_low = bar_low(
                    self.symbol,
                    bar_type=self.EXEC_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
            except Exception as error:
                print("读取 1 分钟 K 失败：", error)
                return

            if one_minute_high > self.mfe_price:
                self.mfe_price = one_minute_high

            current_mfe_r = 0.0
            if self.trade_initial_r > 0:
                current_mfe_r = (
                    self.mfe_price - self.trade_entry_price
                ) / self.trade_initial_r

            # V1.5 两级利润保护。若一次跳涨越过 1R，直接使用成本保护。
            protection_candidate = 0.0
            protection_stage = self.profit_protection_stage

            if (
                self.profit_protection_stage < 2
                and current_mfe_r >= self.BREAKEVEN_ARM_R
            ):
                protection_candidate = (
                    self.trade_entry_price
                    + self.BREAKEVEN_BUFFER_TICKS * self.tick
                )
                protection_stage = 2
            elif (
                self.profit_protection_stage < 1
                and current_mfe_r >= self.PROTECT_SIGNAL_ARM_R
            ):
                protection_candidate = self.signal_low - self.tick
                protection_stage = 1

            if protection_stage > self.profit_protection_stage:
                if protection_candidate <= self.active_stop:
                    # 当前止损已经高于本级保护位，无需重复改单。
                    self.profit_protection_stage = protection_stage
                elif self.stop_order_id != "":
                    # 只有存在可撤销的保护性止损时才推进阶段，避免空订单进入撤单状态。
                    self.profit_protection_stage = protection_stage
                    self.pending_stop_price = protection_candidate
                    self.stop_replace_wait_count = 0
                    self.stop_replace_exit_pending = False
                    print(
                        "利润保护上移止损：",
                        "stage=", self.profit_protection_stage,
                        "MFE_R=", current_mfe_r,
                        "old_stop=", self.active_stop,
                        "new_stop=", protection_candidate
                    )
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("利润保护撤旧止损失败：", error)
                    self.state = self.STOP_REPLACE_CANCEL
                    return

            # 保护性止损订单状态管理。
            stop_status = None
            stop_total_qty = 0.0
            stop_filled_qty = 0.0
            stop_avg_price = 0.0

            if self.stop_order_id == "":
                try:
                    stop_id = place_stop(
                        symbol=self.symbol,
                        aux_price=self.active_stop,
                        qty=strategy_qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC
                    )
                except Exception as error:
                    print("补挂保护性止损失败：", error)
                    stop_id = ""

                if stop_id == "":
                    self.operational_error_today = True
                    self.exit_reason = "STOP_MISSING"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.state = self.EXIT_SUBMIT
                    return

                self.stop_order_id = stop_id
                self.stop_target_qty = strategy_qty
                self.stop_accounted_fill = 0.0
                return

            try:
                stop_status = order_status(self.stop_order_id)
            except Exception as error:
                print("查询保护止损状态失败：", error)
            try:
                stop_total_qty = order_qty(self.stop_order_id)
            except Exception:
                stop_total_qty = 0.0
            try:
                stop_filled_qty = order_filled_qty(self.stop_order_id)
            except Exception:
                stop_filled_qty = 0.0
            try:
                stop_avg_price = order_filled_avg_price(self.stop_order_id)
            except Exception:
                stop_avg_price = 0.0

            if stop_filled_qty > self.stop_accounted_fill and stop_avg_price > 0:
                delta_fill = stop_filled_qty - self.stop_accounted_fill
                self.trade_realized_pnl += (
                    stop_avg_price - self.trade_entry_price
                ) * delta_fill
                self.stop_accounted_fill = stop_filled_qty

            if stop_status == OrderStatus.FILLED_ALL:
                self.state = self.STOP_FILL_SYNC
                self.stop_sync_wait_count = 0
                return

            stop_cancel_terminal = (
                stop_status == OrderStatus.CANCELLED_PART
                or stop_status == OrderStatus.CANCELLED_ALL
                or stop_status == OrderStatus.FAILED
                or stop_status == OrderStatus.DISABLED
            )

            if stop_cancel_terminal:
                self.stop_order_id = ""
                self.stop_target_qty = 0.0
                self.stop_accounted_fill = 0.0
                return

            if stop_status == OrderStatus.FILLED_PART:
                remaining_stop_qty = stop_total_qty - stop_filled_qty
                if remaining_stop_qty < 0:
                    remaining_stop_qty = 0.0

                if abs(remaining_stop_qty - strategy_qty) > 0.000001:
                    self.stop_partial_mismatch_count += 1
                else:
                    self.stop_partial_mismatch_count = 0

                if self.stop_partial_mismatch_count > self.STOP_PARTIAL_SYNC_GRACE:
                    self.pending_stop_price = self.active_stop
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("止损数量不一致撤单失败：", error)
                    self.stop_replace_wait_count = 0
                    self.stop_replace_exit_pending = False
                    self.state = self.STOP_REPLACE_CANCEL
                    return

            # 同一根 1 分钟 K 同时触及结构止损和 Measured Move 时，保守地等待止损。
            if one_minute_low <= self.active_stop:
                return

            # V1.5：Measured Move 仍是最终主动止盈，途中由两级利润保护和重要底部控制回撤。
            target_triggered = False
            target_remaining_qty = strategy_qty
            target_reason = ""
            target_mark_t1 = False

            if (
                self.measured_target_price > 0
                and one_minute_high >= self.measured_target_price
            ):
                target_triggered = True
                target_remaining_qty = 0.0
                target_reason = "MEASURED_MOVE"

            if target_triggered:
                self.exit_reason = target_reason
                self.exit_target_remaining_qty = target_remaining_qty
                self.exit_mark_t1 = target_mark_t1
                self.exit_order_id = ""
                self.exit_submitted_qty = 0.0
                self.exit_position_before = strategy_qty
                self.exit_accounted_fill = 0.0
                self.exit_wait_count = 0
                self.exit_cancel_wait_count = 0
                self.exit_stop_terminal_wait_count = 0

                try:
                    cancel_order_by_orderid(self.stop_order_id)
                except Exception as error:
                    print("止盈前撤止损失败：", error)
                self.state = self.EXIT_CANCEL_STOP
                return

            # 5 分钟持仓管理。
            if is_new_5m and self.entry_5m_key != current_5m_key:
                self.hold_5m_bars += 1

                try:
                    signal_open0 = bar_open(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT,
                        session_type=self.SESSION
                    )
                    signal_close0 = bar_close(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT,
                        session_type=self.SESSION
                    )
                    signal_high0 = bar_high(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT,
                        session_type=self.SESSION
                    )
                    signal_low0 = bar_low(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT,
                        session_type=self.SESSION
                    )
                    signal_close1 = bar_close(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT + 1,
                        session_type=self.SESSION
                    )
                    signal_high1 = bar_high(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT + 1,
                        session_type=self.SESSION
                    )
                    signal_low1 = bar_low(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT + 1,
                        session_type=self.SESSION
                    )
                except Exception as error:
                    print("读取持仓管理 5 分钟 K 失败：", error)
                    return

                mfe_r = 0.0
                if self.trade_initial_r > 0:
                    mfe_r = (
                        self.mfe_price - self.trade_entry_price
                    ) / self.trade_initial_r

                if (
                    self.hold_5m_bars <= self.FAST_FAIL_MAX_BARS
                    and mfe_r < self.FAST_FAIL_MFE_R
                    and signal_close0 < signal_open0
                    and signal_close0 < self.signal_midpoint
                    and signal_close0 < self.trade_entry_price
                ):
                    self.exit_reason = "FAST_FAILURE"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = strategy_qty
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("快速失败撤止损失败：", error)
                    self.state = self.EXIT_CANCEL_STOP
                    return

                if (
                    self.hold_5m_bars >= self.NO_PROGRESS_BARS
                    and mfe_r < self.NO_PROGRESS_MFE_R
                ):
                    self.exit_reason = "NO_PROGRESS"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = strategy_qty
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("无进展退出撤止损失败：", error)
                    self.state = self.EXIT_CANCEL_STOP
                    return

                if self.hold_5m_bars >= self.MAX_HOLD_5M_BARS:
                    self.exit_reason = "MAX_HOLD_TIME"
                    self.exit_target_remaining_qty = 0.0
                    self.exit_mark_t1 = False
                    self.exit_order_id = ""
                    self.exit_submitted_qty = 0.0
                    self.exit_position_before = strategy_qty
                    self.exit_accounted_fill = 0.0
                    self.exit_wait_count = 0
                    self.exit_cancel_wait_count = 0
                    self.exit_stop_terminal_wait_count = 0
                    try:
                        cancel_order_by_orderid(self.stop_order_id)
                    except Exception as error:
                        print("最长持仓退出撤止损失败：", error)
                    self.state = self.EXIT_CANCEL_STOP
                    return

                # V1.5：浮盈达到 0.6R 后，使用确认的重要 Higher Low 继续上移止损。
                if (
                    not self.important_low_armed
                    and mfe_r >= self.IMPORTANT_LOW_ARM_R
                ):
                    self.important_low_armed = True
                    print(
                        "重要底部跟踪已启动：",
                        "MFE_R=", mfe_r,
                        "active_stop=", self.active_stop
                    )

                if self.important_low_armed:
                    pullback_bar = (
                        signal_close0 < signal_open0
                        or signal_close0 < signal_close1
                        or signal_low0 < signal_low1
                    )

                    if not self.pullback_active:
                        if pullback_bar:
                            self.pullback_active = True
                            self.pullback_bars = 1
                            self.pullback_low = signal_low0
                    else:
                        if (
                            pullback_bar
                            and self.pullback_bars < self.IMPORTANT_LOW_MAX_PULLBACK_BARS
                        ):
                            self.pullback_bars += 1
                            if signal_low0 < self.pullback_low:
                                self.pullback_low = signal_low0
                        else:
                            # 当前多头 K 收盘越过前一根 K 高点，确认回调低点。
                            confirmed_break = (
                                signal_close0 > signal_open0
                                and signal_close0 > signal_high1
                            )

                            if confirmed_break:
                                new_stop = self.pullback_low - self.tick

                                if (
                                    self.pullback_bars >= 1
                                    and self.pullback_bars <= self.IMPORTANT_LOW_MAX_PULLBACK_BARS
                                    and self.pullback_low > self.second_bottom_low
                                    and self.pullback_low > self.last_important_low
                                    and new_stop > self.active_stop
                                ):
                                    self.last_important_low = self.pullback_low
                                    self.important_low_count += 1
                                    self.pending_stop_price = new_stop
                                    print(
                                        "确认重要底部：",
                                        "important_low=", self.last_important_low,
                                        "new_stop=", new_stop,
                                        "count=", self.important_low_count
                                    )
                                    try:
                                        cancel_order_by_orderid(self.stop_order_id)
                                    except Exception as error:
                                        print("重要底部上移止损撤旧单失败：", error)
                                    self.stop_replace_wait_count = 0
                                    self.stop_replace_exit_pending = False
                                    self.state = self.STOP_REPLACE_CANCEL
                                    self.pullback_active = False
                                    self.pullback_bars = 0
                                    self.pullback_low = 0.0
                                    return

                            # 未确认突破，或回调超过 4 根，丢弃本次候选底部。
                            self.pullback_active = False
                            self.pullback_bars = 0
                            self.pullback_low = 0.0

            return

        # ============================================================
        # 6. 空仓形态不跨午休和收盘
        # ============================================================
        if (
            self.state in (
                self.WAIT_H1,
                self.WAIT_H1_FAILURE,
                self.WAIT_SECOND_BOTTOM
            )
            and flat_pattern_block
        ):
            if self.state != self.WAIT_H1:
                print("离开允许开仓时段，重置未完成结构")
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
            return

        if not is_new_5m:
            return

        if in_entry_window:
            self.diag_5m_bars += 1

        # ============================================================
        # 7. 读取最近 20 根 5 分钟 K，计算中位区间 MR20
        # ============================================================
        ranges = []

        for offset in range(0, self.MR_LOOKBACK):
            try:
                o = bar_open(
                    self.symbol,
                    bar_type=self.SIGNAL_BAR,
                    select=self.CLOSED_SHIFT + offset,
                    session_type=self.SESSION
                )
                c = bar_close(
                    self.symbol,
                    bar_type=self.SIGNAL_BAR,
                    select=self.CLOSED_SHIFT + offset,
                    session_type=self.SESSION
                )
                h = bar_high(
                    self.symbol,
                    bar_type=self.SIGNAL_BAR,
                    select=self.CLOSED_SHIFT + offset,
                    session_type=self.SESSION
                )
                l = bar_low(
                    self.symbol,
                    bar_type=self.SIGNAL_BAR,
                    select=self.CLOSED_SHIFT + offset,
                    session_type=self.SESSION
                )
            except Exception:
                continue

            if (
                o is not None and c is not None
                and h is not None and l is not None
                and o > 0 and c > 0 and h >= l and l > 0
            ):
                rng = h - l
                if rng > 0:
                    ranges.append(rng)

        if len(ranges) < self.MIN_MR_VALID_BARS:
            return

        ranges.sort()
        n_ranges = len(ranges)
        middle = int(n_ranges / 2)

        if n_ranges % 2 == 1:
            self.mr5 = ranges[middle]
        else:
            self.mr5 = (ranges[middle - 1] + ranges[middle]) / 2.0

        mr5 = self.mr5

        try:
            open0 = bar_open(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT,
                session_type=self.SESSION
            )
            close0 = bar_close(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT,
                session_type=self.SESSION
            )
            high0 = bar_high(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT,
                session_type=self.SESSION
            )
            low0 = bar_low(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT,
                session_type=self.SESSION
            )
            open1 = bar_open(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT + 1,
                session_type=self.SESSION
            )
            close1 = bar_close(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT + 1,
                session_type=self.SESSION
            )
            high1 = bar_high(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT + 1,
                session_type=self.SESSION
            )
            low1 = bar_low(
                self.symbol,
                bar_type=self.SIGNAL_BAR,
                select=self.CLOSED_SHIFT + 1,
                session_type=self.SESSION
            )
        except Exception as error:
            print("读取 5 分钟信号 K 失败：", error)
            return

        if self.session_low <= 0 or low0 < self.session_low:
            self.session_low = low0

        if self.DEBUG_EVERY_5M:
            print(
                "5M DEBUG：",
                "state=", self.state,
                "O=", open0,
                "H=", high0,
                "L=", low0,
                "C=", close0,
                "MR20=", mr5
            )

        # ============================================================
        # 8. WAIT_H1：识别第一段下跌后的 H1
        # ============================================================
        if self.state == self.WAIT_H1:
            if not can_open:
                return

            range0 = high0 - low0
            close_location0 = 0.5
            if range0 > 0:
                close_location0 = (close0 - low0) / range0

            h1_basic = (
                close0 > open0
                and high0 > high1
                and close_location0 >= self.H1_CLOSE_LOCATION_MIN
                and range0 >= self.H1_RANGE_MIN_MR * mr5
                and range0 <= self.H1_RANGE_MAX_MR * mr5
            )

            if not h1_basic:
                return

            self.diag_h1_basic += 1

            found_leg = False
            found_count = 0
            found_start_high = 0.0
            found_bottom_low = 0.0
            found_distance = 0.0
            found_avg_bear_body = 0.0

            for count in range(self.LEG1_MIN_BARS, self.LEG1_MAX_BARS + 1):
                enough_data = True
                leg_start_high = 0.0
                bottom_low = low0
                bear_body_sum = 0.0
                bear_body_count = 0
                lower_highs = 0
                lower_lows = 0

                for offset in range(1, count + 1):
                    try:
                        oo = bar_open(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + offset,
                            session_type=self.SESSION
                        )
                        cc = bar_close(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + offset,
                            session_type=self.SESSION
                        )
                        hh = bar_high(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + offset,
                            session_type=self.SESSION
                        )
                        ll = bar_low(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + offset,
                            session_type=self.SESSION
                        )
                    except Exception:
                        enough_data = False
                        break

                    if hh <= 0 or ll <= 0 or hh < ll:
                        enough_data = False
                        break

                    if hh > leg_start_high:
                        leg_start_high = hh
                    if ll < bottom_low:
                        bottom_low = ll
                    if cc < oo:
                        body = oo - cc
                        bear_body_sum += body
                        bear_body_count += 1

                if not enough_data:
                    continue

                for older_offset in range(count, 1, -1):
                    newer_offset = older_offset - 1
                    try:
                        older_high = bar_high(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + older_offset,
                            session_type=self.SESSION
                        )
                        newer_high = bar_high(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + newer_offset,
                            session_type=self.SESSION
                        )
                        older_low = bar_low(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + older_offset,
                            session_type=self.SESSION
                        )
                        newer_low = bar_low(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + newer_offset,
                            session_type=self.SESSION
                        )
                    except Exception:
                        enough_data = False
                        break

                    if newer_high < older_high:
                        lower_highs += 1
                    if newer_low < older_low:
                        lower_lows += 1

                if not enough_data:
                    continue

                distance = leg_start_high - bottom_low
                if distance < self.LEG1_MIN_DISTANCE_MR * mr5:
                    continue

                # 不再要求三根 K 的每一步都同时形成严格下降高点和下降低点。
                # 只要下跌距离成立，并至少各出现一次 lower high / lower low。
                normal_leg = count >= 3 and lower_highs >= 1 and lower_lows >= 1
                strong_two_bar = False

                if count == 2:
                    try:
                        o_bar1 = bar_open(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 1,
                            session_type=self.SESSION
                        )
                        c_bar1 = bar_close(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 1,
                            session_type=self.SESSION
                        )
                        h_bar1 = bar_high(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 1,
                            session_type=self.SESSION
                        )
                        l_bar1 = bar_low(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 1,
                            session_type=self.SESSION
                        )
                        o_bar2 = bar_open(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 2,
                            session_type=self.SESSION
                        )
                        c_bar2 = bar_close(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 2,
                            session_type=self.SESSION
                        )
                        h_bar2 = bar_high(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 2,
                            session_type=self.SESSION
                        )
                        l_bar2 = bar_low(
                            self.symbol,
                            bar_type=self.SIGNAL_BAR,
                            select=self.CLOSED_SHIFT + 2,
                            session_type=self.SESSION
                        )
                        strong_two_bar = (
                            c_bar1 < o_bar1
                            and c_bar2 < o_bar2
                            and (h_bar1 - l_bar1) + (h_bar2 - l_bar2)
                            >= self.LEG1_STRONG_TWO_BAR_MR * mr5
                        )
                    except Exception:
                        strong_two_bar = False

                if normal_leg or strong_two_bar:
                    found_leg = True
                    found_count = count
                    found_start_high = leg_start_high
                    found_bottom_low = bottom_low
                    found_distance = distance
                    if bear_body_count > 0:
                        found_avg_bear_body = bear_body_sum / bear_body_count
                    break

            if not found_leg:
                return

            self.diag_leg1_pass += 1

            self.first_bottom_low = found_bottom_low
            self.leg1_start_high = found_start_high
            self.leg1_distance = found_distance
            self.leg1_avg_bear_body = found_avg_bear_body
            self.leg1_bars = found_count

            self.h1_high = high0
            self.h1_low = low0
            self.h1_midpoint = (high0 + low0) / 2.0
            self.neckline_high = high0
            self.h1_wait_bars = 0
            self.h1_separated = False
            self.second_leg_bars = 0
            self.signal_attempts = 0
            self.state = self.WAIT_H1_FAILURE

            print(
                "发现 H1：",
                "first_bottom=", self.first_bottom_low,
                "h1_high=", self.h1_high,
                "leg1_distance=", self.leg1_distance
            )
            return

        # ============================================================
        # 9. WAIT_H1_FAILURE：等待足够反弹后 H1 失败
        # ============================================================
        if self.state == self.WAIT_H1_FAILURE:
            self.h1_wait_bars += 1

            if high0 > self.neckline_high:
                self.neckline_high = high0

            if (
                self.neckline_high - self.first_bottom_low
                >= self.H1_MIN_SEPARATION_MR * mr5
            ):
                self.h1_separated = True

            if close0 > self.h1_high and close1 > self.h1_high:
                print("H1 后直接连续上涨，重置结构")
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                return

            if self.h1_separated and (close0 < self.h1_midpoint or low0 <= self.h1_low):
                self.state = self.WAIT_SECOND_BOTTOM
                self.second_leg_bars = 1
                self.diag_h1_failure += 1
                print("H1 失败，开始寻找第二底")
            elif self.h1_wait_bars > self.H1_MAX_WAIT_BARS:
                print("H1 等待失败超时")
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                return
            else:
                return

        # ============================================================
        # 10. WAIT_SECOND_BOTTOM：识别第二底信号 K
        # ============================================================
        if self.state == self.WAIT_SECOND_BOTTOM:
            if not can_open:
                return

            self.diag_second_scans += 1
            self.second_leg_bars += 1

            max_undercut = 3 * self.tick
            adaptive_undercut = self.MAX_UNDERCUT_MR * mr5
            if adaptive_undercut > max_undercut:
                max_undercut = adaptive_undercut

            if low0 < self.first_bottom_low - max_undercut:
                print("明显跌破第一底，结构失效")
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                return

            if self.second_leg_bars > self.SECOND_BOTTOM_MAX_WAIT_BARS:
                print("等待第二底超时")
                self.state = self.WAIT_H1
                self.first_bottom_low = 0.0
                self.h1_high = 0.0
                self.h1_low = 0.0
                self.h1_midpoint = 0.0
                self.neckline_high = 0.0
                self.leg1_start_high = 0.0
                self.leg1_distance = 0.0
                self.leg1_avg_bear_body = 0.0
                self.leg1_bars = 0
                self.h1_wait_bars = 0
                self.h1_separated = False
                self.second_leg_bars = 0
                self.signal_attempts = 0
                return

            bottom_zone = 2 * self.tick
            adaptive_zone = self.BOTTOM_ZONE_MR * mr5
            if adaptive_zone > bottom_zone:
                bottom_zone = adaptive_zone

            near_bottom = True
            if abs(low0 - self.first_bottom_low) > bottom_zone:
                if low0 >= self.first_bottom_low:
                    near_bottom = False

            range0 = high0 - low0
            close_location0 = 0.5
            if range0 > 0:
                close_location0 = (close0 - low0) / range0

            # 第二段是否过强。
            second_leg_too_strong = False
            leg2_distance = self.neckline_high - low0
            if (
                self.leg1_distance > 0
                and leg2_distance > self.LEG2_MAX_VS_LEG1 * self.leg1_distance
            ):
                second_leg_too_strong = True

            try:
                range1 = high1 - low1
                close_location1 = 0.5
                if range1 > 0:
                    close_location1 = (close1 - low1) / range1
                two_strong_bear = (
                    close0 < open0
                    and range0 >= 1.20 * mr5
                    and close_location0 <= 0.20
                    and close1 < open1
                    and range1 >= 1.20 * mr5
                    and close_location1 <= 0.20
                )
                if two_strong_bear:
                    second_leg_too_strong = True
            except Exception:
                pass

            # 15 分钟强空头过滤。
            strong_bear_15m = False
            try:
                c15_0 = bar_close(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                o15_0 = bar_open(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                h15_0 = bar_high(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                l15_0 = bar_low(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                c15_1 = bar_close(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT + 1,
                    session_type=self.SESSION
                )
                o15_1 = bar_open(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT + 1,
                    session_type=self.SESSION
                )
                h15_1 = bar_high(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT + 1,
                    session_type=self.SESSION
                )
                l15_1 = bar_low(
                    self.symbol,
                    bar_type=self.CONTEXT_BAR,
                    select=self.CLOSED_SHIFT + 1,
                    session_type=self.SESSION
                )

                bear_score = 0
                if c15_0 < o15_0 and c15_1 < o15_1:
                    bear_score += 1

                loc15_0 = 0.5
                loc15_1 = 0.5
                if h15_0 > l15_0:
                    loc15_0 = (c15_0 - l15_0) / (h15_0 - l15_0)
                if h15_1 > l15_1:
                    loc15_1 = (c15_1 - l15_1) / (h15_1 - l15_1)

                if loc15_0 <= 0.25 and loc15_1 <= 0.25:
                    bear_score += 1
                if l15_0 < l15_1:
                    bear_score += 1
                if abs(c15_0 - o15_0) >= abs(c15_1 - o15_1):
                    bear_score += 1

                lower_tail15 = 0.0
                body_low15 = o15_0
                if c15_0 < body_low15:
                    body_low15 = c15_0
                lower_tail15 = body_low15 - l15_0
                tail_ratio15 = 0.0
                if h15_0 > l15_0:
                    tail_ratio15 = lower_tail15 / (h15_0 - l15_0)
                if tail_ratio15 < 0.10:
                    bear_score += 1

                strong_bear_15m = bear_score >= 4
            except Exception as error:
                # 15 分钟数据读取失败时不应把所有信号永久否决。
                strong_bear_15m = False
                if self.DEBUG_EVERY_5M:
                    print("15M 背景读取失败，跳过该过滤：", error)

            # 支撑区域过滤。
            support_tolerance = 2 * self.tick
            adaptive_support = 0.70 * mr5
            if adaptive_support > support_tolerance:
                support_tolerance = adaptive_support

            near_day_low = False
            near_prev_day_low = False
            near_recent_15m_low = False

            if self.session_low > 0:
                near_day_low = abs(low0 - self.session_low) <= support_tolerance

            try:
                prev_day_low = bar_low(
                    self.symbol,
                    bar_type=self.DAY_BAR,
                    select=self.CLOSED_SHIFT,
                    session_type=self.SESSION
                )
                if prev_day_low > 0:
                    near_prev_day_low = abs(low0 - prev_day_low) <= support_tolerance
            except Exception:
                near_prev_day_low = False

            recent_15m_low = 0.0
            recent_15m_high = 0.0
            for offset in range(1, 7):
                try:
                    h15 = bar_high(
                        self.symbol,
                        bar_type=self.CONTEXT_BAR,
                        select=self.CLOSED_SHIFT + offset,
                        session_type=self.SESSION
                    )
                    l15 = bar_low(
                        self.symbol,
                        bar_type=self.CONTEXT_BAR,
                        select=self.CLOSED_SHIFT + offset,
                        session_type=self.SESSION
                    )
                except Exception:
                    continue

                if recent_15m_low <= 0 or l15 < recent_15m_low:
                    recent_15m_low = l15
                if h15 > recent_15m_high:
                    recent_15m_high = h15

            if recent_15m_low > 0:
                near_recent_15m_low = abs(low0 - recent_15m_low) <= support_tolerance

            in_lower_zone = True
            if recent_15m_high > recent_15m_low > 0:
                lower_zone_ceiling = recent_15m_low + 0.50 * (
                    recent_15m_high - recent_15m_low
                )
                in_lower_zone = low0 <= lower_zone_ceiling

            context_support_ok = (
                (near_day_low or near_prev_day_low or near_recent_15m_low)
                and in_lower_zone
            )

            # 不在关键支撑附近时，只允许非常明确的假跌破收回绕过支撑过滤。
            context_body_low = open0
            if close0 < context_body_low:
                context_body_low = close0
            context_lower_tail = context_body_low - low0
            strong_false_break = False
            if range0 > 0:
                strong_false_break = (
                    low0 <= self.first_bottom_low
                    and close0 > self.first_bottom_low
                    and close_location0 >= 0.72
                    and context_lower_tail / range0 >= 0.18
                )

            if self.REQUIRE_CONTEXT_SUPPORT:
                background_ok = (
                    not strong_bear_15m
                    and (context_support_ok or strong_false_break)
                )
            else:
                background_ok = not strong_bear_15m

            if background_ok:
                self.diag_context_pass += 1

            signal_basic = (
                near_bottom
                and low0 >= self.first_bottom_low - max_undercut
                and close0 > open0
                and close0 > close1
                and close_location0 >= self.SIGNAL_CLOSE_LOCATION_MIN
                and range0 >= self.SIGNAL_RANGE_MIN_MR * mr5
                and range0 <= self.SIGNAL_RANGE_MAX_MR * mr5
                and not second_leg_too_strong
                and background_ok
            )

            if not signal_basic:
                return

            self.diag_signal_basic += 1

            pa_score = 0

            if close_location0 >= self.SIGNAL_STRONG_CLOSE_LOCATION:
                pa_score += 1

            body_low0 = open0
            if close0 < body_low0:
                body_low0 = close0
            lower_tail0 = body_low0 - low0
            if range0 > 0 and lower_tail0 / range0 >= self.SIGNAL_LOWER_TAIL_MIN:
                pa_score += 1

            if low0 < self.first_bottom_low and close0 > self.first_bottom_low:
                pa_score += 1

            leg2_bear_sum = 0.0
            leg2_bear_count = 0
            leg2_count = self.second_leg_bars
            if leg2_count < 1:
                leg2_count = 1
            if leg2_count > 6:
                leg2_count = 6

            for offset in range(0, leg2_count):
                try:
                    oo = bar_open(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT + offset,
                        session_type=self.SESSION
                    )
                    cc = bar_close(
                        self.symbol,
                        bar_type=self.SIGNAL_BAR,
                        select=self.CLOSED_SHIFT + offset,
                        session_type=self.SESSION
                    )
                except Exception:
                    continue

                if cc < oo:
                    leg2_bear_sum += oo - cc
                    leg2_bear_count += 1

            leg2_avg_bear = 0.0
            if leg2_bear_count > 0:
                leg2_avg_bear = leg2_bear_sum / leg2_bear_count

            if (
                self.leg1_avg_bear_body > 0
                and leg2_avg_bear > 0
                and leg2_avg_bear < self.leg1_avg_bear_body
            ):
                pa_score += 1

            if close0 > open1:
                pa_score += 1

            if pa_score < self.PA_SCORE_MIN:
                return

            self.diag_pa_pass += 1

            # ========================================================
            # 11. 构建入场、止损、目标和仓位
            # ========================================================
            self.signal_high = high0
            self.signal_low = low0
            self.signal_midpoint = (high0 + low0) / 2.0
            self.second_bottom_low = low0

            # 不使用 round(x, n)，避免平台 round 参数报错。
            self.planned_entry = self.signal_high + self.tick
            self.planned_stop = min(
                self.first_bottom_low,
                self.second_bottom_low
            ) - self.tick
            self.planned_r = self.planned_entry - self.planned_stop

            min_r = self.MIN_R_TICKS * self.tick
            adaptive_min_r = self.MIN_R_MR * mr5
            if adaptive_min_r > min_r:
                min_r = adaptive_min_r
            max_r = self.MAX_R_MR * mr5

            if self.planned_r < min_r or self.planned_r > max_r:
                print("放弃信号：止损距离不合格")
                return

            self.diag_risk_pass += 1

            neckline_space = self.neckline_high - self.planned_entry
            if neckline_space < self.NECKLINE_MIN_SPACE_R * self.planned_r:
                print("放弃信号：颈线空间不足")
                return

            bottom_reference = (
                self.first_bottom_low + self.second_bottom_low
            ) / 2.0
            pattern_height = self.neckline_high - bottom_reference
            self.measured_move_target = self.neckline_high + pattern_height

            if (
                self.measured_move_target
                < self.planned_entry + self.MEASURED_TARGET_MIN_R * self.planned_r
            ):
                print("放弃信号：测量目标不足")
                return

            self.diag_space_pass += 1

            try:
                equity = net_asset(currency=self.account_currency)
            except Exception as error:
                print("获取账户净值失败：", error)
                return

            if equity <= 0:
                return

            risk_budget = equity * self.RISK_PER_TRADE_PCT
            value_budget = equity * self.MAX_POSITION_VALUE_PCT
            qty_by_risk = risk_budget / self.planned_r
            qty_by_value = value_budget / self.planned_entry
            raw_qty = qty_by_risk
            if qty_by_value < raw_qty:
                raw_qty = qty_by_value

            planned_lots = int(raw_qty / self.lot)
            if planned_lots < 1:
                print("放弃信号：风险预算不足一手")
                return

            self.planned_qty = planned_lots * self.lot
            self.diag_budget_pass += 1

            try:
                entry_id = place_stop(
                    symbol=self.symbol,
                    aux_price=self.planned_entry,
                    qty=self.planned_qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
            except Exception as error:
                print("提交 Buy Stop 失败：", error)
                entry_id = ""

            if entry_id == "":
                return

            self.entry_order_id = entry_id
            self.entry_expire_minute = minute_of_day + 5
            self.entry_fill_valid = False
            self.entry_expired = False
            self.entry_cancel_wait_count = 0
            self.signal_attempts += 1
            self.diag_orders += 1
            self.state = self.ENTRY_ACTIVE

            print(
                "挂出 Buy Stop：",
                "entry=", self.planned_entry,
                "stop=", self.planned_stop,
                "qty=", self.planned_qty,
                "expire_minute=", self.entry_expire_minute,
                "PA_score=", pa_score
            )
            return
