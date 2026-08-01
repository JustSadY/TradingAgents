import asyncio
from typing import Any

import numpy as np
import yfinance as yf

def _local_extrema(prices: np.ndarray, order: int = 5) -> tuple[list[int], list[int]]:
    maxima: list[int] = []
    minima: list[int] = []
    n = len(prices)
    for i in range(order, n - order):
        window_l = prices[i - order : i]
        window_r = prices[i + 1 : i + order + 1]
        if prices[i] >= window_l.max() and prices[i] >= window_r.max():
            maxima.append(i)
        if prices[i] <= window_l.min() and prices[i] <= window_r.min():
            minima.append(i)
    return maxima, minima

def _detect_double_top(
    prices: np.ndarray,
    dates: list[str],
    maxima: list[int],
    minima: list[int],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for k in range(len(maxima) - 1):
        p1, p2 = maxima[k], maxima[k + 1]
        h1, h2 = prices[p1], prices[p2]
        if abs(h1 - h2) / max(h1, h2) > 0.03:
            continue
        if p2 - p1 < 10:
            continue
        mid_mins = [m for m in minima if p1 < m < p2]
        if not mid_mins:
            continue
        neck_idx = min(mid_mins, key=lambda m: prices[m])
        neckline = float(prices[neck_idx])
        if (max(h1, h2) - neckline) / max(h1, h2) < 0.03:
            continue
        after = prices[p2 : min(p2 + 20, len(prices))]
        broken = bool(len(after) > 0 and float(after.min()) < neckline)
        patterns.append(
            {
                "type": "double_top",
                "label": "Double Top",
                "direction": "bearish",
                "start_date": dates[p1],
                "end_date": dates[min(p2 + 10, len(dates) - 1)],
                "key_points": [
                    {"date": dates[p1], "price": round(float(h1), 2), "label": "Top 1"},
                    {"date": dates[neck_idx], "price": round(neckline, 2), "label": "Neckline"},
                    {"date": dates[p2], "price": round(float(h2), 2), "label": "Top 2"},
                ],
                "confidence": 0.75 if broken else 0.55,
            }
        )
    return patterns

def _detect_double_bottom(
    prices: np.ndarray,
    dates: list[str],
    maxima: list[int],
    minima: list[int],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for k in range(len(minima) - 1):
        t1, t2 = minima[k], minima[k + 1]
        l1, l2 = prices[t1], prices[t2]
        if abs(l1 - l2) / max(l1, l2) > 0.03:
            continue
        if t2 - t1 < 10:
            continue
        mid_maxs = [m for m in maxima if t1 < m < t2]
        if not mid_maxs:
            continue
        neck_idx = max(mid_maxs, key=lambda m: prices[m])
        neckline = float(prices[neck_idx])
        if (neckline - min(l1, l2)) / neckline < 0.03:
            continue
        after = prices[t2 : min(t2 + 20, len(prices))]
        broken = bool(len(after) > 0 and float(after.max()) > neckline)
        patterns.append(
            {
                "type": "double_bottom",
                "label": "Double Bottom",
                "direction": "bullish",
                "start_date": dates[t1],
                "end_date": dates[min(t2 + 10, len(dates) - 1)],
                "key_points": [
                    {"date": dates[t1], "price": round(float(l1), 2), "label": "Bottom 1"},
                    {"date": dates[neck_idx], "price": round(neckline, 2), "label": "Neckline"},
                    {"date": dates[t2], "price": round(float(l2), 2), "label": "Bottom 2"},
                ],
                "confidence": 0.75 if broken else 0.55,
            }
        )
    return patterns

def _detect_head_and_shoulders(
    prices: np.ndarray,
    dates: list[str],
    maxima: list[int],
    minima: list[int],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for k in range(len(maxima) - 2):
        ls, hd, rs = maxima[k], maxima[k + 1], maxima[k + 2]
        lh, hh, rh = float(prices[ls]), float(prices[hd]), float(prices[rs])
        if not (hh > lh and hh > rh):
            continue
        if abs(lh - rh) / max(lh, rh) > 0.06:
            continue
        if rs - ls < 20:
            continue
        left_mins = [m for m in minima if ls < m < hd]
        right_mins = [m for m in minima if hd < m < rs]
        if not left_mins or not right_mins:
            continue
        lt = min(left_mins, key=lambda m: prices[m])
        rt = min(right_mins, key=lambda m: prices[m])
        neckline = (float(prices[lt]) + float(prices[rt])) / 2
        after = prices[rs : min(rs + 20, len(prices))]
        broken = bool(len(after) > 0 and float(after.min()) < neckline)
        patterns.append(
            {
                "type": "head_and_shoulders",
                "label": "Head & Shoulders",
                "direction": "bearish",
                "start_date": dates[ls],
                "end_date": dates[min(rs + 10, len(dates) - 1)],
                "key_points": [
                    {"date": dates[ls], "price": round(lh, 2), "label": "Left Shoulder"},
                    {"date": dates[lt], "price": round(float(prices[lt]), 2), "label": "Neckline"},
                    {"date": dates[hd], "price": round(hh, 2), "label": "Head"},
                    {"date": dates[rt], "price": round(float(prices[rt]), 2), "label": "Neckline"},
                    {"date": dates[rs], "price": round(rh, 2), "label": "Right Shoulder"},
                ],
                "confidence": 0.80 if broken else 0.60,
            }
        )
    return patterns

def _detect_inv_head_and_shoulders(
    prices: np.ndarray,
    dates: list[str],
    maxima: list[int],
    minima: list[int],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for k in range(len(minima) - 2):
        ls, hd, rs = minima[k], minima[k + 1], minima[k + 2]
        lh, hh, rh = float(prices[ls]), float(prices[hd]), float(prices[rs])
        if not (hh < lh and hh < rh):
            continue
        if abs(lh - rh) / max(lh, rh) > 0.06:
            continue
        if rs - ls < 20:
            continue
        left_maxs = [m for m in maxima if ls < m < hd]
        right_maxs = [m for m in maxima if hd < m < rs]
        if not left_maxs or not right_maxs:
            continue
        lt = max(left_maxs, key=lambda m: prices[m])
        rt = max(right_maxs, key=lambda m: prices[m])
        neckline = (float(prices[lt]) + float(prices[rt])) / 2
        after = prices[rs : min(rs + 20, len(prices))]
        broken = bool(len(after) > 0 and float(after.max()) > neckline)
        patterns.append(
            {
                "type": "inv_head_and_shoulders",
                "label": "Inv. Head & Shoulders",
                "direction": "bullish",
                "start_date": dates[ls],
                "end_date": dates[min(rs + 10, len(dates) - 1)],
                "key_points": [
                    {"date": dates[ls], "price": round(lh, 2), "label": "Left Shoulder"},
                    {"date": dates[hd], "price": round(hh, 2), "label": "Head"},
                    {"date": dates[rs], "price": round(rh, 2), "label": "Right Shoulder"},
                ],
                "confidence": 0.80 if broken else 0.60,
            }
        )
    return patterns

def _detect_flags(prices: np.ndarray, dates: list[str]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    n = len(prices)
    pole_len = 10
    flag_min = 5
    flag_max = 15
    seen_pole_starts: list[int] = []

    for i in range(n - flag_min - 1, pole_len - 1, -1):
        pole_start = i - pole_len
        if any(abs(s - pole_start) < 8 for s in seen_pole_starts):
            continue

        pole_return = (prices[i] - prices[pole_start]) / prices[pole_start]
        if abs(pole_return) < 0.07:
            continue

        for flag_end in range(i + flag_min, min(i + flag_max + 1, n)):
            flag_prices = prices[i : flag_end + 1]
            flag_range = (float(flag_prices.max()) - float(flag_prices.min())) / float(prices[i])
            if flag_range >= 0.06:
                break
            flag_trend = (float(prices[flag_end]) - float(prices[i])) / float(prices[i])
            if pole_return > 0 and -0.05 <= flag_trend <= 0.01:
                seen_pole_starts.append(pole_start)
                patterns.append(
                    {
                        "type": "bull_flag",
                        "label": "Bull Flag",
                        "direction": "bullish",
                        "start_date": dates[pole_start],
                        "end_date": dates[flag_end],
                        "key_points": [
                            {
                                "date": dates[pole_start],
                                "price": round(float(prices[pole_start]), 2),
                                "label": "Pole Start",
                            },
                            {"date": dates[i], "price": round(float(prices[i]), 2), "label": "Flag Start"},
                            {"date": dates[flag_end], "price": round(float(prices[flag_end]), 2), "label": "Flag End"},
                        ],
                        "confidence": 0.65,
                    }
                )
                break
            elif pole_return < 0 and -0.01 <= flag_trend <= 0.05:
                seen_pole_starts.append(pole_start)
                patterns.append(
                    {
                        "type": "bear_flag",
                        "label": "Bear Flag",
                        "direction": "bearish",
                        "start_date": dates[pole_start],
                        "end_date": dates[flag_end],
                        "key_points": [
                            {
                                "date": dates[pole_start],
                                "price": round(float(prices[pole_start]), 2),
                                "label": "Pole Start",
                            },
                            {"date": dates[i], "price": round(float(prices[i]), 2), "label": "Flag Start"},
                            {"date": dates[flag_end], "price": round(float(prices[flag_end]), 2), "label": "Flag End"},
                        ],
                        "confidence": 0.65,
                    }
                )
                break

        if len(patterns) >= 3:
            break

    return patterns

def _dedup(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for p in patterns:
        key = f"{p['type']}_{p['start_date'][:7]}"
        if key not in seen or p["confidence"] > seen[key]["confidence"]:
            seen[key] = p
    return list(seen.values())

async def detect_patterns(ticker: str, period: str = "1y") -> list[dict[str, Any]]:
    def _fetch() -> Any:
        return yf.download(ticker, period=period, progress=False, auto_adjust=True)

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, _fetch)

    if raw.empty or len(raw) < 30:
        return []

    close_col = raw["Close"]
    if hasattr(close_col, "columns"):
        close_col = close_col[ticker]
    close_col = close_col.dropna()

    prices = np.array(close_col.values, dtype=float)
    dates = [str(d)[:10] for d in close_col.index.tolist()]

    if len(prices) < 30:
        return []

    kernel = np.ones(3) / 3
    smoothed = np.convolve(prices, kernel, mode="same")
    smoothed[0] = prices[0]
    smoothed[-1] = prices[-1]

    order = max(5, len(prices) // 25)
    maxima, minima = _local_extrema(smoothed, order=order)

    all_patterns: list[dict[str, Any]] = []
    all_patterns.extend(_detect_double_top(prices, dates, maxima, minima))
    all_patterns.extend(_detect_double_bottom(prices, dates, maxima, minima))
    all_patterns.extend(_detect_head_and_shoulders(prices, dates, maxima, minima))
    all_patterns.extend(_detect_inv_head_and_shoulders(prices, dates, maxima, minima))
    all_patterns.extend(_detect_flags(prices, dates))

    deduped = _dedup(all_patterns)
    deduped.sort(key=lambda x: x["confidence"], reverse=True)
    return deduped[:8]
