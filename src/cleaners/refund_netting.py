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


def _extract_merchant_keywords(title: str) -> list[str]:
    """
    Extract merchant keywords from Meituan order title for fuzzy matching.
    Returns a list of candidate keywords (longest first) for flexible matching.

    Examples:
        "小象超市-订单编号1364001542164368" -> ["小象超市"]
        "阿招鸡煲代金券" -> ["阿招鸡煲"]
        "LUSH单人餐" -> ["LUSH"]
        "Tims天好咖啡·贝果·暖食(西三旗万象汇店) 订单详情" -> ["Tims天好咖啡", "Tims"]
        "COSTA咖啡(回龙观华联1店) 订单详情" -> ["COSTA咖啡", "COSTA"]
        "喜茶（北京辉煌国际店） 订单详情" -> ["喜茶"]
        "喜茶（北京辉煌国际店）-301721361180131048" -> ["喜茶"]
        "宅舍 HOUSE 推拿院" -> ["宅舍 HOUSE 推拿院", "宅舍"]
        "美团商家代金券-289529094000906348" -> ["美团商家代金券-289529094000906348"]  (exact match by full title)
    """
    title = str(title).strip()

    keywords = []

    # Always include the full raw title first for exact-match scenarios
    # (e.g. 美团商家代金券-289529094000906348 purchase ↔ refund)
    keywords.append(title)

    # Remove common suffixes
    cleaned = re.sub(r"(代金券|招牌[^\s]*|订单详情|订单编号\S+)", "", title)
    # Remove trailing number IDs like "-301721361180131048"
    cleaned = re.sub(r"-\d{10,}$", "", cleaned)
    # Remove meal suffixes
    cleaned = re.sub(r"\d+人餐|单人餐|双人餐", "", cleaned)
    # Remove "-订单编号XXX"
    cleaned = re.sub(r"-订单编号\S+", "", cleaned)

    # Add cleaned version if different from raw
    full = cleaned.strip()
    if full and full != title:
        keywords.append(full)

    # Split by common delimiters and take first segment
    for sep in ["(", "（", "-", "·", " "]:
        if sep in cleaned:
            first = cleaned.split(sep)[0].strip()
            if first and first not in keywords:
                keywords.append(first)
            break  # Only split by the first found delimiter

    # Extract pure brand names (Latin/CJK prefix before mixing)
    brand = re.match(r"^([A-Za-z]+)", cleaned)
    if brand:
        b = brand.group(1)
        if b not in keywords and len(b) >= 2:
            keywords.append(b)

    return keywords


def _net_meituan_refunds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Meituan refund netting via global index matching.

    Builds a global index of all Meituan payment rows keyed by merchant
    keywords. For each refund row, looks up candidates by keyword and
    picks the best match (closest in time, amount ≥ refund).
    """
    meituan_mask = df["source_platform"] == "meituan"
    meituan_df = df[meituan_mask]

    # Build global index: keyword -> list of (idx, amount, timestamp)
    from collections import defaultdict
    payment_index = defaultdict(list)

    for idx, row in meituan_df.iterrows():
        if row["platform_tx_type"] != "支付":
            continue
        keywords = _extract_merchant_keywords(row["counterparty"])
        for kw in keywords:
            payment_index[kw].append(idx)

    # Process refund rows
    for idx, row in meituan_df.iterrows():
        if row["platform_tx_type"] != "退款":
            continue

        refund_amount = row["amount"]
        refund_keywords = _extract_merchant_keywords(row["counterparty"])

        # Mark refund row as ignored
        df.at[idx, "is_ignored"] = True
        df.at[idx, "track"] = "refund_processed"

        if not refund_keywords:
            # Coupon refunds — no matching payment expected
            df.at[idx, "effective_amount"] = -refund_amount
            continue

        # Search for matching payment across all keywords
        matched = False
        for kw in refund_keywords:
            if kw not in payment_index:
                continue

            candidates = payment_index[kw]
            for candidate_idx in candidates:
                candidate = df.loc[candidate_idx]

                if candidate["is_refunded"]:
                    continue  # Already matched

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

            if matched:
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
