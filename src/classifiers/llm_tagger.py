"""
LLM Tagger — Generates prompts for LLM-based L1+L2 classification.

This module does NOT call an LLM directly. Instead, it:
1. Prepares batch prompts with transaction data
2. Outputs them to a file for the Agent to process
3. Provides a function to parse LLM responses back into the DataFrame

The Agent (which IS a LLM) processes these prompts and writes results back.
"""

import json
import pandas as pd
from pathlib import Path
from .taxonomy import get_taxonomy_prompt_block, TAXONOMY, ALL_L1


BATCH_SIZE = 20

SYSTEM_PROMPT = """你是财务分类专家。请为以下支付交易打上 L1 一级分类和 L2 二级分类。
必须从以下固定清单中选择分类：

{taxonomy}

每条记录格式: [序号]. [交易对方] | [商品/服务描述] | [金额]

请返回一个 JSON 数组，格式:
[{{"index": 1, "l1": "餐饮美食", "l2": "外卖配送"}}, ...]

注意：
- 如果平台原始分类有误（例如停车费被标为"数码电器"），请根据商户名和描述纠正
- 对于模糊的记录，根据商户名推断最可能的分类
- L2 必须属于对应 L1 下的子分类"""


def generate_tagging_batches(df: pd.DataFrame, output_dir: str) -> list[dict]:
    """
    Generate batch prompt files for LLM tagging.

    Filters to consumption-track records missing L2 tags.

    Args:
        df: UUL DataFrame
        output_dir: Directory to write prompt files

    Returns:
        List of batch metadata dicts with 'file', 'indices', 'count'
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Select records needing tagging
    mask = (
        (df["track"] == "consumption")
        & (df["global_category_l2"].fillna("") == "")
        & (~df["is_ignored"])
    )
    records_to_tag = df[mask].copy()

    if records_to_tag.empty:
        return []

    taxonomy_block = get_taxonomy_prompt_block()
    batches = []

    for batch_num, start in enumerate(range(0, len(records_to_tag), BATCH_SIZE)):
        batch = records_to_tag.iloc[start : start + BATCH_SIZE]
        lines = []

        for i, (idx, row) in enumerate(batch.iterrows(), 1):
            counterparty = row["counterparty"] or "未知"
            desc = row["description"] or "无描述"
            amount = row["amount"]
            platform = row["source_platform"]
            hint = ""
            if row["platform_category"]:
                hint = f" (平台原标签: {row['platform_category']})"
            lines.append(
                f"{i}. [{platform}] {counterparty} | {desc} | ¥{amount:.2f}{hint}"
            )

        prompt = SYSTEM_PROMPT.format(taxonomy=taxonomy_block) + "\n\n" + "\n".join(lines)

        batch_file = output_path / f"batch_{batch_num:03d}.txt"
        batch_file.write_text(prompt, encoding="utf-8")

        batches.append({
            "file": str(batch_file),
            "indices": list(batch.index),
            "count": len(batch),
        })

    # Write batch manifest
    manifest = output_path / "manifest.json"
    manifest.write_text(json.dumps(batches, indent=2, ensure_ascii=False), encoding="utf-8")

    return batches


def apply_tagging_results(df: pd.DataFrame, results_dir: str) -> pd.DataFrame:
    """
    Read LLM tagging results and apply them to the DataFrame.

    Expects result files named batch_XXX_result.json containing:
    [{"index": 1, "l1": "...", "l2": "..."}, ...]

    Args:
        df: UUL DataFrame
        results_dir: Directory containing result JSON files

    Returns:
        Updated DataFrame with L1+L2 tags filled in
    """
    df = df.copy()
    results_path = Path(results_dir)

    # Load manifest
    manifest_file = results_path / "manifest.json"
    if not manifest_file.exists():
        return df

    with open(manifest_file, "r", encoding="utf-8") as f:
        batches = json.load(f)

    for batch in batches:
        result_file = results_path / Path(batch["file"]).stem.replace(
            "batch_", "batch_"
        )
        result_file = results_path / f"{Path(batch['file']).stem}_result.json"

        if not result_file.exists():
            continue

        with open(result_file, "r", encoding="utf-8") as f:
            results = json.load(f)

        indices = batch["indices"]
        for item in results:
            i = item.get("index", 0) - 1  # 1-indexed to 0-indexed
            if 0 <= i < len(indices):
                row_idx = indices[i]
                l1 = item.get("l1", "")
                l2 = item.get("l2", "")

                # Validate against taxonomy
                if l1 in TAXONOMY:
                    df.at[row_idx, "global_category_l1"] = l1
                    if l2 in TAXONOMY[l1]:
                        df.at[row_idx, "global_category_l2"] = l2
                    else:
                        df.at[row_idx, "global_category_l2"] = TAXONOMY[l1][0]

    return df
