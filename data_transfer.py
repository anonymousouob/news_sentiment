import csv
import json
import time
import requests
from bs4 import BeautifulSoup
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

CHECKPOINT_FILE = "data/jsonl/checkpoint_transfer.json"  # 跟第一階段(解網址)的 checkpoint 分開存放，避免互相覆蓋


class Checkpoint:

    def __init__(self, path=CHECKPOINT_FILE):
        self.path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                print("⚠️ checkpoint 檔案損毀，將視為全新開始")
        return {"completed_files": [], "current": None}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp_path = self.path + f".tmp_{os.getpid()}"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        last_err = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, self.path)
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.5)

        print(f"⚠️ checkpoint 暫存檔重新命名失敗 ({last_err})，改用直接覆寫")
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e2:
            print(f"⚠️ checkpoint 仍然無法儲存，本次進度可能遺失: {e2}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def is_file_completed(self, stock, year):
        return f"{stock}_{year}" in self.data["completed_files"]

    def get_resume_row(self, stock, year):
        """如果現在這個 stock/year 正是上次中斷的那一個，回傳應該從第幾列(0-based)繼續"""
        cur = self.data.get("current")
        if cur and cur.get("stock") == stock and cur.get("year") == year:
            return cur.get("rows_done", 0)
        return 0

    def update_progress(self, stock, year, rows_done, last_date):
        self.data["current"] = {
            "stock": stock,
            "year": year,
            "rows_done": rows_done,
            "last_date": last_date,
        }
        self._save()

    def mark_file_completed(self, stock, year):
        key = f"{stock}_{year}"
        if key not in self.data["completed_files"]:
            self.data["completed_files"].append(key)
        self.data["current"] = None
        self._save()


class CSVNewsCollector:
    """CSV 新聞讀取與爬蟲器"""

    def __init__(self, csv_path, stock=None, year=None):
        self.csv_path = csv_path
        self.stock = stock
        self.year = year
        self.news_data = []

    def fetch_content_from_url(self, url):
        """從網址爬取標題 + 內文"""
        try:
            if not url.startswith('http') or url.endswith('.pdf'):
                return None, None
                
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.encoding = response.apparent_encoding  # 自動偵測編碼，解決亂碼
            
            if response.status_code != 200:
                return None, None

            soup = BeautifulSoup(response.text, 'html.parser')

            # ── 取得標題 ──────────────────────────────
            title = None
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"].strip()
            elif soup.title and soup.title.string:
                title = soup.title.string.strip()
            else:
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text().strip()

            # ── 取得內文 ──────────────────────────────
            # 移除雜訊標籤
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "form", "iframe", "noscript"]):
                tag.decompose()

            body_text = ""

            # 常見新聞內文容器（依優先順序嘗試）
            candidates = [
                soup.find("article"),
                soup.find(class_=lambda c: c and any(
                    k in c for k in ["article-content", "article-body", "news-content",
                                     "post-content", "entry-content", "story-body",
                                     "content-body", "articleBody"])),
                soup.find(id=lambda i: i and any(
                    k in i for k in ["article", "content", "main", "story"])),
                soup.find("main"),
            ]

            for candidate in candidates:
                if candidate:
                    paragraphs = candidate.find_all("p")
                    text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                    if len(text) > 100:   # 內容夠長才採用
                        body_text = text
                        break

            # fallback：抓全頁所有 <p>
            if not body_text:
                paragraphs = soup.find_all("p")
                body_text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            return title, body_text.strip() if body_text else None

        except Exception as e:
            print(f"⚠️ 爬取失敗 {url}: {e}")
            return None, None

    def process_csv(self, checkpoint):
        """讀取 CSV 並整理數據 (支援斷點續跑；每爬完一列就直接標籤化並 append 進最終 jsonl)"""
        print("="*60)
        print(f"📂 讀取檔案: {self.csv_path}")
        print("="*60)

        if not os.path.exists(self.csv_path):
            print(f"❌ 找不到檔案: {self.csv_path}")
            return []

        with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)

        if rows and ('日期' in rows[0][0] or 'Date' in rows[0][0]):
            rows = rows[1:]

        # 最終輸出檔：同一支股票跨年度共用同一個檔案，永遠用 append 模式，
        # 檔案不存在時 open(..., 'a') 會自動建立，不用另外判斷 'w'/'a'。
        output_file = f"data/jsonl/{self.stock}_transfer.jsonl"
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        labeler = SentimentLabeler()
        processed_list = []
        start_row = checkpoint.get_resume_row(self.stock, self.year)

        if start_row > 0:
            print(f"⏩ 偵測到上次中斷紀錄，從第 {start_row + 1} 列開始接續 (已爬取 {start_row} 筆)...")

        total = len(rows)
        print(f"🔄 開始處理 {total} 筆資料 (已完成 {start_row} 筆)...\n")

        with open(output_file, 'a', encoding='utf-8') as outfile:
            for i in range(start_row, total):
                row = rows[i]

                if len(row) < 3:
                    checkpoint.update_progress(self.stock, self.year, rows_done=i + 1, last_date="")
                    continue

                date     = row[0].split(' ')[0].split('T')[0]
                stock_id = row[1]
                url      = row[2]

                # CSV 第 4 欄若有標題可直接用（但內文仍需爬取）
                csv_title = ""
                if len(row) >= 4 and row[3].strip() and row[3] != "undefined":
                    csv_title = row[3].strip()

                print(f"   [{i + 1}/{total}] 正在爬取: {url[:60]}...")
                web_title, body = self.fetch_content_from_url(url)
                time.sleep(1)   # 禮貌性延遲

                # 標題優先用 CSV 欄位；沒有才用爬到的
                title = csv_title or web_title or ""

                if not title and not body:
                    print(f"⚠️ [{i + 1}] 無法取得內容，跳過。")
                else:
                    # 組合 input：「標題。內文」
                    content_parts = [p for p in [title, body] if p]
                    full_input = "。".join(content_parts)

                    news_item = {
                        'date'    : date,
                        'stock_id': stock_id,
                        'title'   : title,
                        'input'   : full_input,
                        'url'     : url,
                    }
                    processed_list.append(news_item)

                    # 沿用原本的標籤化邏輯，一次處理一筆，馬上寫進最終檔案
                    labeled_item = labeler.prepare_label([news_item])[0]
                    outfile.write(json.dumps({
                        "date"  : labeled_item['date'],
                        "stock" : labeled_item['stock'],
                        "input" : labeled_item['input'],
                        "output": labeled_item['output'],
                    }, ensure_ascii=False) + '\n')
                    outfile.flush()
                    os.fsync(outfile.fileno())  # 立刻落地，避免中斷時資料還停留在緩衝區沒寫入

                # 每處理完一列就更新斷點紀錄
                checkpoint.update_progress(self.stock, self.year, rows_done=i + 1, last_date=date)

                if (i + 1) % 10 == 0:
                    print(f"   ✅ 已處理 {i + 1} 筆...")

        self.news_data = processed_list
        print(f"\n✅ 成功取得 {len(processed_list)} 則有效新聞")
        return processed_list


