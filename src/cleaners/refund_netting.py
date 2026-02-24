"""
Refund Netting — 退款对冲算法

Platform-specific logic to match refunds to original transactions
and calculate effective (net) amounts.
"""

import re
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


def _net_jd_refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    JD refund netting.

    JD inline refund amounts (e.g. "293.10(已全额退款)") are already handled
    by the parser which sets is_refunded, refund_amount, effective_amount.

    This function ensures standalone refund rows (交易状态=退款成功) are
    properly marked as ignored.
    """
    for idx, row in df.iterrows():
        if row["source_platform"] != "jd":
            continue
        if row["status"] == "退款成功":
            df.at[idx, "is_ignored"] = True
            df.at[idx, "track"] = "refund_processed"

    return df


def _extract_merchant_keyword(title: str) -> str:
    """
    Extract a merchant keyword from Meituan order title for fuzzy matching.

    Examples:
        "小象超市-订单编号1364001542164368" -> "小象超市"
        "阿招鸡煲代金券" -> "阿招鸡煲"
        "LUSH单人餐" -> "LUSH"
        "许家菜4人餐" -> "许家菜"
    """
    title = str(title).strip()
    # Remove common suffixes: 代金券, X人餐, 单人餐, 招牌X, 订单详情, etc.
    title = re.sub(r"(代金券|\d+人餐|单人餐|双人餐|订单详情|订单编号\S+)", "", title)
    # Remove "美团商家代金券-数字" pattern
    title = re.sub(r"美团商家代金券-\d+", "", title)
    # Remove "小象超市-订单编号XXX" -> keep "小象超市"
    title = re.sub(r"-订单编号\S+", "", title)
    # Take the first meaningful segment (split by common delimiters)
    for sep in ["(", "（", "-", "·", " "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def _net_meituan_refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Meituan refund netting via adjacent-row reverse matching.

    For each refund row (交易类型=退款), searches backward within 10 rows
    to find a matching payment row with similar merchant name and
    sufficient amount. On match, deducts from the original's effective_amount.
    """
    meituan_mask = df["source_platform"] == "meituan"
    meituan_indices = df[meituan_mask].index.tolist()

    for pos, idx in enumerate(meituan_indices):
        row = df.loc[idx]
        if row["platform_tx_type"] != "退款":
            continue

        refund_amount = row["amount"]
        refund_keyword = _extract_merchant_keyword(row["counterparty"])

        # Mark refund row as ignored
        df.at[idx, "is_ignored"] = True
        df.at[idx, "track"] = "refund_processed"

        if not refund_keyword:
            continue

        # Search backward in the meituan sub-list (up to 10 rows)
        matched = False
        search_start = max(0, pos - 10)
        for search_pos in range(pos - 1, search_start - 1, -1):
            candidate_idx = meituan_indices[search_pos]
            candidate = df.loc[candidate_idx]

            if candidate["platform_tx_type"] != "支付":
                continue
            if candidate["is_refunded"]:
                continue  # Already matched to another refund

            candidate_keyword = _extract_merchant_keyword(candidate["counterparty"])

            # Fuzzy match: either keyword contains the other, or they share
            # a significant common substring
            if (refund_keyword in candidate_keyword or
                    candidate_keyword in refund_keyword):
                if refund_amount <= candidate["amount"]:
                    # Match found — deduct from original
                    df.at[candidate_idx, "is_refunded"] = True
                    df.at[candidate_idx, "refund_amount"] += refund_amount
                    df.at[candidate_idx, "effective_amount"] = max(
                        0,
                        candidate["amount"] - df.at[candidate_idx, "refund_amount"]
                    )
                    matched = True
                    break

        if not matched:
            # Unmatched refund — keep as negative effective_amount for natural offset
            df.at[idx, "effective_amount"] = -refund_amount

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
    df = _net_jd_refunds(df)
    df = _net_meituan_refunds(df)

    return df
