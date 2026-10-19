import json

stockList = [2303, 2308, 2330, 2408, 2454]

for stock in stockList:

    # 初始化計數器字典
    counts = {
        "positive": 0,
        "neutral": 0,
        "negative": 0
    }

    # 讀取 JSON 檔案 (請確認檔案名稱與路徑是否正確)
    file_path = f'data/jsonl/taiwan_news/taiwan_news_{stock}.jsonl'

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            # 逐行讀取
            for line in file:
                line = line.strip()
                if not line:
                    continue
                
                # 將字串解析為 JSON 物件
                data = json.loads(line)
                
                # 取得 output 欄位的值
                output_value = data.get("output")
                
                # 若該值在我們的計數器中，則將數量 +1
                if output_value in counts:
                    counts[output_value] += 1

        # 依照您要求的格式印出結果
        print(f"{stock}-> 正面: {counts['positive']} | 中性: {counts['neutral']} | 負面: {counts['negative']}")

    except FileNotFoundError:
        print(f"找不到檔案: {file_path}")
    except json.JSONDecodeError:
        print("JSON 格式解析錯誤，請確認檔案內容格式。")