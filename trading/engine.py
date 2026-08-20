"""
AI Trading Engine — Main Engine (Phase 2 Enhanced)

Orchestrates the complete trading pipeline:
Market Scanner → Feature Engineering → Multi-TF Regime →
Ensemble Scoring → Opportunity Ranking → Risk → Execution → Management

Phase 2 enhancements:
- Full multi-symbol, multi-timeframe scanning
- Cross-timeframe alignment analysis
- Opportunity ranking with quality grades
- Scanner result persistence
- Enhanced NO TRADE logic
- API failure recovery with backoff
"""

import time
import threading
import traceback
from datetime import datetime

from trading.config import get_trading_config
from trading.db import (
    create_trading_tables, get_or_create_bot, save_position,
    update_position, close_position, record_order, record_signal,
    record_equity_snapshot, update_daily_stats, get_open_positions,
    record_scanner_result, get_recent_scanner_results, get_scanner_summary,
)
from trading.market_data import (
    get_multi_tf_data, fetch_ticker, scan_symbol, analyze_spread,
)
from trading.features import calculate_all_features, analyze_timeframe_alignment
from trading.regime import detect_regime, detect_multi_tf_regime
from trading.scoring import score_opportunity
from trading.risk_manager import RiskEngine
from trading.position_manager import PositionManager


