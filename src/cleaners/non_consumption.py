"""
Non-consumption Filter — 非消费项过滤与双轨分流

Separates real consumption from cashflow (transfers, red packets,
investments, credit repayments, etc.)
"""

import re
import pandas as pd


# Alipay categories that belong to cashflow track
ALIPAY_CASHFLOW_CATEGORIES = {
    "转账红包",
    "投资理财",
    "信用借还",
    "收入",
}

# WeChat transaction types that are cashflow
WECHAT_CASHFLOW_TYPES = {
    "转账",
    "微信红包（单发）",
    "微信红包（群红包）",
    "微信红包",
    "二维码收款",
    "群收款",
}

# Partial match patterns for WeChat cashflow
WECHAT_CASHFLOW_PATTERNS = [
    "转入零钱通",
    "零钱通",
]


def _classify_alipay_track(row: pd.Series) -> str:
    """Determine track for an Alipay record."""
    # Already processed refunds
    if row["track"] == "refund_processed":
        return "refund_processed"

    # 不计收支 -> cashflow
    if row["direction"] == "不计收支":
        return "cashflow"

    # 收入 direction -> cashflow
    if row["direction"] == "收入":
        return "cashflow"

    # Cashflow categories
    if row["platform_category"] in ALIPAY_CASHFLOW_CATEGORIES:
        return "cashflow"

    # 退款 category (unmatched refunds) -> cashflow
    if row["platform_category"] == "退款":
        return "cashflow"

    # Everything else with direction=支出 -> consumption
    if row["direction"] == "支出":
        return "consumption"

    return "cashflow"


def _classify_wechat_track(row: pd.Series) -> str:
    """Determine track for a WeChat record."""
    # Already processed refunds
    if row["track"] == "refund_processed":
        return "refund_processed"

    # Refund income rows
    if row["is_ignored"]:
        return "refund_processed"

    tx_type = str(row["platform_tx_type"])

    # Explicit cashflow types
    if tx_type in WECHAT_CASHFLOW_TYPES:
        return "cashflow"

    # Pattern-based cashflow
    for pattern in WECHAT_CASHFLOW_PATTERNS:
        if pattern in tx_type:
            return "cashflow"

    # Refund types
    if "退款" in tx_type:
        return "refund_processed"

    # 收入 direction -> cashflow
    if row["direction"] == "收入":
        return "cashflow"

    # 中性 (neutral) -> cashflow
    if row["direction"] == "中性":
        return "cashflow"

    # 扫二维码付款 with status "已转账" -> cashflow (person-to-person)
    if tx_type == "扫二维码付款" and "已转账" in str(row["status"]):
        return "cashflow"

    # 商户消费 / 扫二维码付款 (with 支付成功) -> consumption
    if tx_type in ("商户消费", "扫二维码付款"):
        return "consumption"

    return "cashflow"


def _classify_jd_track(row: pd.Series) -> str:
    """Determine track for a JD record."""
    # Already processed refunds
    if row["track"] == "refund_processed":
        return "refund_processed"

    # Standalone refund rows
    if row["status"] == "退款成功":
        return "refund_processed"

    # 不计收支 → cashflow (白条还款, 小金库, 预授权 etc.)
    if row["direction"] == "不计收支":
        return "cashflow"

    # 收入 → cashflow (小金库红包 etc.)
    if row["direction"] == "收入":
        return "cashflow"

    # 支出 → consumption
    if row["direction"] == "支出":
        return "consumption"

    return "cashflow"


def _classify_meituan_track(row: pd.Series) -> str:
    """Determine track for a Meituan record."""
    # Already processed refunds
    if row["track"] == "refund_processed":
        return "refund_processed"

    tx_type = str(row["platform_tx_type"])

    # 退款 → refund_processed
    if tx_type == "退款":
        return "refund_processed"

    # 还款 (美团月付代扣还款) → cashflow
    if tx_type == "还款":
        return "cashflow"

    # 支付 + 支出 → consumption
    if tx_type == "支付" and row["direction"] == "支出":
        return "consumption"

    return "cashflow"


def apply_track_classification(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classify each record into consumption or cashflow track.

    Must be run AFTER refund netting.
    """
    df = df.copy()

    for idx, row in df.iterrows():
        if row["track"] and row["track"] != "":
            # Already classified (e.g. refund_processed)
            continue

        if row["source_platform"] == "alipay":
            df.at[idx, "track"] = _classify_alipay_track(row)
        elif row["source_platform"] == "wechat":
            df.at[idx, "track"] = _classify_wechat_track(row)
        elif row["source_platform"] == "jd":
            df.at[idx, "track"] = _classify_jd_track(row)
        elif row["source_platform"] == "meituan":
            df.at[idx, "track"] = _classify_meituan_track(row)

    return df