class SentimentLabeler:
    """資料初始化器（將 output 結構化留空，不進行預標註，供後續大模型/人工標註）"""
    
    def prepare_label(self, news_list):
        print("\n" + "="*60)
        print("🏷️  整理資料（建構預標註 JSON 骨架）")
        print("="*60)
        
        labeled_data = []
        for news in news_list:
            # 安全轉換股票代碼為整數（例如 '2330' -> 2330）
            try:
                stock_val = int(news['stock_id'])
            except ValueError:
                stock_val = news['stock_id']

            labeled_data.append({
                'date'  : news['date'],
                'stock' : stock_val,
                'input' : news['input'],   # 標題 + 內文
                'output': {
                    "sentiment_score": None,
                    "confidence": None
                }
            })
            
        print(f"✅ 整理完成: {len(labeled_data)} 筆")
        return labeled_data


def save_to_jsonl(labeled_data, output_file):
    print("\n💾 儲存檔案中...")
    
    # 自動建立輸出目錄（避免資料夾不存在而報錯）
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
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


# ==========================================
# 主程式執行區
# ==========================================

if __name__ == "__main__":
    stockList = [2317, 2327, 3481, 3711, 6182] # [2303, 2308, 2330, 2408, 2454]
    yearList = [2024, 2025, 2026]

    checkpoint = Checkpoint()

    for stock in stockList:
        for year in yearList:
            if checkpoint.is_file_completed(stock, year):
                print(f"⏭️  {stock}_{year} 先前已完成，跳過")
                continue

            csv_filename = f"data/csv/{stock}_news_{year}.csv"

            collector = CSVNewsCollector(csv_filename, stock, year)
            collector.process_csv(checkpoint)

            checkpoint.mark_file_completed(stock, year)

    print("\n🎉 全部股票、全部年度都已處理完畢！")