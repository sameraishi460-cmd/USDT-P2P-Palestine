"""
AI Trading Engine — Risk Engine

The Risk Engine has FINAL AUTHORITY over all trade decisions.
AI cannot override risk limits.
"""

from datetime import datetime, timedelta


class RiskEngine:
    """Manages all risk controls for the trading bot."""

    def __init__(self, config):
        self.config = config

    def can_trade(self, con, bot_id, symbol, direction, ai_score):
        """
        Master check: can this trade be taken?
        Returns (allowed: bool, reason: str).
        """
        bot = con.execute(
            "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
        ).fetchone()
        if not bot:
            return False, "Bot not found"

        # 1. Bot must be running
        if bot["status"] != "RUNNING":
            return False, f"Bot status: {bot['status']}"

        # 2. Emergency shutdown check
        dd = self._drawdown_pct(bot)
        if dd >= self.config["emergency_shutdown_pct"]:
            return False, f"Emergency shutdown: drawdown {dd:.1f}%"

        # 3. Safe mode check
        if bot["safe_mode"]:
            return False, "Safe mode active"

        # 4. Daily loss limit
        daily_loss = self._daily_loss_pct(bot)
        if daily_loss >= self.config["daily_loss_limit_pct"]:
            return False, f"Daily loss limit reached: {daily_loss:.1f}%"

        # 5. Consecutive losses
        if bot["consecutive_losses"] >= self.config["max_consecutive_losses"]:
            return False, f"Consecutive losses: {bot['consecutive_losses']}"

        # 6. Maximum positions
        open_count = con.execute(
            "SELECT COUNT(*) as cnt FROM trading_positions WHERE bot_id=? AND status='OPEN'",
            (bot_id,),
        ).fetchone()["cnt"]
        if open_count >= self.config["max_positions"]:
            return False, f"Max positions reached: {open_count}"

        # 7. Already in this symbol
        existing = con.execute(
            "SELECT COUNT(*) as cnt FROM trading_positions WHERE bot_id=? AND symbol=? AND status='OPEN'",
            (bot_id, symbol),
        ).fetchone()["cnt"]
        if existing > 0:
            return False, f"Already holding {symbol}"

        # 8. AI score threshold
        if ai_score < self.config["min_ai_score"]:
            return False, f"AI score too low: {ai_score:.1f} < {self.config['min_ai_score']}"

        # 9. Portfolio risk limit
        total_risk = self._total_portfolio_risk(con, bot_id)
        if total_risk >= self.config["max_portfolio_risk_pct"]:
            return False, f"Portfolio risk exceeded: {total_risk:.1f}%"

        # 10. Correlated exposure
        corr_exposure = self._correlated_exposure(con, bot_id, symbol)
        if corr_exposure >= self.config["max_correlated_exposure_pct"]:
            return False, f"Correlated exposure: {corr_exposure:.1f}%"

        return True, "OK"

    def calculate_position_size(self, con, bot_id, entry_price, stop_loss, ai_score):
        """
        Calculate optimal position size based on risk parameters.
        Returns (quantity, risk_amount, position_value).
        """
        bot = con.execute(
            "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
        ).fetchone()
        if not bot:
            return 0, 0, 0

        equity = bot["equity"]
        if equity <= 0 or entry_price <= 0 or stop_loss <= 0:
            return 0, 0, 0

        # Base risk percentage
        base_risk = self.config["risk_per_trade_pct"]

        # Dynamic adjustment based on AI score
        if ai_score >= 85:
            risk_pct = min(base_risk * 1.2, self.config["max_risk_per_trade_pct"])
        elif ai_score >= 75:
            risk_pct = base_risk
        elif ai_score >= 65:
            risk_pct = base_risk * 0.8
        else:
            risk_pct = base_risk * 0.5

        # Portfolio risk check
        current_risk = self._total_portfolio_risk(con, bot_id)
        remaining_risk = self.config["max_portfolio_risk_pct"] - current_risk
        if remaining_risk <= 0:
            return 0, 0, 0

        risk_pct = min(risk_pct, remaining_risk)

        # Calculate
        risk_amount = equity * (risk_pct / 100)
        price_risk = abs(entry_price - stop_loss)

        if price_risk <= 0:
            return 0, 0, 0

        quantity = risk_amount / price_risk
        position_value = quantity * entry_price

        # Cap at max risk
        max_risk_amount = equity * (self.config["max_risk_per_trade_pct"] / 100)
        if risk_amount > max_risk_amount:
            risk_amount = max_risk_amount
            quantity = risk_amount / price_risk
            position_value = quantity * entry_price

        return round(quantity, 8), round(risk_amount, 2), round(position_value, 2)

    def check_position_exit(self, con, bot_id, position, current_price):
        """
        Check if a position should be exited.
        Returns (should_exit: bool, reason: str).
        """
        entry = position["entry_price"]
        sl = position["stop_loss"]
        tp1 = position["take_profit1"]
        tp2 = position["take_profit2"]
        side = position["side"]

        if side == "LONG":
            # Stop loss
            if current_price <= sl:
                return True, "STOP_LOSS"

            # Take profit 1
            if tp1 and not position["tp1_hit"]:
                if current_price >= tp1:
                    return False, "TP1_REACHED"  # Partial close handled by position manager

            # Take profit 2
            if tp2 and not position["tp2_hit"]:
                if current_price >= tp2:
                    return True, "TAKE_PROFIT2"

            # Trailing stop
            if position["trailing_active"]:
                trail = position.get("trailing_stop", 0)
                if trail > 0 and current_price <= trail:
                    return True, "TRAILING_STOP"

            # Emergency volatility exit
            bot = con.execute(
                "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
            ).fetchone()
            if bot:
                dd = self._drawdown_pct(bot)
                if dd >= self.config["emergency_shutdown_pct"]:
                    return True, "EMERGENCY_SHUTDOWN"

        else:  # SHORT
            if current_price >= sl:
                return True, "STOP_LOSS"

            if tp1 and not position["tp1_hit"]:
                if current_price <= tp1:
                    return False, "TP1_REACHED"

            if tp2 and not position["tp2_hit"]:
                if current_price <= tp2:
                    return True, "TAKE_PROFIT2"

            if position["trailing_active"]:
                trail = position.get("trailing_stop", 0)
                if trail > 0 and current_price >= trail:
                    return True, "TRAILING_STOP"

            bot = con.execute(
                "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
            ).fetchone()
            if bot:
                dd = self._drawdown_pct(bot)
                if dd >= self.config["emergency_shutdown_pct"]:
                    return True, "EMERGENCY_SHUTDOWN"

        # Max holding period
        entry_time = position["entry_time"]
        if isinstance(entry_time, str):
            try:
                entry_time = datetime.fromisoformat(entry_time)
            except Exception:
                entry_time = datetime.now()

        if entry_time and (datetime.now() - entry_time).total_seconds() > self.config["max_holding_periods"] * 300:
            return True, "MAX_HOLDING_PERIOD"

        return False, "HOLDING"

    def _drawdown_pct(self, bot):
        """Calculate current drawdown from peak."""
        peak = bot["peak_equity"]
        equity = bot["equity"]
        if peak <= 0:
            return 0
        return max(0, (peak - equity) / peak * 100)

    def _daily_loss_pct(self, bot):
        """Calculate today's loss percentage."""
        start = bot["daily_start_equity"]
        equity = bot["equity"]
        if start <= 0:
            return 0
        if equity >= start:
            return 0
        return (start - equity) / start * 100

    def _total_portfolio_risk(self, con, bot_id):
        """Calculate total risk as % of equity."""
        bot = con.execute(
            "SELECT equity FROM trading_bots WHERE id=?", (bot_id,)
        ).fetchone()
        if not bot or bot["equity"] <= 0:
            return 0

        positions = con.execute(
            "SELECT entry_price, remaining_qty, stop_loss FROM trading_positions WHERE bot_id=? AND status='OPEN'",
            (bot_id,),
        ).fetchall()

        total_risk = 0
        for pos in positions:
            price_risk = abs(pos["entry_price"] - pos["stop_loss"])
            pos_risk = pos["remaining_qty"] * price_risk
            total_risk += pos_risk

        return (total_risk / bot["equity"]) * 100

    def _correlated_exposure(self, con, bot_id, new_symbol):
        """Calculate exposure to correlated assets."""
        bot = con.execute(
            "SELECT equity FROM trading_bots WHERE id=?", (bot_id,)
        ).fetchone()
        if not bot or bot["equity"] <= 0:
            return 0

        # Simple correlation groups
        btc_group = {"BTCUSDT", "ETHUSDT"}
        alt_group = {"BNBUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"}
        meme_group = {"DOGEUSDT", "XRPUSDT"}

        new_group = None
        for g in [btc_group, alt_group, meme_group]:
            if new_symbol in g:
                new_group = g
                break

        if not new_group:
            return 0

        positions = con.execute(
            "SELECT symbol, entry_price, remaining_qty FROM trading_positions WHERE bot_id=? AND status='OPEN'",
            (bot_id,),
        ).fetchall()

        group_value = 0
        for pos in positions:
            if pos["symbol"] in new_group:
                group_value += pos["entry_price"] * pos["remaining_qty"]

        return (group_value / bot["equity"]) * 100


# Backward-compatible standalone functions
def calculate_position_size(capital, risk_percent, entry_price, stop_loss):
    """Legacy function — use RiskEngine for new code."""
    if capital <= 0 or risk_percent <= 0 or entry_price <= 0 or stop_loss <= 0:
        return 0
    risk_amount = capital * (risk_percent / 100)
    price_risk = abs(entry_price - stop_loss)
    if price_risk == 0:
        return 0
    return risk_amount / price_risk


def daily_loss_limit_reached(starting_capital, current_capital, max_loss_percent=1.0):
    """Legacy function."""
    if starting_capital <= 0:
        return True
    loss_pct = (starting_capital - current_capital) / starting_capital * 100
    return loss_pct >= max_loss_percent


def daily_target_reached(starting_capital, current_capital, target_percent=1.0):
    """Legacy function."""
    if starting_capital <= 0:
        return False
    profit_pct = (current_capital - starting_capital) / starting_capital * 100
    return profit_pct >= target_percent
