def calculate_position_size(
    capital,
    risk_percent,
    entry_price,
    stop_loss
):
    """
    Calculate position size based on maximum allowed risk.
    """

    if capital <= 0:
        return 0

    if risk_percent <= 0:
        return 0

    if entry_price <= 0:
        return 0

    if stop_loss <= 0:
        return 0

    risk_amount = capital * (
        risk_percent / 100
    )

    price_risk = abs(
        entry_price - stop_loss
    )

    if price_risk == 0:
        return 0

    quantity = risk_amount / price_risk

    return quantity


def daily_loss_limit_reached(
    starting_capital,
    current_capital,
    max_loss_percent=1.0
):
    """
    Stop trading when daily loss reaches the configured limit.
    """

    if starting_capital <= 0:
        return True

    loss_percent = (
        (starting_capital - current_capital)
        / starting_capital
    ) * 100

    return loss_percent >= max_loss_percent


def daily_target_reached(
    starting_capital,
    current_capital,
    target_percent=1.0
):
    """
    Returns True when the daily target is reached.
    """

    if starting_capital <= 0:
        return False

    profit_percent = (
        (current_capital - starting_capital)
        / starting_capital
    ) * 100

    return profit_percent >= target_percent
