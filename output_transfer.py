import json
import os

# 1. 核心轉換邏輯：轉型 stock、清空 output
def transform_item(item):
    return {
        "date": item.get("date"),
        "stock": int(item.get("stock", 0)),  # 確保將字串轉換為整數
        "input": item.get("input"),
        "output": {
            "sentiment_score": None,         # 清空並替換格式
            "confidence": None
        }
    }

# 2. 讀取 JSONL 檔案
def load_from_jsonl(input_file):
    data = []
    # 檢查檔案是否存在，避免程式報錯中斷
    if not os.path.exists(input_file):
        print(f"⚠️ 找不到檔案: {input_file}，已跳過。")
        return data
        
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip(): # 確保不處理空行
                data.append(json.loads(line))
    return data

# 3. 儲存為 JSONL (使用你提供的邏輯)
def save_to_jsonl(labeled_data, output_file):
    print("💾 儲存檔案中...")
    
    # 確保輸出的資料夾存在，避免路徑錯誤
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for item in labeled_data:
            json_line = json.dumps({
                "date"  : item['date'],
                "stock" : item['stock'],
                "input" : item['input'],
                "output": item['output']
            }, ensure_ascii=False)
            f.write(json_line + '\n')
    print(f"🎉 檔案已儲存至: {output_file}")


if __name__ == "__main__":
    stockList = [2303, 2308, 2330, 2408, 2454]
    
    for stock in stockList:
        input_file = f'data/jsonl/{stock}_output.jsonl'
        output_file = f"data/jsonl/{stock}_output_fixed.jsonl"
        
        print(f"\n⏳ 開始處理股票代碼: {stock}")
        
        original_data = load_from_jsonl(input_file)
        
        if not original_data:
            continue
        final_data = [transform_item(item) for item in original_data]
        save_to_jsonl(final_data, output_file)