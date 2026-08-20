"""
AI Trading Engine — Institutional-Grade Backtesting Engine

Simulates the complete trading pipeline on historical data:
- Market data fetching (cached)
- Feature engineering
- Multi-TF regime detection
- Ensemble scoring
- Risk-engine position sizing
- SL/TP/trailing management
- Commission + slippage
- Equity curve tracking
- 20+ performance metrics

Walk-forward validation:
- Train on historical window
- Validate on out-of-sample
- Roll forward and repeat
- Aggregate statistics
"""

import json
import time
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

from trading.market_data import fetch_klines, fetch_ticker
from trading.features import calculate_all_features, analyze_timeframe_alignment
from trading.regime import detect_regime, detect_multi_tf_regime, is_regime_suitable
from trading.scoring import score_opportunity
from trading.config import DEFAULT_CONFIG


# ============================================================
# BACKTEST RESULT DATA CLASS
# ============================================================

class BacktestResult:
    """Container for all backtest results and metrics."""

    def __init__(self):
        # Basic info
        self.symbol = ""
        self.timeframe = ""
        self.start_date = ""
        self.end_date = ""
        self.parameters = {}

        # Capital
        self.starting_capital = 10000.0
        self.final_capital = 10000.0

        # Trades
        self.trades = []
        self.total_trades = 0
        self.wins = 0
        self.losses = 0

        # Returns
        self.net_profit = 0.0
        self.roi_pct = 0.0
        self.win_rate = 0.0
        self.loss_rate = 0.0

        # Profitability
        self.profit_factor = 0.0
        self.expectancy = 0.0
        self.avg_trade = 0.0
        self.avg_win = 0.0
        self.avg_loss = 0.0
        self.largest_win = 0.0
        self.largest_loss = 0.0

        # Risk
        self.max_drawdown_pct = 0.0
        self.max_drawdown_amount = 0.0
        self.max_drawdown_duration = 0
        self.sharpe_ratio = 0.0
        self.sortino_ratio = 0.0
        self.calmar_ratio = 0.0

        # Holding
        self.avg_holding_bars = 0.0
        self.avg_holding_hours = 0.0

        # Equity curve
        self.equity_curve = []
        self.drawdown_curve = []
        self.monthly_returns = {}

        # Breakdown
        self.trades_by_regime = {}
        self.trades_by_symbol = {}
        self.trades_by_reason = {}
        self.daily_pnl = {}

        # Consecutive
        self.max_consecutive_wins = 0
        self.max_consecutive_losses = 0

        # Execution
        self.total_commission = 0.0
        self.total_slippage = 0.0
        self.signals_generated = 0
        self.signals_rejected = 0

        # Status
        self.status = "PENDING"
        self.error = None

    def to_dict(self):
        """Convert to serializable dict."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "parameters": self.parameters,
            "starting_capital": round(self.starting_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "net_profit": round(self.net_profit, 2),
            "roi_pct": round(self.roi_pct, 2),
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 1),
            "loss_rate": round(self.loss_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 2),
            "avg_trade": round(self.avg_trade, 2),
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "largest_win": round(self.largest_win, 2),
            "largest_loss": round(self.largest_loss, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_amount": round(self.max_drawdown_amount, 2),
            "max_drawdown_duration": self.max_drawdown_duration,
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "avg_holding_bars": round(self.avg_holding_bars, 1),
            "avg_holding_hours": round(self.avg_holding_hours, 1),
            "equity_curve": self.equity_curve[-200:] if self.equity_curve else [],
            "drawdown_curve": self.drawdown_curve[-200:] if self.drawdown_curve else [],
            "monthly_returns": self.monthly_returns,
            "trades_by_regime": self.trades_by_regime,
            "trades_by_reason": self.trades_by_reason,
            "max_consecutive_wins": self.max_consecutive_wins,
            "max_consecutive_losses": self.max_consecutive_losses,
            "total_commission": round(self.total_commission, 2),
            "total_slippage": round(self.total_slippage, 2),
            "signals_generated": self.signals_generated,
            "signals_rejected": self.signals_rejected,
            "status": self.status,
            "error": self.error,
        }


# ============================================================
# SIMULATED POSITION
# ============================================================

class SimPosition:
    """Simulated position for backtesting."""

    def __init__(self, symbol, side, entry_price, quantity, sl, tp1, tp2,
                 ai_score=0, regime="", entry_tf="", entry_idx=0):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.remaining_qty = quantity
        self.stop_loss = sl
        self.take_profit1 = tp1
        self.take_profit2 = tp2
        self.trailing_stop = 0.0
        self.trailing_active = False
        self.break_even = False
        self.tp1_hit = False
        self.tp2_hit = False
        self.ai_score = ai_score
        self.regime = regime
        self.entry_tf = entry_tf
        self.entry_idx = entry_idx
        self.max_price = entry_price if side == "LONG" else 0
        self.min_price = entry_price if side == "SHORT" else float("inf")
        self.pnl = 0.0

    def update(self, high, low, close, bar_idx, config):
        """Update position management. Returns (should_exit, reason, partial_close_qty)."""
        entry = self.entry_price
        sl = self.stop_loss
        side = self.side
        partial_close = 0.0

        if side == "LONG":
            pnl_pct = (close - entry) / entry * 100 if entry > 0 else 0
            self.max_price = max(self.max_price, high)
        else:
            pnl_pct = (entry - close) / entry * 100 if entry > 0 else 0
            self.min_price = min(self.min_price, low)

        # Break-even
        be_act = config.get("break_even_activation_pct", 0.3)
        if not self.break_even and pnl_pct >= be_act:
            if side == "LONG":
                self.stop_loss = max(self.stop_loss, entry * 1.001)
            else:
                self.stop_loss = min(self.stop_loss, entry * 0.999)
            self.break_even = True

        # Partial TP1
        if not self.tp1_hit and self.take_profit1 > 0:
            if (side == "LONG" and high >= self.take_profit1) or \
               (side == "SHORT" and low <= self.take_profit1):
                close_pct = config.get("tp1_close_pct", 0.3)
                partial_close = round(self.quantity * close_pct, 8)
                self.remaining_qty -= partial_close
                self.tp1_hit = True
                if side == "LONG":
                    self.stop_loss = max(entry, self.stop_loss)
                else:
                    self.stop_loss = min(entry, self.stop_loss)

        # Partial TP2
        if not self.tp2_hit and self.take_profit2 > 0:
            if (side == "LONG" and high >= self.take_profit2) or \
               (side == "SHORT" and low <= self.take_profit2):
                close_pct = config.get("tp2_close_pct", 0.4)
                pc2 = round(self.quantity * close_pct, 8)
                if pc2 <= self.remaining_qty:
                    partial_close += pc2
                    self.remaining_qty -= pc2
                    self.tp2_hit = True

        # Trailing stop activation
        sl_dist = abs(entry - sl) if sl else entry * 0.01
        act_rr = config.get("trailing_stop_activation_rr", 1.0)
        act_pnl = sl_dist * act_rr / entry * 100 if entry > 0 else 0.5
        if pnl_pct >= act_pnl and not self.trailing_active:
            self.trailing_active = True

        if self.trailing_active:
            trail_pct = config.get("trailing_stop_distance_pct", 0.5)
            if side == "LONG":
                new_trail = close * (1 - trail_pct / 100)
                if new_trail > self.trailing_stop:
                    self.trailing_stop = new_trail
            else:
                new_trail = close * (1 + trail_pct / 100)
                if self.trailing_stop == 0 or new_trail < self.trailing_stop:
                    self.trailing_stop = new_trail

        # Check exits
        if side == "LONG":
            if low <= sl:
                return True, "STOP_LOSS", partial_close
            if self.trailing_active and self.trailing_stop > 0 and low <= self.trailing_stop:
                return True, "TRAILING_STOP", partial_close
            if high >= self.take_profit2 and self.tp2_hit:
                return True, "TAKE_PROFIT2", partial_close
        else:
            if high >= sl:
                return True, "STOP_LOSS", partial_close
            if self.trailing_active and self.trailing_stop > 0 and high >= self.trailing_stop:
                return True, "TRAILING_STOP", partial_close
            if low <= self.take_profit2 and self.tp2_hit:
                return True, "TAKE_PROFIT2", partial_close

        # Max holding
        max_hold = config.get("max_holding_periods", 48)
        if (bar_idx - self.entry_idx) >= max_hold:
            return True, "MAX_HOLDING", partial_close

        return False, "HOLDING", partial_close


# ============================================================
# BACKTESTER
# ============================================================

class Backtester:
    """Institutional-grade backtester."""

    def __init__(self, config=None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)

    def run(self, symbol, timeframe="1h", limit=1000):
        """
        Run a backtest on historical data for a single symbol/timeframe.

        Returns a BacktestResult.
        """
        result = BacktestResult()
        result.symbol = symbol
        result.timeframe = timeframe
        result.parameters = {
            "risk_per_trade_pct": self.config["risk_per_trade_pct"],
            "min_ai_score": self.config["min_ai_score"],
            "sl_atr_multiplier": self.config["sl_atr_multiplier"],
            "tp1_rr": self.config["tp1_rr"],
            "tp2_rr": self.config["tp2_rr"],
            "max_positions": self.config["max_positions"],
        }

        try:
            # 1. Fetch historical data
            print(f"  Backtest: Fetching {symbol} {timeframe} ({limit} candles)...")
            df = fetch_klines(symbol, timeframe, limit=limit)
            if df is None or len(df) < 60:
                result.status = "FAILED"
                result.error = f"Insufficient data: {len(df) if df is not None else 0} candles"
                return result

            # 2. Calculate features
            print(f"  Backtest: Calculating features...")
            df = calculate_all_features(df)
            df = df.dropna(subset=["close", "atr", "rsi"]).reset_index(drop=True)

            if len(df) < 60:
                result.status = "FAILED"
                result.error = "Insufficient data after feature calculation"
                return result

            result.start_date = str(df.iloc[0].get("timestamp", ""))
            result.end_date = str(df.iloc[-1].get("timestamp", ""))

            # 3. Run simulation
            print(f"  Backtest: Simulating {len(df)} bars...")
            result = self._simulate(df, result, symbol, timeframe)

            # 4. Calculate metrics
            print(f"  Backtest: Calculating metrics...")
            result = self._calculate_metrics(result)

            result.status = "COMPLETED"
            print(f"  Backtest: Done — {result.total_trades} trades, ROI {result.roi_pct:.1f}%, "
                  f"Sharpe {result.sharpe_ratio:.2f}, MaxDD {result.max_drawdown_pct:.1f}%")

        except Exception as e:
            result.status = "FAILED"
            result.error = str(e)
            traceback.print_exc()

        return result

    def run_multi_symbol(self, symbols, timeframe="1h", limit=1000):
        """Run backtests on multiple symbols and aggregate."""
        results = []
        for sym in symbols:
            sym = sym.strip()
            if not sym:
                continue
            r = self.run(sym, timeframe, limit)
            results.append(r)
            time.sleep(0.5)  # Rate limit

        # Aggregate
        if not results:
            return None, []

        agg = BacktestResult()
        agg.symbol = "MULTI"
        agg.timeframe = timeframe
        agg.starting_capital = self.config["starting_capital"]

        all_trades = []
        for r in results:
            if r.status == "COMPLETED":
                all_trades.extend(r.trades)

        agg.trades = sorted(all_trades, key=lambda t: t.get("entry_idx", 0))
        agg = self._calculate_metrics(agg)

        return agg, [r.to_dict() for r in results]

    def _simulate(self, df, result, symbol, timeframe):
        """Core simulation loop."""
        capital = self.config["starting_capital"]
        equity = capital
        peak_equity = capital
        positions = []
        closed_trades = []
        equity_curve = [(0, capital)]
        signals_generated = 0
        signals_rejected = 0
        total_commission = 0.0
        total_slippage = 0.0

        # Pre-fetch multi-TF data for scoring (only once per symbol)
        multi_tf = {}
        for mtf in ["15m", "1h", "4h"]:
            try:
                mtf_df = fetch_klines(symbol, mtf, 200)
                if mtf_df is not None and len(mtf_df) >= 30:
                    mtf_df = calculate_all_features(mtf_df)
                    multi_tf[mtf] = mtf_df
            except Exception:
                pass

        start_bar = 50  # Need enough data for indicators

        for i in range(start_bar, len(df)):
            row = df.iloc[i]
            high = row.get("high", row["close"])
            low = row.get("low", row["close"])
            close = row["close"]

            # 1. Manage existing positions
            new_positions = []
            for pos in positions:
                # Check if this bar's candle triggers any exit
                if pos.side == "LONG":
                    candle_high = high
                    candle_low = low
                else:
                    candle_high = high
                    candle_low = low

                should_exit, reason, partial_close = pos.update(
                    candle_high, candle_low, close, i, self.config
                )

                # Handle partial close
                if partial_close > 0 and pos.remaining_qty > 0:
                    pc_price = close
                    slippage = pc_price * self.config["slippage_bps"] / 10000
                    commission = pc_price * partial_close * self.config["commission_bps"] / 10000
                    total_commission += commission
                    total_slippage += slippage

                    if pos.side == "LONG":
                        fill = pc_price - slippage
                        pnl = (fill - pos.entry_price) * partial_close
                    else:
                        fill = pc_price + slippage
                        pnl = (pos.entry_price - fill) * partial_close

                    net = pnl - commission
                    equity += net

                if should_exit:
                    slippage = close * self.config["slippage_bps"] / 10000
                    commission = close * pos.remaining_qty * self.config["commission_bps"] / 10000
                    total_commission += commission
                    total_slippage += slippage

                    if pos.side == "LONG":
                        fill = close - slippage
                        pnl = (fill - pos.entry_price) * pos.remaining_qty
                    else:
                        fill = close + slippage
                        pnl = (pos.entry_price - fill) * pos.remaining_qty

                    net = pnl - commission
                    equity += net

                    trade = {
                        "symbol": symbol,
                        "side": pos.side,
                        "entry_price": pos.entry_price,
                        "exit_price": fill,
                        "quantity": pos.quantity,
                        "pnl": round(pnl, 4),
                        "net_pnl": round(net, 4),
                        "commission": round(commission, 4),
                        "exit_reason": reason,
                        "ai_score": pos.ai_score,
                        "regime": pos.regime,
                        "entry_idx": pos.entry_idx,
                        "exit_idx": i,
                        "holding_bars": i - pos.entry_idx,
                    }
                    closed_trades.append(trade)

                    # Update equity tracking
                    peak_equity = max(peak_equity, equity)
                else:
                    new_positions.append(pos)

            positions = new_positions

            # 2. Generate signals for new entries
            if len(positions) < self.config.get("max_positions", 5):
                # Slice up to current bar for feature calculation
                sub_df = df.iloc[max(0, i - 200):i + 1].copy()
                if len(sub_df) < 30:
                    continue

                try:
                    sub_df = calculate_all_features(sub_df)
                    if len(sub_df) < 1:
                        continue

                    last_row = sub_df.iloc[-1]

                    for direction in ["LONG", "SHORT"]:
                        signals_generated += 1

                        # Check if already have position in this symbol
                        has_pos = any(p.symbol == symbol for p in positions)
                        if has_pos:
                            signals_rejected += 1
                            continue

                        # Quick regime check
                        regime, regime_conf, _ = detect_regime(sub_df)

                        if direction == "LONG" and regime in ("BEAR_TREND", "BREAKDOWN"):
                            signals_rejected += 1
                            continue
                        if direction == "SHORT" and regime in ("BULL_TREND", "BREAKOUT"):
                            signals_rejected += 1
                            continue

                        # Score opportunity with multi-TF data
                        score_result = score_opportunity(sub_df, direction, self.config, multi_tf_data=multi_tf if multi_tf else None)

                        if score_result["ai_score"] < self.config.get("min_ai_score", 70) - 15:  # Lower threshold for backtesting (no ML)
                            signals_rejected += 1
                            continue

                        if score_result["rr_ratio"] < self.config.get("min_rr_ratio", 1.5):
                            signals_rejected += 1
                            continue

                        # Calculate position size
                        entry_price = score_result["entry_price"]
                        sl_price = score_result["stop_loss"]
                        tp1 = score_result["take_profit1"]
                        tp2 = score_result["take_profit2"]

                        if entry_price <= 0 or sl_price <= 0:
                            signals_rejected += 1
                            continue

                        # Risk-based sizing
                        risk_pct = self.config["risk_per_trade_pct"]
                        if score_result["ai_score"] >= 85:
                            risk_pct = min(risk_pct * 1.2, self.config["max_risk_per_trade_pct"])
                        elif score_result["ai_score"] < 65:
                            risk_pct *= 0.5

                        risk_amount = equity * (risk_pct / 100)
                        price_risk = abs(entry_price - sl_price)
                        if price_risk <= 0:
                            signals_rejected += 1
                            continue

                        quantity = risk_amount / price_risk
                        position_value = quantity * entry_price

                        # Cap at 20% of equity
                        if position_value > equity * 0.2:
                            quantity = (equity * 0.2) / entry_price

                        if quantity * entry_price < 10:
                            signals_rejected += 1
                            continue

                        # Deduct from equity (paper lock)
                        equity -= commission if i > start_bar else 0

                        pos = SimPosition(
                            symbol=symbol,
                            side=direction,
                            entry_price=entry_price,
                            quantity=round(quantity, 8),
                            sl=sl_price,
                            tp1=tp1,
                            tp2=tp2,
                            ai_score=score_result["ai_score"],
                            regime=regime,
                            entry_tf=timeframe,
                            entry_idx=i,
                        )
                        positions.append(pos)
                        break  # Only one position per symbol at a time

                except Exception:
                    signals_rejected += 1
                    continue

            # 3. Record equity
            unrealized = sum(
                (close - p.entry_price) * p.remaining_qty if p.side == "LONG"
                else (p.entry_price - close) * p.remaining_qty
                for p in positions
            )
            total_equity = equity + unrealized
            equity_curve.append((i, round(total_equity, 2)))

        # Close remaining positions at last price
        last_close = df.iloc[-1]["close"]
        for pos in positions:
            slippage = last_close * self.config["slippage_bps"] / 10000
            commission = last_close * pos.remaining_qty * self.config["commission_bps"] / 10000
            total_commission += commission
            total_slippage += slippage

            if pos.side == "LONG":
                fill = last_close - slippage
                pnl = (fill - pos.entry_price) * pos.remaining_qty
            else:
                fill = last_close + slippage
                pnl = (pos.entry_price - fill) * pos.remaining_qty

            net = pnl - commission
            equity += net

            closed_trades.append({
                "symbol": symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "exit_price": fill,
                "quantity": pos.quantity,
                "pnl": round(pnl, 4),
                "net_pnl": round(net, 4),
                "commission": round(commission, 4),
                "exit_reason": "BACKTEST_END",
                "ai_score": pos.ai_score,
                "regime": pos.regime,
                "entry_idx": pos.entry_idx,
                "exit_idx": len(df) - 1,
                "holding_bars": len(df) - 1 - pos.entry_idx,
            })

        result.trades = closed_trades
        result.equity_curve = equity_curve
        result.signals_generated = signals_generated
        result.signals_rejected = signals_rejected
        result.total_commission = total_commission
        result.total_slippage = total_slippage

        return result

    def _calculate_metrics(self, result):
        """Calculate all performance metrics from trades and equity curve."""
        trades = result.trades
        capital = result.starting_capital

        if not trades:
            result.status = "COMPLETED"
            result.final_capital = capital
            return result

        # Basic trade stats
        result.total_trades = len(trades)
        wins = [t for t in trades if t["net_pnl"] > 0]
        losses = [t for t in trades if t["net_pnl"] <= 0]
        result.wins = len(wins)
        result.losses = len(losses)
        result.win_rate = (result.wins / result.total_trades * 100) if result.total_trades else 0
        result.loss_rate = (result.losses / result.total_trades * 100) if result.total_trades else 0

        # P&L
        gross_profit = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        result.net_profit = sum(t["net_pnl"] for t in trades)
        result.final_capital = capital + result.net_profit
        result.roi_pct = (result.net_profit / capital * 100) if capital > 0 else 0

        # Profitability
        result.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
        result.expectancy = (result.net_profit / result.total_trades) if result.total_trades else 0
        result.avg_trade = result.expectancy
        result.avg_win = (gross_profit / len(wins)) if wins else 0
        result.avg_loss = (-gross_loss / len(losses)) if losses else 0
        result.largest_win = max((t["net_pnl"] for t in wins), default=0)
        result.largest_loss = min((t["net_pnl"] for t in losses), default=0)

        # Drawdown from equity curve
        if result.equity_curve:
            peak = capital
            max_dd_pct = 0
            max_dd_amt = 0
            dd_start = 0
            max_dd_duration = 0
            current_dd_start = 0
            drawdown_curve = []

            for idx, eq in result.equity_curve:
                eq_val = eq if isinstance(eq, (int, float)) else eq[1]
                if eq_val > peak:
                    peak = eq_val
                    current_dd_start = idx
                dd = peak - eq_val
                dd_pct = (dd / peak * 100) if peak > 0 else 0
                drawdown_curve.append(round(dd_pct, 2))

                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct
                    max_dd_amt = dd
                    dd_start = current_dd_start
                    max_dd_duration = idx - dd_start

            result.max_drawdown_pct = max_dd_pct
            result.max_drawdown_amount = max_dd_amt
            result.max_drawdown_duration = max_dd_duration
            result.drawdown_curve = drawdown_curve[-200:]

        # Returns series for Sharpe/Sortino
        returns = []
        for i in range(1, len(result.equity_curve)):
            prev = result.equity_curve[i - 1][1]
            curr = result.equity_curve[i][1]
            if prev > 0:
                returns.append((curr - prev) / prev)

        if returns:
            ret_arr = np.array(returns)
            mean_ret = np.mean(ret_arr)
            std_ret = np.std(ret_arr)
            if std_ret > 0:
                result.sharpe_ratio = (mean_ret / std_ret) * np.sqrt(252 * 24)  # Annualized
            neg_returns = ret_arr[ret_arr < 0]
            if len(neg_returns) > 0:
                neg_std = np.std(neg_returns)
                if neg_std > 0:
                    result.sortino_ratio = (mean_ret / neg_std) * np.sqrt(252 * 24)
            if result.max_drawdown_pct > 0:
                result.calmar_ratio = result.roi_pct / result.max_drawdown_pct

        # Holding time
        bars = [t["holding_bars"] for t in trades if t.get("holding_bars")]
        if bars:
            result.avg_holding_bars = np.mean(bars)
            # Estimate hours (depends on timeframe)
            tf_minutes = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
            minutes = tf_minutes.get(result.timeframe, 60)
            result.avg_holding_hours = result.avg_holding_bars * minutes / 60

        # Consecutive wins/losses
        max_cw, max_cl = 0, 0
        cw, cl = 0, 0
        for t in trades:
            if t["net_pnl"] > 0:
                cw += 1
                cl = 0
                max_cw = max(max_cw, cw)
            else:
                cl += 1
                cw = 0
                max_cl = max(max_cl, cl)
        result.max_consecutive_wins = max_cw
        result.max_consecutive_losses = max_cl

        # Breakdown by regime
        regime_stats = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
        reason_stats = defaultdict(lambda: {"count": 0, "pnl": 0})
        for t in trades:
            r = t.get("regime", "UNKNOWN")
            regime_stats[r]["count"] += 1
            regime_stats[r]["pnl"] += t["net_pnl"]
            if t["net_pnl"] > 0:
                regime_stats[r]["wins"] += 1
            reason = t.get("exit_reason", "UNKNOWN")
            reason_stats[reason]["count"] += 1
            reason_stats[reason]["pnl"] += t["net_pnl"]

        result.trades_by_regime = {
            k: {"count": v["count"], "pnl": round(v["pnl"], 2),
                "win_rate": round(v["wins"] / v["count"] * 100, 1) if v["count"] else 0}
            for k, v in regime_stats.items()
        }
        result.trades_by_reason = {
            k: {"count": v["count"], "pnl": round(v["pnl"], 2)}
            for k, v in reason_stats.items()
        }

        # Monthly returns
        monthly = defaultdict(float)
        for t in trades:
            exit_time = t.get("exit_time", "")
            if exit_time and isinstance(exit_time, str) and len(exit_time) >= 7:
                month = exit_time[:7]
            else:
                month = f"trade_{t.get('exit_idx', 0)}"
            monthly[month] += t["net_pnl"]
        result.monthly_returns = {k: round(v, 2) for k, v in monthly.items()}

        return result


# ============================================================
# WALK-FORWARD VALIDATION
# ============================================================

class WalkForwardValidator:
    """
    Walk-forward optimization and validation.

    Pipeline:
    1. Split data into windows
    2. For each window: train on in-sample, test on out-of-sample
    3. Aggregate all out-of-sample results
    4. Report walk-forward performance
    """

    def __init__(self, config=None):
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)

    def run(self, symbol, timeframe="1h", limit=2000,
            in_sample_bars=500, out_of_sample_bars=100, step_bars=100):
        """
        Run walk-forward validation.

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            limit: Total candles to fetch
            in_sample_bars: Training window size
            out_of_sample_bars: Testing window size
            step_bars: Step size for rolling window

        Returns:
            dict with aggregate results and per-window details
        """
        result = {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": "PENDING",
            "windows": [],
            "aggregate": {},
        }

        try:
            # Fetch full dataset
            print(f"  Walk-Forward: Fetching {symbol} {timeframe} ({limit} candles)...")
            df = fetch_klines(symbol, timeframe, limit=limit)
            if df is None or len(df) < in_sample_bars + out_of_sample_bars + 60:
                result["status"] = "FAILED"
                result["error"] = "Insufficient data"
                return result

            # Calculate features
            print(f"  Walk-Forward: Calculating features...")
            df = calculate_all_features(df)
            df = df.dropna(subset=["close", "atr", "rsi"]).reset_index(drop=True)

            total_bars = len(df)
            print(f"  Walk-Forward: {total_bars} bars available")

            # Generate windows
            windows = []
            start = 0
            while start + in_sample_bars + out_of_sample_bars <= total_bars:
                is_end = start + in_sample_bars
                oos_end = min(is_end + out_of_sample_bars, total_bars)
                windows.append((start, is_end, oos_end))
                start += step_bars

            if not windows:
                result["status"] = "FAILED"
                result["error"] = "No valid windows"
                return result

            print(f"  Walk-Forward: {len(windows)} windows to process")

            # Process each window
            all_oos_trades = []
            all_oos_equity = []
            window_results = []

            for w_idx, (is_start, is_end, oos_end) in enumerate(windows):
                print(f"  Window {w_idx + 1}/{len(windows)}: IS[{is_start}:{is_end}] OOS[{is_end}:{oos_end}]")

                is_data = df.iloc[is_start:is_end].copy()
                oos_data = df.iloc[is_end:oos_end].copy()

                if len(is_data) < 60 or len(oos_data) < 20:
                    continue

                # In-sample: calculate stats to determine best parameters
                is_regime = self._get_dominant_regime(is_data)
                is_trend = self._get_trend_strength(is_data)

                # Create config adjustments based on in-sample
                window_config = dict(self.config)
                if is_trend > 0.5:
                    window_config["min_ai_score"] = max(60, self.config.get("min_ai_score", 70) - 5)
                elif is_trend < 0.2:
                    window_config["min_ai_score"] = min(85, self.config.get("min_ai_score", 70) + 5)

                # Out-of-sample backtest
                bt = Backtester(config=window_config)
                # Create a mini-result
                oos_result = BacktestResult()
                oos_result.symbol = symbol
                oos_result.timeframe = timeframe
                oos_result.starting_capital = self.config["starting_capital"]

                oos_result = bt._simulate(oos_data, oos_result, symbol, timeframe)
                oos_result = bt._calculate_metrics(oos_result)

                window_info = {
                    "window": w_idx + 1,
                    "is_bars": len(is_data),
                    "oos_bars": len(oos_data),
                    "is_regime": is_regime,
                    "is_trend_strength": round(is_trend, 3),
                    "oos_trades": oos_result.total_trades,
                    "oos_pnl": round(oos_result.net_profit, 2),
                    "oos_roi": round(oos_result.roi_pct, 2),
                    "oos_win_rate": round(oos_result.win_rate, 1),
                    "oos_max_dd": round(oos_result.max_drawdown_pct, 2),
                    "oos_sharpe": round(oos_result.sharpe_ratio, 3),
                    "status": oos_result.status,
                }
                window_results.append(window_info)
                all_oos_trades.extend(oos_result.trades)

            # Aggregate OOS results
            if all_oos_trades:
                agg = BacktestResult()
                agg.symbol = symbol
                agg.timeframe = timeframe
                agg.trades = all_oos_trades
                agg.starting_capital = self.config["starting_capital"]
                agg = bt._calculate_metrics(agg)

                result["aggregate"] = {
                    "total_oos_trades": agg.total_trades,
                    "oos_win_rate": round(agg.win_rate, 1),
                    "oos_profit_factor": round(agg.profit_factor, 2),
                    "oos_expectancy": round(agg.expectancy, 2),
                    "oos_sharpe": round(agg.sharpe_ratio, 3),
                    "oos_sortino": round(agg.sortino_ratio, 3),
                    "oos_max_drawdown": round(agg.max_drawdown_pct, 2),
                    "oos_roi": round(agg.roi_pct, 2),
                    "oos_net_profit": round(agg.net_profit, 2),
                    "oos_avg_trade": round(agg.avg_trade, 2),
                    "oos_avg_win": round(agg.avg_win, 2),
                    "oos_avg_loss": round(agg.avg_loss, 2),
                    "oos_max_consecutive_wins": agg.max_consecutive_wins,
                    "oos_max_consecutive_losses": agg.max_consecutive_losses,
                    "windows_profitable": sum(1 for w in window_results if w["oos_pnl"] > 0),
                    "windows_total": len(window_results),
                    "consistency": round(
                        sum(1 for w in window_results if w["oos_pnl"] > 0) / len(window_results) * 100, 1
                    ) if window_results else 0,
                }

            result["windows"] = window_results
            result["status"] = "COMPLETED"

            agg_info = result["aggregate"]
            print(f"  Walk-Forward: Done — {agg_info.get('total_oos_trades', 0)} trades, "
                  f"WR {agg_info.get('oos_win_rate', 0)}%, "
                  f"Sharpe {agg_info.get('oos_sharpe', 0)}, "
                  f"Consistency {agg_info.get('consistency', 0)}%")

        except Exception as e:
            result["status"] = "FAILED"
            result["error"] = str(e)
            traceback.print_exc()

        return result

    def _get_dominant_regime(self, df):
        """Get the dominant regime from a dataframe."""
        try:
            regime, conf, _ = detect_regime(df)
            return regime
        except Exception:
            return "UNKNOWN"

    def _get_trend_strength(self, df):
        """Get aggregate trend strength from a dataframe (0-1 scale)."""
        try:
            if len(df) < 20:
                return 0.3
            # Use ADX as trend strength proxy
            adx_vals = df["adx"].dropna()
            if len(adx_vals) > 0:
                avg_adx = adx_vals.mean()
                return min(1.0, avg_adx / 50)
            return 0.3
        except Exception:
            return 0.3


# ============================================================
# LEGACY COMPATIBILITY
# ============================================================

class TradingBot:
    """Legacy compatibility wrapper."""

    def __init__(self, symbol="BTCUSDT", interval="1h", capital=2500,
                 risk_percent=0.5, stop_loss_percent=1.0, take_profit_percent=1.5):
        self.symbol = symbol
        self.interval = interval
        self.capital = capital
        self.risk_percent = risk_percent
        self.stop_loss_percent = stop_loss_percent
        self.take_profit_percent = take_profit_percent
        self._running = False
        self._positions = []
        self._trades = []

    def start(self):
        self._running = True
        print(f"Legacy bot started: {self.symbol}")

    def stop(self):
        self._running = False
        print("Legacy bot stopped")

    def stats(self):
        return {
            "symbol": self.symbol,
            "capital": self.capital,
            "trades": len(self._trades),
            "positions": len(self._positions),
            "running": self._running,
        }
