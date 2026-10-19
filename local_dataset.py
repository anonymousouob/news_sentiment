from datasets import load_dataset
import pandas as pd
import os

# 1. 告訴程式你想下載的資料集名稱
dataset_name = "FinGPT/fingpt-sentiment-train"
print(f"🔄 正在從 Hugging Face 下載 {dataset_name} ...")

# 2. 載入資料集 (這會自動幫你把整個資料庫載下來，並暫存在電腦裡)
dataset = load_dataset(dataset_name)

# 3. 將 'train' 分割區的資料轉換成熟悉的 Pandas DataFrame
df = dataset['train'].to_pandas()

print(f"✅ 下載完成！總共有 {len(df)} 筆資料。")
print("資料預覽：")
print(df.head())

# 存成你剛剛很熟悉的 JSONL 格式 (如果後續要直接餵給模型訓練很常用)
jsonl_path = "data/fingpt_sentiment_train.jsonl"
df.to_json(jsonl_path, orient="records", lines=True, force_ascii=False)
print(f"💾 已儲存為 JSONL: {jsonl_path}")