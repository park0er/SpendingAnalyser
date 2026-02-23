"""
WeChat Pay (微信支付) XLSX Parser

Parses XLSX files exported from WeChat Pay.
File structure:
  - Rows 0-15: metadata (nickname, date range, stats)
  - Row 16: column headers
  - Row 17+: transaction data

WeChat exports quarterly files — this parser handles multiple files
and merges them into a single UUL DataFrame.
"""

import re
import glob
import openpyxl
import pandas as pd
from pathlib import Path
from .base import UUL_COLUMNS, create_empty_uul
from ..users import identify_user


def _parse_metadata_from_rows(rows: list) -> dict:
    """Extract user nickname from XLSX header rows."""
    metadata = {}
    for row in rows[:16]:
        cell = str(row[0]) if row[0] else ""
        # e.g. "微信昵称：[Parko]"
        m = re.search(r"微信昵称[：:]\s*\[?([^\]]+)\]?", cell)
        if m:
            metadata["name"] = m.group(1).strip()
    return metadata


def _clean_amount(amount_str: str) -> float:
    """Remove ¥ prefix and parse amount."""
    if not amount_str:
        return 0.0
    s = str(amount_str).replace("¥", "").replace("￥", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_refund_from_status(status: str) -> tuple[bool, float]:
    """
    Parse refund info from WeChat's '当前状态' field.

    Returns:
        (is_refunded, refund_amount)

    Examples:
        "已全额退款" -> (True, -1)  # -1 means full refund (use original amount)
        "已退款(￥14.00)" -> (True, 14.0)
        "已退款￥14.00" -> (True, 14.0)
        "支付成功" -> (False, 0)
    """
    if not status:
        return False, 0.0

    if "已全额退款" in status:
        return True, -1.0  # sentinel: full refund

    # Match patterns like "已退款(￥14.00)" or "已退款￥14.00"
    m = re.search(r"已退款[（(]?[¥￥]?([\d.]+)[）)]?", status)
    if m:
        return True, float(m.group(1))

    return False, 0.0


def parse_wechat_file(filepath: str) -> tuple[pd.DataFrame, str]:
    """
    Parse a single WeChat XLSX file.

    Returns:
        (DataFrame, user_id)
    """
    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    # Extract metadata
    metadata = _parse_metadata_from_rows(all_rows)
    user_id = identify_user(name=metadata.get("name"))

    # Find header row (contains "交易时间")
    header_idx = None
    for i, row in enumerate(all_rows):
        if row[0] and "交易时间" in str(row[0]):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(f"Cannot find header row in {filepath}")

    # Parse data rows
    records = []
    for row in all_rows[header_idx + 1 :]:
        if row[0] is None:
            continue

        timestamp_str = str(row[0]).strip()
        tx_type = str(row[1]).strip() if row[1] else ""
        counterparty = str(row[2]).strip() if row[2] else ""
        description = str(row[3]).strip() if row[3] else ""
        direction = str(row[4]).strip() if row[4] else ""
        amount = _clean_amount(row[5])
        payment_method = str(row[6]).strip() if row[6] else ""
        status = str(row[7]).strip() if row[7] else ""
        tx_id = str(row[8]).strip() if row[8] else ""
        merchant_order_id = str(row[9]).strip() if row[9] else ""
        note = str(row[10]).strip() if row[10] else ""

        # Handle None/empty merchant order
        if merchant_order_id == "None":
            merchant_order_id = ""

        # Parse timestamp
        try:
            timestamp = pd.to_datetime(timestamp_str)
        except Exception:
            continue

        # Direction: WeChat uses "/" for neutral transactions
        if direction == "/":
            direction = "中性"

        # Check refund status on original payment records
        is_refunded, refund_amt = _parse_refund_from_status(status)
        if is_refunded:
            if refund_amt == -1.0:
                # Full refund
                refund_amt = amount
            effective = amount - refund_amt
        else:
            effective = amount

        # Determine if this row is a refund income (XXX-退款)
        is_refund_income = "退款" in tx_type and direction == "收入"

        records.append({
            "source_platform": "wechat",
            "user_id": user_id,
            "transaction_id": tx_id,
            "timestamp": timestamp,
            "direction": direction,
            "amount": amount,
            "counterparty": counterparty,
            "description": description,
            "payment_method": payment_method,
            "status": status,
            "platform_category": "",  # WeChat has NO category
            "platform_tx_type": tx_type,
            "original_tx_id": "",  # WeChat doesn't provide this directly
            "merchant_order_id": merchant_order_id,
            "note": note,
            "track": "",
            "is_refunded": is_refunded,
            "refund_amount": refund_amt if is_refunded else 0.0,
            "effective_amount": effective,
            "is_ignored": is_refund_income,
            "global_category_l1": "",
            "global_category_l2": "",
        })

    if not records:
        return create_empty_uul(), user_id

    df = pd.DataFrame(records, columns=UUL_COLUMNS)
    return df, user_id


def parse_wechat(data_dir: str) -> pd.DataFrame:
    """
    Parse all WeChat XLSX files in a directory and merge them.

    Args:
        data_dir: Directory containing WeChat XLSX files

    Returns:
        Merged DataFrame conforming to UUL schema
    """
    pattern = str(Path(data_dir) / "微信支付账单流水文件*.xlsx")
    files = sorted(glob.glob(pattern))

    if not files:
        return create_empty_uul()

    dfs = []
    for f in files:
        df, _ = parse_wechat_file(f)
        dfs.append(df)

    merged = pd.concat(dfs, ignore_index=True)

    # Deduplicate by transaction_id (in case quarterly files overlap)
    merged = merged.drop_duplicates(subset=["transaction_id"], keep="first")

    # Sort by timestamp descending
    merged = merged.sort_values("timestamp", ascending=False).reset_index(drop=True)

    return merged
