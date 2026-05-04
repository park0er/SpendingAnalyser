"""
LLM Tagger Runner — Provider-agnostic batch tagging

Reads batch prompts from `OUTPUT_DIR/tagging_batches/*.txt` and calls an
LLM API (Anthropic SDK format) to get JSON classification results.
Supports any provider with Anthropic-compatible endpoint (MiMo, MiniMax, etc.)

Configuration is read from `CONFIG_PATH` or `config.env` in the project root:
  LLM_API_KEY=your_key
  LLM_BASE_URL=https://api.xiaomimimo.com/anthropic
  LLM_MODEL=mimo-v2.5-pro

Usage:
  python3 src/classifiers/llm_tagger_runner.py
"""

import os
import sys
import json
import glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Load config from config.env ──────────────────────────────
def load_config():
    """Load LLM configuration from config.env file."""
    config = {}
    if os.environ.get("CONFIG_PATH"):
        config_path = Path(os.environ["CONFIG_PATH"]).expanduser()
    else:
        config_path = Path(__file__).resolve().parent.parent.parent / "config.env"

    if not config_path.exists():
        # Try current working directory
        config_path = Path("config.env")

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()

    # Environment variables override config file
    config["LLM_API_KEY"] = os.environ.get("LLM_API_KEY", config.get("LLM_API_KEY", ""))
    config["LLM_BASE_URL"] = os.environ.get("LLM_BASE_URL", config.get("LLM_BASE_URL", ""))
    config["LLM_MODEL"] = os.environ.get("LLM_MODEL", config.get("LLM_MODEL", ""))

    return config

config = load_config()

if not config["LLM_API_KEY"]:
    print("❌ 错误: 未找到 LLM API Key。")
    print("   请在 config.env 中设置 LLM_API_KEY，或通过环境变量 export LLM_API_KEY='...'")
    sys.exit(1)

if not config["LLM_BASE_URL"]:
    print("❌ 错误: 未找到 LLM Base URL。")
    print("   请在 config.env 中设置 LLM_BASE_URL")
    sys.exit(1)

if not config["LLM_MODEL"]:
    print("❌ 错误: 未找到 LLM Model 名称。")
    print("   请在 config.env 中设置 LLM_MODEL")
    sys.exit(1)

# ── Setup dependencies ───────────────────────────────────────
try:
    from anthropic import Anthropic
    import tqdm
except ImportError:
    print("📦 正在安装依赖 (anthropic, tqdm)...")
    os.system(f"{sys.executable} -m pip install anthropic tqdm")
    from anthropic import Anthropic
    import tqdm

# ── Setup client ─────────────────────────────────────────────
print(f"🔗 模型: {config['LLM_MODEL']}")
print(f"🌐 接口: {config['LLM_BASE_URL']}")

client = Anthropic(
    api_key=config["LLM_API_KEY"],
    base_url=config["LLM_BASE_URL"]
)

SYSTEM_PROMPT = "你是严格遵循格式的财务分类专家。请只输出合法的 JSON 数组，不要夹杂任何 Markdown 标记、思考过程或其他废话。返回的必须是可直接解析的 JSON 字符串。"


def process_batch(txt_file: str) -> None:
    """Processes a single batch file using the configured LLM."""
    result_file = txt_file.replace(".txt", "_result.json")

    # Skip if already processed
    if os.path.exists(result_file):
        return

    with open(txt_file, "r", encoding="utf-8") as f:
        prompt = f.read()

    try:
        response = client.messages.create(
            model=config["LLM_MODEL"],
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract text content (ignoring any 'thinking' block)
        output_text = ""
        for block in response.content:
            if block.type == "text":
                output_text += block.text

        # Clean up Markdown JSON blocks if any
        output_text = output_text.strip()
        if output_text.startswith("```json"):
            output_text = output_text[7:]
        if output_text.startswith("```"):
            output_text = output_text[3:]
        if output_text.endswith("```"):
            output_text = output_text[:-3]
        output_text = output_text.strip()

        # Verify it's valid JSON
        result_json = json.loads(output_text)

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result_json, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"\n❌ Error processing {os.path.basename(txt_file)}: {e}")


def main():
    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    batch_dir = output_dir / "tagging_batches"
    batch_files = sorted(glob.glob(str(batch_dir / "batch_*.txt")))
    if not batch_files:
        print(f"❌ 未找到 batch 文件 ({batch_dir}/)")
        return

    # Count how many need processing
    pending = [f for f in batch_files if not os.path.exists(f.replace(".txt", "_result.json"))]
    print(f"🚀 共 {len(batch_files)} 个 batch，其中 {len(pending)} 个待处理（{len(batch_files) - len(pending)} 个已跳过）")

    if not pending:
        print("✅ 所有 batch 已有结果，无需重新打标。")
        print("   如需重新打标，请删除对应的 _result.json 文件后重试。")
    else:
        # Concurrently process files (5 workers is safe for most rate limits)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(process_batch, f): f for f in batch_files}

            for _ in tqdm.tqdm(as_completed(futures), total=len(batch_files), desc="打标中"):
                pass

    print("\n✅ 打标完成！正在更新 CSV...")

    # Apply results to processed_data.csv
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    from src.classifiers.llm_tagger import apply_tagging_results
    import pandas as pd

    df_path = output_dir / "processed_data.csv"
    if os.path.exists(df_path):
        df = pd.read_csv(df_path)
        df = apply_tagging_results(df, str(batch_dir))
        df.to_csv(df_path, index=False, encoding="utf-8-sig")
        print("\n🎉 CSV 已更新！重启 Flask 后端即可看到变化。")
    else:
        print("\n❌ 找不到 processed_data.csv")


if __name__ == "__main__":
    main()
