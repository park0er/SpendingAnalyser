"""
Refund Netting — 退款对冲算法

Platform-specific logic to match refunds to original transactions
and calculate effective (net) amounts.
"""

import pandas as pd


def _net_alipay_refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Alipay refund netting via transaction ID split.

    Refund records have compound IDs: originalTxId_refundSuffix or originalTxId*refundSuffix.
    The original_tx_id field was already extracted by the parser.
    """
    # Build lookup: transaction_id -> row index (for expenditures)
    tx_index = {}
    for idx, row in df.iterrows():
        if row["source_platform"] == "alipay" and row["direction"] == "支出":
            tx_index[row["transaction_id"]] = idx

    # Process refunds
    for idx, row in df.iterrows():
        if row["source_platform"] != "alipay":
            continue
        if row["status"] != "退款成功":
            continue

        # This is a refund record — mark it as ignored
        df.at[idx, "is_ignored"] = True
        df.at[idx, "track"] = "refund_processed"

        # Try to match to original
        orig_id = row["original_tx_id"]
        if orig_id and orig_id in tx_index:
            orig_idx = tx_index[orig_id]
            refund_amt = row["amount"]

            # Accumulate refund on original record
            df.at[orig_idx, "is_refunded"] = True
            df.at[orig_idx, "refund_amount"] += refund_amt
            df.at[orig_idx, "effective_amount"] = max(
                0, df.at[orig_idx, "amount"] - df.at[orig_idx, "refund_amount"]
            )

    return df


def _net_wechat_refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    WeChat refund netting via status field self-description.

    The WeChat parser already set is_refunded, refund_amount, and effective_amount
    based on the '当前状态' field. This function just ensures refund income rows
    are properly ignored.
    """
    for idx, row in df.iterrows():
        if row["source_platform"] != "wechat":
            continue

        # Refund income rows (交易类型 = 'XXX-退款') are already marked is_ignored by parser
        # Just ensure track is set
        if row["is_ignored"] and "退款" in str(row["platform_tx_type"]):
            df.at[idx, "track"] = "refund_processed"

    return df


def apply_refund_netting(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply refund netting to the entire UUL DataFrame.

    This modifies:
    - Original payment records: is_refunded, refund_amount, effective_amount
    - Refund income records: is_ignored = True, track = refund_processed
    """
    df = df.copy()

    # Ensure numeric columns
    df["refund_amount"] = df["refund_amount"].fillna(0).astype(float)
    df["effective_amount"] = df["effective_amount"].fillna(0).astype(float)

    df = _net_alipay_refunds(df)
    df = _net_wechat_refunds(df)

    return df
