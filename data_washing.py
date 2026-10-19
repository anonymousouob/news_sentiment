import json
from difflib import SequenceMatcher
from datetime import datetime, timedelta

def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def remove_duplicates(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    data = []
    for line in lines:
        try:
            data.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"跳過無效行: {e}")

    print(f"原始資料筆數: {len(data)}")

    before = len(data)
    data = [
        d for d in data
        if len(d.get('input', '')) > 70 and not is_junk_content(d.get('input', ''))
    ]
    print(f"過短或內容截斷資料刪除筆數: {before - len(data)}，剩餘: {len(data)}")

    i = 0
    while i < len(data):
        prefix_i = data[i].get('input', '')[:30]
        date_i = datetime.strptime(data[i].get('date', ''), '%Y-%m-%d')
        
        j = i + 1
        while j < len(data):
            date_j = datetime.strptime(data[j].get('date', ''), '%Y-%m-%d')
            
            if abs((date_i - date_j).days) <= 30:
                prefix_j = data[j].get('input', '')[:30]
                ratio = similarity(prefix_i, prefix_j)
                if ratio >= 0.7:
                    print(f"發現與第{i}筆重複（相似度 {ratio:.0%}）→ 刪除第 {j} 筆: {data[j].get('input', '')[:30]}...")
                    data.pop(j)
                else:
                    j += 1
            else:
                j+=1
        
        i += 1

    print(f"去重後資料筆數: {len(data)}")

    with open(output_file, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"結果已寫入: {output_file}")

def is_junk_content(text: str) -> bool:
    prefix = text[:200]
    return '...' in prefix

if __name__ == '__main__':
    stockList = [2317, 2327, 3481, 3711, 6182] #[2303, 2308, 2330, 2408, 2454]

    for stock in stockList:
        input_file = f'data/jsonl/{stock}_transfer.jsonl'
        output_file = f'data/jsonl/{stock}_washing.jsonl'
        remove_duplicates(input_file, output_file)