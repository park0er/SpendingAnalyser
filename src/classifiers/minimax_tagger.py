"""
MiniMax M2.5 LLM Tagger

Reads batch prompts from `output/tagging_batches/*.txt` and calls the 
MiniMax API using the Anthropic SDK to get JSON classification results.

Usage:
  export MINIMAX_API_KEY="your_api_key_here"
  python3 minimax_tagger.py
"""

import os
import sys
import json
import glob
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from anthropic import Anthropic
    import tqdm
except ImportError:
    print("Missing dependencies. Installing...")
    os.system(f"{sys.executable} -m pip install anthropic tqdm")
    from anthropic import Anthropic
    import tqdm

# Setup client as per MiniMax documentation
API_KEY = os.environ.get("MINIMAX_API_KEY")
if not API_KEY:
    print("❌ Error: MINIMAX_API_KEY environment variable not set.")
    print("Please run: export MINIMAX_API_KEY='your_key' before running this script.")
    sys.exit(1)

client = Anthropic(
    api_key=API_KEY,
    base_url="https://api.minimaxi.com/anthropic"
)

def process_batch(txt_file: str) -> None:
    """Processes a single batch file using MiniMax-M2.5"""
    result_file = txt_file.replace(".txt", "_result.json")
    
    # Skip if already processed
    if os.path.exists(result_file):
        return
        
    with open(txt_file, "r", encoding="utf-8") as f:
        prompt = f.read()

    try:
        response = client.messages.create(
            model="MiniMax-M2.5",
            max_tokens=2000,
            system="你是严格遵循格式的财务分类专家。请只输出合法的 JSON 数组，不要夹杂任何 Markdown 标记、思考过程或其他废话。返回的必须是可直接解析的 JSON 字符串。",
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
    batch_files = sorted(glob.glob("output/tagging_batches/batch_*.txt"))
    if not batch_files:
        print("No batch files found in output/tagging_batches/")
        return
        
    print(f"🚀 Found {len(batch_files)} batches. Starting MiniMax tagging...")
    
    # Concurrently process files (5 workers is safe for most rate limits)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_batch, f): f for f in batch_files}
        
        for _ in tqdm.tqdm(as_completed(futures), total=len(batch_files), desc="Tagging"):
            pass
            
    print("\n✅ Tagging completed! Generating new CSV...")
    
    # Load into main
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    from src.classifiers.llm_tagger import apply_tagging_results
    import pandas as pd
    
    df_path = "output/processed_data.csv"
    if os.path.exists(df_path):
        df = pd.read_csv(df_path)
        df = apply_tagging_results(df, "output/tagging_batches")
        df.to_csv(df_path, index=False, encoding="utf-8-sig")
        print("\n🎉 CSV successfully updated! You can now restart your Flask backend to see the changes.")
    else:
        print("\n❌ Processed data CSV not found to update.")

if __name__ == "__main__":
    main()
