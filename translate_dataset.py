import json
import time
from deep_translator import GoogleTranslator
import os

# 檔案路徑設定
input_file = "data/fingpt_sentiment_train.jsonl"
output_file = "data/fingpt_sentiment_train_v2.jsonl"

# 初始化 Google 翻譯器 (自動偵測語言 -> 繁體中文)
translator = GoogleTranslator(source='auto', target='zh-TW')

if not os.path.exists(input_file):
    print(f"❌ 找不到檔案: {input_file}")
else:
    print(f"📂 開始讀取並翻譯 {input_file} ...")
    
    with open(input_file, 'r', encoding='utf-8') as infile, \
         open(output_file, 'w', encoding='utf-8') as outfile:
         
        for i, line in enumerate(infile, 1):
            if not line.strip():
                continue
                
            data = json.loads(line)
            
            # 取得需要翻譯的英文內文和要保留的 output
            english_text = data.get("input", "")
            sentiment_output = data.get("output", "")
            
            try:
                # 進行翻譯
                translated_text = translator.translate(english_text)
                
                # 重新組合成只有 input 和 output 的格式 (捨棄 instruction)
                new_data = {
                    "input": translated_text,
                    "output": sentiment_output
                }
                
                # 寫入新檔案 (ensure_ascii=False 確保中文不會變成亂碼)
                outfile.write(json.dumps(new_data, ensure_ascii=False) + '\n')
                
                print(f"✅ 完成第 {i} 筆翻譯")
                
                # 禮貌性延遲，避免短時間發送過多請求被 Google 暫時封鎖 API
                time.sleep(0.5) 
                
            except Exception as e:
                print(f"⚠️ 第 {i} 筆翻譯失敗: {e}")
                # 如果翻譯失敗，可以選擇保留原文，以免資料遺失
                new_data = {"input": english_text, "output": sentiment_output}
                outfile.write(json.dumps(new_data, ensure_ascii=False) + '\n')

    print("=" * 40)
    print(f"🎉 翻譯與清洗完成！新檔案已儲存為: {output_file}")