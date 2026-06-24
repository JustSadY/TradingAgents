import logging

_logger = logging.getLogger(__name__)


def calculate_kelly_size(
    win_probability: float, win_loss_ratio: float, kelly_fraction: float = 0.5, max_cap: float = 0.20
) -> float:
    """
    Calculates the optimal position size using the Kelly Criterion.

    Formula: K% = W - [(1 - W) / R]
    W = Win Probability
    R = Win/Loss Ratio (Average profit / Average loss)

    Args:
        win_probability: Estimated probability of a successful trade (0 to 1).
        win_loss_ratio: Average win amount divided by average loss amount.
        kelly_fraction: Multiplier to be conservative (e.g., 0.5 for 'Half-Kelly').
        max_cap: Hard cap on position size (default 20%).

    Returns:
        float: Recommended position size as a decimal (0.05 = 5%).
    """
    if win_probability <= 0 or win_loss_ratio <= 0:
        return 0.0

    # Kelly Formula
    kelly_percent = win_probability - ((1 - win_probability) / win_loss_ratio)

    # Apply conservative fraction
    final_size = kelly_percent * kelly_fraction

    # Ensure it's not negative and apply cap
    final_size = max(0.0, min(final_size, max_cap))

    _logger.info(f"Kelly Calc: WinProb={win_probability:.2f}, R/R={win_loss_ratio:.2f}, Result={final_size:.4f}")
    return final_size


def get_risk_reward_from_plan(target_price: float, stop_loss: float, current_price: float) -> float:
    """Calculates R/R ratio based on proposed trade levels."""
    potential_profit = abs(target_price - current_price)
    potential_loss = abs(current_price - stop_loss)

    if potential_loss == 0:
        return 1.0

    return potential_profit / potential_loss
