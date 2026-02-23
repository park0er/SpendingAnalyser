"""
UUL (Unified Universal Ledger) Schema — 统一标准账单数据模型

All platform parsers output DataFrames conforming to this schema.
"""

import pandas as pd

# Column definitions for the UUL DataFrame
UUL_COLUMNS = [
    "source_platform",      # str: alipay / wechat
    "user_id",              # str: user profile key (e.g. "parko")
    "transaction_id",       # str: platform-original transaction ID
    "timestamp",            # datetime: UTC+8
    "direction",            # str: 支出 / 收入 / 不计收支 / 中性
    "amount",               # float: absolute amount (always positive)
    "counterparty",         # str: merchant / person name
    "description",          # str: item / order description
    "payment_method",       # str: payment channel
    "status",               # str: original platform status
    "platform_category",    # str: platform-native category (Alipay has it; WeChat doesn't)
    "platform_tx_type",     # str: WeChat '交易类型' (商户消费/转账/红包 etc.)
    "original_tx_id",       # str: linked original tx ID for refunds
    "merchant_order_id",    # str: merchant-side order ID
    "note",                 # str: remarks / notes
    "track",                # str: consumption / cashflow / refund_pending
    "is_refunded",          # bool: whether this record has been (fully/partially) refunded
    "refund_amount",        # float: amount refunded against this record
    "effective_amount",     # float: amount - refund_amount (net spend)
    "is_ignored",           # bool: True for refund income rows (don't count)
    "global_category_l1",   # str: L1 category from taxonomy
    "global_category_l2",   # str: L2 category from taxonomy
]


def create_empty_uul() -> pd.DataFrame:
    """Create an empty DataFrame with UUL schema."""
    df = pd.DataFrame(columns=UUL_COLUMNS)
    # Set dtypes
    df = df.astype({
        "source_platform": "object",
        "user_id": "object",
        "transaction_id": "object",
        "direction": "object",
        "amount": "float64",
        "counterparty": "object",
        "description": "object",
        "payment_method": "object",
        "status": "object",
        "platform_category": "object",
        "platform_tx_type": "object",
        "original_tx_id": "object",
        "merchant_order_id": "object",
        "note": "object",
        "track": "object",
        "is_refunded": "bool",
        "refund_amount": "float64",
        "effective_amount": "float64",
        "is_ignored": "bool",
        "global_category_l1": "object",
        "global_category_l2": "object",
    })
    return df


def validate_uul(df: pd.DataFrame) -> None:
    """Validate that a DataFrame conforms to UUL schema."""
    missing = set(UUL_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"UUL validation failed — missing columns: {missing}")