class AIEngine:
    """The main AI trading engine with Phase 2 multi-TF scanner."""

    def __init__(self, database_path="database.db"):
        self.db_path = database_path
        self.running_bots = {}  # username -> thread
        self._stop_events = {}  # username -> threading.Event
        self._last_scan_data = {}  # bot_id -> latest scan results (for UI)

    def _connect(self):
        """Get a database connection."""
        import sqlite3
        con = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def init_db(self):
        """Initialize trading tables."""
        con = self._connect()
        create_trading_tables(con)
        from trading.config import init_trading_settings
        init_trading_settings(con)
        con.close()

    def start_bot(self, username):
        """Start the AI trading bot for a user."""
        if username in self.running_bots:
            return False, "Bot already running"

        con = self._connect()
        bot = get_or_create_bot(con, username)
        config = get_trading_config(con)
        con.close()

        con2 = self._connect()
        con2.execute(
            "UPDATE trading_bots SET status='RUNNING', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bot["id"],),
        )
        con2.commit()
        con2.close()

        stop_event = threading.Event()
        self._stop_events[username] = stop_event

        thread = threading.Thread(
            target=self._run_loop,
            args=(username, bot["id"], config, stop_event),
            daemon=True,
        )
        thread.start()
        self.running_bots[username] = thread

        return True, "Bot started"

    def stop_bot(self, username):
        """Stop the AI trading bot."""
        stop_event = self._stop_events.get(username)
        if stop_event:
            stop_event.set()

        con = self._connect()
        con.execute(
            "UPDATE trading_bots SET status='STOPPED', updated_at=CURRENT_TIMESTAMP WHERE username=?",
            (username,),
        )
        con.commit()
        con.close()

        self.running_bots.pop(username, None)
        self._stop_events.pop(username, None)
        return True, "Bot stopped"

    def pause_bot(self, username):
        """Pause the bot (no new trades, but manages existing)."""
        con = self._connect()
        con.execute(
            "UPDATE trading_bots SET status='PAUSED', updated_at=CURRENT_TIMESTAMP WHERE username=?",
            (username,),
        )
        con.commit()
        con.close()
        return True, "Bot paused"

    def emergency_stop(self, username):
        """Emergency stop — close all positions immediately."""
        con = self._connect()
        bot = con.execute(
            "SELECT * FROM trading_bots WHERE username=?", (username,)
        ).fetchone()
        if not bot:
            con.close()
            return False, "Bot not found"

        positions = get_open_positions(con, bot["id"])
        for pos in positions:
            ticker = fetch_ticker(pos["symbol"])
            if ticker:
                exit_price = ticker["price"]
            else:
                exit_price = pos["current_price"] or pos["entry_price"]

            pnl = self._calculate_pnl(pos, exit_price)
            commission_bps = 10
            commission = exit_price * pos["remaining_qty"] * commission_bps / 10000
            net_pnl = pnl - commission
            holding = self._holding_periods(pos)

            close_position(con, pos["id"], exit_price, "EMERGENCY_STOP", pnl, net_pnl, holding)
            record_order(con, bot["id"], pos["symbol"], "SELL" if pos["side"] == "LONG" else "BUY",
                        "MARKET", exit_price, pos["remaining_qty"], reason="EMERGENCY_STOP",
                        position_id=pos["id"])

        con.execute(
            "UPDATE trading_bots SET status='STOPPED', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (bot["id"],),
        )
        con.commit()
        con.close()

        self.stop_bot(username)
        return True, f"Emergency stop: closed {len(positions)} positions"

    def _run_loop(self, username, bot_id, config, stop_event):
        """Main bot loop running in a thread."""
        con = self._connect()
        risk_engine = RiskEngine(config)
        pos_manager = PositionManager(config)
        scan_interval = config.get("scan_interval_seconds", 60)

        while not stop_event.is_set():
            try:
                config = get_trading_config(con)
                risk_engine.config = config
                pos_manager.config = config

                bot = con.execute(
                    "SELECT * FROM trading_bots WHERE id=?", (bot_id,)
                ).fetchone()
                if not bot or bot["status"] in ("STOPPED", "ERROR"):
                    break

                if bot["status"] == "PAUSED":
                    self._manage_positions(con, bot_id, config, pos_manager, risk_engine)
                    time.sleep(scan_interval)
                    continue

                # === PHASE 2: MULTI-TF SCANNER ===
                self._scan_market_phase2(con, bot_id, config, risk_engine)

                # === MANAGE POSITIONS ===
                self._manage_positions(con, bot_id, config, pos_manager, risk_engine)

                # === UPDATE STATS ===
                update_daily_stats(con, bot_id)
                record_equity_snapshot(con, bot_id)

            except Exception as e:
                print(f"AI Engine error ({username}): {e}")
                traceback.print_exc()
                try:
                    con.execute(
                        "UPDATE trading_bots SET status='ERROR', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (bot_id,),
                    )
                    con.commit()
                except Exception:
                    pass

            stop_event.wait(scan_interval)

        try:
            con.close()
        except Exception:
            pass
        self.running_bots.pop(username, None)
        self._stop_events.pop(username, None)

    def _scan_market_phase2(self, con, bot_id, config, risk_engine):
        """
        Phase 2 Multi-Symbol, Multi-Timeframe Scanner.

        Pipeline:
        1. Scan all symbols → quality checks
        2. Fetch multi-TF data for each
        3. Calculate features for each TF
        4. Detect regime per-TF and composite
        5. Analyze timeframe alignment
        6. Score opportunities (both directions)
        7. Rank all opportunities
        8. Execute the best ones (subject to risk engine)
        """
        symbols = [s.strip() for s in config["symbols"].split(",") if s.strip()]
        timeframes = [t.strip() for t in config["timeframes"].split(",") if t.strip()]
        min_score = config.get("min_ai_score", 70)
        max_positions = config.get("max_positions", 5)

        # Current open position count
        open_positions = get_open_positions(con, bot_id)
        open_count = len(open_positions)
        open_symbols = {p["symbol"] for p in open_positions}

        # Collect all opportunities
        opportunities = []
        scan_count = 0
        reject_count = 0

        for symbol in symbols:
            try:
                # Phase 2: Run quality scan first
                scan_result = scan_symbol(symbol, timeframes)

                if scan_result.get("rejected"):
                    reject_count += 1
                    record_scanner_result(
                        con, bot_id, symbol, scan_result,
                        reject_reason=scan_result.get("reject_reason", ""),
                    )
                    continue

                scan_count += 1
                data = scan_result.get("data", {})

                if len(data) < 2:
                    reject_count += 1
                    record_scanner_result(
                        con, bot_id, symbol, scan_result,
                        reject_reason=f"Only {len(data)} timeframes",
                    )
                    continue

                # 1. Detect composite regime
                regime_info = detect_multi_tf_regime(data, timeframes)

                # 2. Analyze timeframe alignment
                alignment_info = analyze_timeframe_alignment(data, timeframes)

                # 3. Check regime tradeability
                if not regime_info["tradeable"]:
                    record_scanner_result(
                        con, bot_id, symbol, scan_result,
                        regime_info=regime_info,
                        alignment_info=alignment_info,
                        reject_reason=f"Regime not tradeable: {regime_info['composite_regime']}",
                    )
                    continue

                # 4. Use primary timeframe for detailed scoring
                primary_tf = config.get("primary_tf", "1h")
                if primary_tf not in data:
                    primary_tf = list(data.keys())[-1] if data else None
                if not primary_tf:
                    continue

                df = data[primary_tf]
                df = calculate_all_features(df)

                # 5. Score both directions
                for direction in ["LONG", "SHORT"]:
                    # Skip if already have position in this symbol+direction
                    if symbol in open_symbols:
                        break

                    score_result = score_opportunity(df, direction, config, multi_tf_data=data)

                    # 6. Filter: minimum score
                    if score_result["ai_score"] < min_score:
                        record_signal(con, bot_id, {
                            "symbol": symbol,
                            "timeframe": primary_tf,
                            "direction": direction,
                            **score_result,
                            "executed": False,
                            "reject_reason": f"Score {score_result['ai_score']:.1f} < {min_score}",
                        })
                        continue

                    # 7. Risk engine check
                    allowed, reason = risk_engine.can_trade(
                        con, bot_id, symbol, direction, score_result["ai_score"]
                    )
                    if not allowed:
                        record_signal(con, bot_id, {
                            "symbol": symbol,
                            "timeframe": primary_tf,
                            "direction": direction,
                            **score_result,
                            "executed": False,
                            "reject_reason": reason,
                        })
                        continue

                    # 8. R:R check
                    if score_result["rr_ratio"] < config.get("min_rr_ratio", 1.5):
                        record_signal(con, bot_id, {
                            "symbol": symbol,
                            "timeframe": primary_tf,
                            "direction": direction,
                            **score_result,
                            "executed": False,
                            "reject_reason": f"R:R {score_result['rr_ratio']:.2f} too low",
                        })
                        continue

                    # Add to opportunities for ranking
                    opportunities.append({
                        "symbol": symbol,
                        "direction": direction,
                        "score": score_result,
                        "regime_info": regime_info,
                        "alignment_info": alignment_info,
                        "scan_result": scan_result,
                        "primary_tf": primary_tf,
                    })

                # Record scanner result
                best_opp = max(opportunities, key=lambda x: x["score"]["ai_score"]) if opportunities else None
                record_scanner_result(
                    con, bot_id, symbol, scan_result,
                    regime_info=regime_info,
                    alignment_info=alignment_info,
                    best_score=best_opp["score"]["ai_score"] if best_opp else 0,
                    best_direction=best_opp["direction"] if best_opp else "",
                    tradeable=True,
                )

            except Exception as e:
                print(f"Scanner error {symbol}: {e}")
                reject_count += 1
                continue

        # Store scan data for UI
        self._last_scan_data[bot_id] = {
            "timestamp": datetime.now(),
            "symbols_scanned": scan_count,
            "symbols_rejected": reject_count,
            "opportunities": opportunities,
        }

        # 9. RANK opportunities
        ranked = sorted(opportunities, key=lambda x: x["score"]["ai_score"], reverse=True)

        # 10. EXECUTE top opportunities (up to max_positions)
        executed_count = 0
        for opp in ranked:
            if open_count + executed_count >= max_positions:
                break

            symbol = opp["symbol"]
            direction = opp["direction"]
            score_result = opp["score"]

            # Final check — symbol not already open
            if symbol in open_symbols:
                continue

            ticker = fetch_ticker(symbol)
            if not ticker:
                continue
            current_price = ticker["price"]

            # Calculate position size
            qty, risk_amt, pos_value = risk_engine.calculate_position_size(
                con, bot_id,
                score_result["entry_price"],
                score_result["stop_loss"],
                score_result["ai_score"],
            )

            if qty <= 0:
                record_signal(con, bot_id, {
                    "symbol": symbol,
                    "timeframe": opp["primary_tf"],
                    "direction": direction,
                    **score_result,
                    "executed": False,
                    "reject_reason": "Position size = 0",
                })
                continue

            # EXECUTE TRADE
            self._execute_entry(
                con, bot_id, symbol, direction, current_price,
                qty, score_result, config,
            )

            record_signal(con, bot_id, {
                "symbol": symbol,
                "timeframe": opp["primary_tf"],
                "direction": direction,
                **score_result,
                "executed": True,
            })

            executed_count += 1
            open_symbols.add(symbol)

        # Update last scan
        try:
            con.execute(
                "UPDATE trading_bots SET last_scan=CURRENT_TIMESTAMP WHERE id=?",
                (bot_id,),
            )
            con.commit()
        except Exception:
            pass

    def _execute_entry(self, con, bot_id, symbol, side, price, quantity, score_result, config):
        """Execute a paper trade entry."""
        slippage_bps = config.get("slippage_bps", 5)
        slippage = price * slippage_bps / 10000
        if side == "LONG":
            fill_price = price + slippage
        else:
            fill_price = price - slippage

        commission_bps = config.get("commission_bps", 10)
        commission = fill_price * quantity * commission_bps / 10000

        pos_data = {
            "symbol": symbol,
            "side": side,
            "entry_price": fill_price,
            "quantity": quantity,
            "stop_loss": score_result["stop_loss"],
            "take_profit1": score_result["take_profit1"],
            "take_profit2": score_result["take_profit2"],
            "ai_score": score_result["ai_score"],
            "entry_tf": score_result.get("direction", "5m"),
            "regime": score_result.get("regime", ""),
        }

        pos_id = save_position(con, bot_id, pos_data)

        record_order(con, bot_id, symbol, "BUY" if side == "LONG" else "SELL",
                    "LIMIT", fill_price, quantity, slippage=slippage,
                    commission=commission, reason=score_result.get("regime", ""),
                    position_id=pos_id)

        con.execute(
            "UPDATE trading_bots SET last_trade=CURRENT_TIMESTAMP WHERE id=?",
            (bot_id,),
        )
        con.commit()

        print(f"ENTRY: {side} {quantity:.6f} {symbol} @ {fill_price:.2f} "
              f"(AI: {score_result['ai_score']:.1f})")

    def _manage_positions(self, con, bot_id, config, pos_manager, risk_engine):
        """Monitor and manage all open positions."""
        positions = get_open_positions(con, bot_id)

        for pos in positions:
            try:
                ticker = fetch_ticker(pos["symbol"])
                if not ticker:
                    continue

                current_price = ticker["price"]
                pos_manager.update(con, pos, current_price)

                # Reload position after updates
                pos = con.execute(
                    "SELECT * FROM trading_positions WHERE id=?", (pos["id"],)
                ).fetchone()

                should_exit, reason = risk_engine.check_position_exit(con, bot_id, pos, current_price)

                if should_exit:
                    self._execute_exit(con, bot_id, pos, current_price, reason, config)
                elif reason == "TP1_REACHED":
                    self._partial_close(con, bot_id, pos, current_price, "TP1", config)

            except Exception as e:
                print(f"Position mgmt error {pos['symbol']}: {e}")
                continue

    def _execute_exit(self, con, bot_id, pos, exit_price, reason, config):
        """Execute a position exit."""
        slippage_bps = config.get("slippage_bps", 5)
        slippage = exit_price * slippage_bps / 10000

        if pos["side"] == "LONG":
            fill_price = exit_price - slippage
        else:
            fill_price = exit_price + slippage

        pnl = self._calculate_pnl(pos, fill_price)
        commission_bps = config.get("commission_bps", 10)
        commission = fill_price * pos["remaining_qty"] * commission_bps / 10000
        net_pnl = pnl - commission
        holding = self._holding_periods(pos)

        close_position(con, pos["id"], fill_price, reason, pnl, net_pnl, holding)
        record_order(con, bot_id, pos["symbol"],
                    "SELL" if pos["side"] == "LONG" else "BUY",
                    "MARKET", fill_price, pos["remaining_qty"],
                    slippage=slippage, commission=commission,
                    reason=reason, position_id=pos["id"])

        print(f"EXIT: {pos['symbol']} @ {fill_price:.2f} | PnL: {net_pnl:.2f} | Reason: {reason}")

    def _partial_close(self, con, bot_id, pos, price, reason, config):
        """Partial position close for TP1."""
        close_pct = config.get("tp1_close_pct", 0.3)
        close_qty = round(pos["quantity"] * close_pct, 8)

        if close_qty <= 0 or close_qty > pos["remaining_qty"]:
            return

        slippage_bps = config.get("slippage_bps", 5)
        slippage = price * slippage_bps / 10000
        fill_price = price - slippage if pos["side"] == "LONG" else price + slippage

        pnl = (fill_price - pos["entry_price"]) * close_qty if pos["side"] == "LONG" else (pos["entry_price"] - fill_price) * close_qty
        commission_bps = config.get("commission_bps", 10)
        commission = fill_price * close_qty * commission_bps / 10000
        net_pnl = pnl - commission

        new_qty = pos["remaining_qty"] - close_qty
        update_position(con, pos["id"],
                       remaining_qty=new_qty,
                       tp1_hit=1,
                       stop_loss=max(pos["entry_price"], pos["stop_loss"]) if pos["side"] == "LONG" else min(pos["entry_price"], pos["stop_loss"]))

        record_order(con, bot_id, pos["symbol"],
                    "SELL" if pos["side"] == "LONG" else "BUY",
                    "PARTIAL_TP", fill_price, close_qty,
                    slippage=slippage, commission=commission,
                    reason=reason, position_id=pos["id"])

        con.execute(
            "UPDATE trading_bots SET equity=equity+?, total_pnl=total_pnl+?, today_pnl=today_pnl+? WHERE id=?",
            (net_pnl, net_pnl, net_pnl, bot_id),
        )
        con.commit()

        print(f"PARTIAL: {close_qty:.6f} {pos['symbol']} @ {fill_price:.2f} | PnL: {net_pnl:.2f}")

    def _calculate_pnl(self, pos, exit_price):
        """Calculate PnL for a position."""
        if pos["side"] == "LONG":
            return (exit_price - pos["entry_price"]) * pos["remaining_qty"]
        else:
            return (pos["entry_price"] - exit_price) * pos["remaining_qty"]

    def _holding_periods(self, pos):
        """Calculate holding time in periods."""
        entry_time = pos["entry_time"]
        if isinstance(entry_time, str):
            try:
                entry_time = datetime.fromisoformat(entry_time)
            except Exception:
                return 0
        if entry_time:
            delta = datetime.now() - entry_time
            return int(delta.total_seconds() / 300)
        return 0

    def get_bot_status(self, username):
        """Get comprehensive bot status (Phase 2 enhanced)."""
        con = self._connect()
        bot = get_or_create_bot(con, username)
        config = get_trading_config(con)
        positions = get_open_positions(con, bot["id"])
        from trading.db import get_trade_stats, get_recent_trades
        stats = get_trade_stats(con, bot["id"])
        recent = get_recent_trades(con, bot["id"], 10)

        # Phase 2: scanner data
        scan_summary = get_scanner_summary(con, bot["id"])
        recent_scans = get_recent_scanner_results(con, bot["id"], 10)

        con.close()

        is_running = username in self.running_bots

        # Get last scan data from memory
        last_scan = self._last_scan_data.get(bot["id"])

        # Build opportunity list for UI
        top_opportunities = []
        if last_scan and "opportunities" in last_scan:
            for opp in last_scan["opportunities"][:5]:
                s = opp["score"]
                ml_pred = s.get("ml_prediction", {})
                top_opportunities.append({
                    "symbol": opp["symbol"],
                    "direction": opp["direction"],
                    "ai_score": s["ai_score"],
                    "quality": s.get("quality", {}),
                    "regime": s.get("regime", ""),
                    "regime_description": s.get("regime_description", ""),
                    "entry_price": s["entry_price"],
                    "stop_loss": s["stop_loss"],
                    "take_profit1": s["take_profit1"],
                    "take_profit2": s["take_profit2"],
                    "rr_ratio": s["rr_ratio"],
                    "reasons": s.get("reasons", []),
                    "tf_alignment": s.get("tf_alignment", {}),
                    "scores": s.get("scores", {}),
                    "ml_score": ml_pred.get("ml_score", 50),
                    "ml_confidence": ml_pred.get("ml_confidence", 0),
                    "model_version": ml_pred.get("model_version", "none"),
                })

        # Phase 3: ML status
        ml_status = self._get_ml_status()

        return {
            "bot": dict(bot) if bot else None,
            "config": config,
            "positions": [dict(p) for p in positions],
            "stats": stats,
            "recent_trades": [dict(t) for t in recent],
            "is_running": is_running,
            "scan_summary": scan_summary,
            "recent_scans": [dict(s) for s in recent_scans],
            "top_opportunities": top_opportunities,
            "last_scan_time": last_scan["timestamp"] if last_scan else None,
            "symbols_scanned": last_scan["symbols_scanned"] if last_scan else 0,
            "symbols_rejected": last_scan["symbols_rejected"] if last_scan else 0,
            "ml_status": ml_status,
        }

    def _get_ml_status(self):
        """Get ML engine status for UI display."""
        try:
            from trading.ml_engine import MLPredictor, ModelRegistry
            predictor = MLPredictor()
            ml_info = predictor.get_status()

            registry = ModelRegistry()
            registry_info = registry.get_registry_info()

            return {
                "available": ml_info.get("active_model") is not None,
                "active_model": ml_info.get("active_model"),
                "model_version": ml_info.get("active_model"),
                "total_models": ml_info.get("total_models", 0),
                "predictions_made": ml_info.get("prediction_count", 0),
                "errors": ml_info.get("error_count", 0),
                "model_info": registry_info.get("active_info"),
            }
        except Exception as e:
            return {
                "available": False,
                "active_model": None,
                "model_version": "none",
                "total_models": 0,
                "predictions_made": 0,
                "errors": 0,
                "model_info": None,
                "error": str(e),
            }

    def train_ml(self):
        """Train the ML model. Called from route or startup."""
        try:
            from trading.ml_engine import run_ml_training_pipeline
            result = run_ml_training_pipeline()
            return result
        except Exception as e:
            print(f"ML training error: {e}")
            traceback.print_exc()
            return {"status": "FAILED", "reason": str(e)}
