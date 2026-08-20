"""
AI Trading Engine — Position Manager

Handles all post-entry position management:
- Partial take-profit
- Break-even stops
- Trailing stops
- Dynamic SL adjustment
- Maximum holding period
"""

from trading.db import update_position


class PositionManager:
    """Manages open positions after entry."""

    def __init__(self, config):
        self.config = config

    def update(self, con, position, current_price):
        """
        Update position management for a single position.
        Called every scan cycle for each open position.
        """
        pos_id = position["id"]
        side = position["side"]
        entry = position["entry_price"]
        sl = position["stop_loss"]
        tp1 = position["take_profit1"]
        tp2 = position["take_profit2"]
        qty = position["remaining_qty"]
        total_qty = position["quantity"]

        if side == "LONG":
            pnl_pct = (current_price - entry) / entry * 100 if entry > 0 else 0
        else:
            pnl_pct = (entry - current_price) / entry * 100 if entry > 0 else 0

        updates = {"current_price": current_price}

        # Track max favorable excursion
        if side == "LONG":
            if current_price > position.get("max_price", 0):
                updates["max_price"] = current_price
        else:
            if current_price < position.get("min_price", 999999):
                updates["min_price"] = current_price

        # === BREAK-EVEN ===
        be_activation = self.config.get("break_even_activation_pct", 0.3)
        if not position.get("break_even", 0) and pnl_pct >= be_activation:
            if side == "LONG":
                new_sl = max(sl, entry * 1.001)  # Slightly above entry
                updates["stop_loss"] = new_sl
            else:
                new_sl = min(sl, entry * 0.999)
                updates["stop_loss"] = new_sl
            updates["break_even"] = 1

        # === PARTIAL TAKE PROFIT 1 ===
        tp1_rr = self.config.get("tp1_rr", 1.5)
        sl_distance = abs(entry - sl) if sl else entry * 0.01
        tp1_target = entry + (sl_distance * tp1_rr) if side == "LONG" else entry - (sl_distance * tp1_rr)

        if not position.get("tp1_hit", 0) and tp1:
            if (side == "LONG" and current_price >= tp1) or (side == "SHORT" and current_price <= tp1):
                close_pct = self.config.get("tp1_close_pct", 0.3)
                close_qty = round(total_qty * close_pct, 8)
                if close_qty > 0 and close_qty <= qty:
                    updates["remaining_qty"] = qty - close_qty
                    updates["tp1_hit"] = 1
                    # Move SL to break-even after TP1
                    if side == "LONG":
                        updates["stop_loss"] = max(entry, sl)
                    else:
                        updates["stop_loss"] = min(entry, sl)

        # === PARTIAL TAKE PROFIT 2 ===
        tp2_rr = self.config.get("tp2_rr", 2.5)
        tp2_target = entry + (sl_distance * tp2_rr) if side == "LONG" else entry - (sl_distance * tp2_rr)

        if not position.get("tp2_hit", 0) and tp2:
            current_remaining = updates.get("remaining_qty", qty)
            if (side == "LONG" and current_price >= tp2) or (side == "SHORT" and current_price <= tp2):
                close_pct = self.config.get("tp2_close_pct", 0.4)
                close_qty = round(total_qty * close_pct, 8)
                if close_qty > 0 and close_qty <= current_remaining:
                    updates["remaining_qty"] = current_remaining - close_qty
                    updates["tp2_hit"] = 1

        # === TRAILING STOP ===
        activation_rr = self.config.get("trailing_stop_activation_rr", 1.0)
        activation_pnl = sl_distance * activation_rr / entry * 100 if entry > 0 else 0.5

        if pnl_pct >= activation_pnl and not position.get("trailing_active", 0):
            updates["trailing_active"] = 1

        if position.get("trailing_active", 0) or updates.get("trailing_active", 0):
            trail_dist_pct = self.config.get("trailing_stop_distance_pct", 0.5)
            if side == "LONG":
                new_trail = current_price * (1 - trail_dist_pct / 100)
                old_trail = position.get("trailing_stop", 0)
                if new_trail > old_trail:
                    updates["trailing_stop"] = new_trail
            else:
                new_trail = current_price * (1 + trail_dist_pct / 100)
                old_trail = position.get("trailing_stop", 999999)
                if new_trail < old_trail:
                    updates["trailing_stop"] = new_trail

        # Apply updates
        if len(updates) > 1:  # More than just current_price
            update_position(con, pos_id, **updates)

        return updates
