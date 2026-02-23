"""
Alipay (支付宝) CSV Parser

Parses GB2312-encoded CSV exported from Alipay.
File structure:
  - Lines 0-23: metadata (name, account, date range, disclaimers)
  - Line 24: column headers
  - Line 25+: transaction data
"""

import re
from typing import Optional, List
import pandas as pd
from pathlib import Path
from .base import UUL_COLUMNS, create_empty_uul
from ..users import identify_user


def _detect_encoding(filepath: str) -> str:
    """Detect file encoding, trying GB2312/GBK first."""
    for enc in ["gb2312", "gbk", "utf-8-sig", "utf-8"]:
        try:
            with open(filepath, "r", encoding=enc) as f:
                f.read(2000)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"


def _parse_metadata(lines: List[str]) -> dict:
    """Extract user name and account from header lines."""
    metadata = {}
    for line in lines[:25]:
        if "姓名" in line or "姓名：" in line:
            # e.g. "姓名：赵锡盛"
            m = re.search(r"姓名[：:]\s*(.+)", line)
            if m:
                metadata["name"] = m.group(1).strip()
        if "支付宝账户" in line:
            m = re.search(r"支付宝账户[：:]\s*(\S+)", line)
            if m:
                metadata["account"] = m.group(1).strip()
    return metadata


def _extract_refund_original_id(tx_id: str) -> Optional[str]:
    """
    Extract original transaction ID from a refund's compound transaction ID.

    Alipay refund IDs use '_' or '*' to join: originalTxId_refundSuffix
    Returns the original ID if a separator is found, else None.
    """
    tx_id = tx_id.strip()
    for sep in ["_", "*"]:
        if sep in tx_id:
            candidate = tx_id.split(sep)[0].strip()
            if len(candidate) > 10:  # sanity check — real IDs are long
                return candidate
    return None


def parse_alipay(filepath: str) -> pd.DataFrame:
    """
    Parse an Alipay CSV file into UUL format.

    Args:
        filepath: Path to the Alipay CSV file

    Returns:
        DataFrame conforming to UUL schema
    """
    encoding = _detect_encoding(filepath)

    with open(filepath, "r", encoding=encoding, errors="replace") as f:
        all_lines = f.readlines()

    # Extract metadata for user identification
    metadata = _parse_metadata(all_lines)
    user_id = identify_user(
        name=metadata.get("name"),
        account=metadata.get("account"),
    )

    # Find header line (contains "交易时间")
    header_idx = None
    for i, line in enumerate(all_lines):
        if "交易时间" in line and "交易对方" in line:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(f"Cannot find header row in {filepath}")

    # Parse data lines
    records = []
    for line in all_lines[header_idx + 1 :]:
        line = line.strip().rstrip(",")
        if not line or line.startswith("-"):
            continue

        parts = line.split(",")
        if len(parts) < 11:
            continue

        # Extract fields
        timestamp_str = parts[0].strip()
        platform_category = parts[1].strip()
        counterparty = parts[2].strip()
        # parts[3] = 对方账号 (skip)
        description = parts[4].strip()
        direction = parts[5].strip()
        amount_str = parts[6].strip()
        payment_method = parts[7].strip()
        status = parts[8].strip()
        tx_id = parts[9].strip()
        merchant_order_id = parts[10].strip()
        note = parts[11].strip() if len(parts) > 11 else ""

        # Parse amount
        try:
            amount = float(amount_str)
        except ValueError:
            continue

        # Parse timestamp
        try:
            timestamp = pd.to_datetime(timestamp_str)
        except Exception:
            continue

        # Determine original tx ID for refunds
        original_tx_id = ""
        if status == "退款成功":
            orig = _extract_refund_original_id(tx_id)
            if orig:
                original_tx_id = orig

        records.append({
            "source_platform": "alipay",
            "user_id": user_id,
            "transaction_id": tx_id,
            "timestamp": timestamp,
            "direction": direction,
            "amount": amount,
            "counterparty": counterparty,
            "description": description,
            "payment_method": payment_method,
            "status": status,
            "platform_category": platform_category,
            "platform_tx_type": "",  # Alipay doesn't have this
            "original_tx_id": original_tx_id,
            "merchant_order_id": merchant_order_id,
            "note": note,
            # Defaults — will be filled by downstream modules
            "track": "",
            "is_refunded": False,
            "refund_amount": 0.0,
            "effective_amount": amount,
            "is_ignored": False,
            "global_category_l1": "",
            "global_category_l2": "",
        })

    if not records:
        return create_empty_uul()

    df = pd.DataFrame(records, columns=UUL_COLUMNS)
    return df
