"""
JD (京东) CSV Parser

Parses UTF-8 (BOM) CSV exported from JD Finance.
File structure:
  - Lines 0-20: metadata (account info, stats, disclaimers)
  - Line 21: column headers (交易时间,商户名称,交易说明,金额,...)
  - Line 22+: transaction data

Special handling:
  - Amount field may contain inline refund info: "293.10(已全额退款)" or "2977.63(已退款2974.66)"
  - Fields have trailing whitespace that must be stripped
"""

import re
import pandas as pd
from pathlib import Path
from .base import UUL_COLUMNS, create_empty_uul
from ..users import identify_user


# Regex for parsing inline refund amounts
# Matches: "293.10(已全额退款)" or "2977.63(已退款2974.66)"
RE_FULL_REFUND = re.compile(r"^([\d.]+)\(已全额退款\)$")
RE_PARTIAL_REFUND = re.compile(r"^([\d.]+)\(已退款([\d.]+)\)$")


def _parse_amount_field(raw: str) -> tuple[float, float, float]:
    """
    Parse JD's amount field which may contain inline refund info.

    Returns:
        (amount, refund_amount, effective_amount)
    """
    raw = raw.strip()

    # Full refund: "293.10(已全额退款)"
    m = RE_FULL_REFUND.match(raw)
    if m:
        amount = float(m.group(1))
        return amount, amount, 0.0

    # Partial refund: "2977.63(已退款2974.66)"
    m = RE_PARTIAL_REFUND.match(raw)
    if m:
        amount = float(m.group(1))
        refunded = float(m.group(2))
        return amount, refunded, round(amount - refunded, 2)

    # Normal amount: "375.00"
    try:
        amount = float(raw)
        return amount, 0.0, amount
    except ValueError:
        return 0.0, 0.0, 0.0


def parse_jd(filepath: str) -> pd.DataFrame:
    """
    Parse a JD CSV file into UUL format.

    Args:
        filepath: Path to the JD CSV file

    Returns:
        DataFrame conforming to UUL schema
    """
    # JD exports as UTF-8 with BOM
    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        all_lines = f.readlines()

    # Find header line (contains "交易时间" and "商户名称")
    header_idx = None
    for i, line in enumerate(all_lines):
        if "交易时间" in line and "商户名称" in line:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(f"Cannot find header row in {filepath}")

    # User identification — JD doesn't have name in metadata easily,
    # default to "parko" for now
    user_id = "parko"

    # Parse data lines
    records = []
    for line in all_lines[header_idx + 1:]:
        line = line.strip().rstrip(",")
        if not line or line.startswith("-"):
            continue

        parts = line.split(",")
        if len(parts) < 11:
            continue

        # Extract and strip fields (JD has lots of trailing whitespace)
        timestamp_str = parts[0].strip()
        counterparty = parts[1].strip()
        description = parts[2].strip()
        amount_raw = parts[3].strip()
        payment_method = parts[4].strip()
        status = parts[5].strip()
        direction = parts[6].strip()
        platform_category = parts[7].strip()
        tx_id = parts[8].strip()
        merchant_order_id = parts[9].strip()
        note = parts[10].strip() if len(parts) > 10 else ""

        # Parse amount with inline refund detection
        amount, refund_amount, effective_amount = _parse_amount_field(amount_raw)

        # Determine if this is a refunded record
        is_refunded = refund_amount > 0

        # Parse timestamp
        try:
            timestamp = pd.to_datetime(timestamp_str)
        except Exception:
            continue

        # For standalone refund rows (退款成功), extract the refund description
        original_tx_id = ""
        is_refund_row = (status == "退款成功")

        records.append({
            "source_platform": "jd",
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
            "platform_tx_type": "",  # JD doesn't have this
            "original_tx_id": original_tx_id,
            "merchant_order_id": merchant_order_id,
            "note": note,
            # Defaults — will be refined by downstream modules
            "track": "",
            "is_refunded": is_refunded,
            "refund_amount": refund_amount,
            "effective_amount": effective_amount,
            "is_ignored": is_refund_row,  # Standalone refund rows are ignored
            "global_category_l1": "",
            "global_category_l2": "",
        })

    if not records:
        return create_empty_uul()

    df = pd.DataFrame(records, columns=UUL_COLUMNS)
    return df
