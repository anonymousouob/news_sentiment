import csv
import time
import os
import json
import requests
import base64
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By  # 🌟 用來找網頁上的超連結元素

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

CHECKPOINT_FILE = "data/csv/checkpoint.json"


class Checkpoint:
    """
    負責記錄「現在跑到哪個股票、哪個年度、哪一列(日期)」，
    程式中斷後重跑時可以直接接續，不用從頭開始。

    儲存格式:
    {
        "completed_files": [
            "2317_2024"
        ],
        "current": {
            "stock": 2317,
            "year": 2025,
            "rows_done": 2216,
            "last_date": "2025-05-12 06:31:09"
        }
    }
    """

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
 
        # 原子寫入，避免寫到一半又斷電/中斷造成檔案壞掉。
        # Windows 上常因為檔案被其他程式(編輯器/防毒/OneDrive)鎖住而 PermissionError，
        # 這裡重試幾次，還是不行就直接降級覆寫，避免整支程式因此崩潰。
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


class URLResolver:
    """智慧型網址解析工具 (支援 Base64 解碼、動態跳轉、破解重新導向通知、斷點續跑)"""

    def __init__(self):
        self.driver = None
        self._init_selenium()
        self.checkpoint = Checkpoint()

    def _init_selenium(self):
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument(f'user-agent={HEADERS["User-Agent"]}')

        self.driver = webdriver.Chrome(options=chrome_options)
        print("✅ Selenium WebDriver 初始化成功\n")

    def _decode_base64_url(self, url):
        """嘗試從 Google News URL 中暴力解碼出真實網址"""
        try:
            match = re.search(r'articles/([^?]+)', url)
            if not match:
                return None
            encoded_str = match.group(1)
            padding = 4 - (len(encoded_str) % 4)
            if padding != 4:
                encoded_str += "=" * padding
            decoded_bytes = base64.urlsafe_b64decode(encoded_str)
            url_match = re.search(b'(https?://[a-zA-Z0-9./\-_%?=&+]+)', decoded_bytes)
            if url_match:
                return url_match.group(1).decode('utf-8')
        except Exception:
            pass
        return None

    def get_actual_url(self, url):
        """取得重定向後的真實網址"""
        if not url.startswith('http') or url.endswith('.pdf'):
            return url

        # 只要是 Google 相關網址，就啟動三段式破解
        if 'news.google.com' in url or 'google.com/url?' in url:

            # ⚡ 策略一：Base64 暴力解碼
            decoded_url = self._decode_base64_url(url)
            if decoded_url:
                print(f"        ⚡ Base64 暴力解碼成功!")
                return decoded_url

            # 🌐 策略二：Requests 處理
            try:
                print(f"        → 嘗試 Requests 追蹤跳轉...")
                response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)

                # 1. 正常跳轉成功 (網址已不在 google 網域)
                if 'google.com' not in response.url:
                    return response.url

                # 2. 遇到「重新導向通知」的卡關頁面
                if "重新導向通知" in response.text or "Redirect Notice" in response.text:
                    print(f"        🔍 遇到「重新導向通知」，嘗試從畫面提取連結...")
                    match = re.search(r'<a[^>]+href=["\'](https?://[^"\']+)["\']', response.text)
                    if match:
                        extracted_url = match.group(1).replace('&amp;', '&')
                        if 'google.com' not in extracted_url:
                            return extracted_url
            except Exception:
                pass

            # 🤖 策略三：Selenium 處理 (最後防線)
            try:
                print(f"        → 嘗試 Selenium 渲染跳轉...")
                self.driver.get(url)
                time.sleep(3)

                if "重新導向通知" in self.driver.page_source or "Redirect Notice" in self.driver.page_source:
                    print(f"        🔍 Selenium 遇到「重新導向通知」，提取連結...")
                    try:
                        links = self.driver.find_elements(By.TAG_NAME, 'a')
                        for link in links:
                            href = link.get_attribute('href')
                            if href and 'http' in href and 'google.com' not in href:
                                return href
                    except Exception:
                        pass

                return self.driver.current_url
            except Exception as e:
                print(f"        ⚠️ 所有解析方法皆失敗: {e}")
                return url
        else:
            # 非 Google 網址，一般跳轉
            try:
                response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
                return response.url
            except Exception:
                return url

    def process_and_save_csv(self, input_path, output_path, stock, year):
        print("=" * 70)
        print(f"📂 讀取檔案: {input_path}")
        print("=" * 70)

        if not os.path.exists(input_path):
            print(f"❌ 找不到檔案: {input_path}")
            return

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(input_path, 'r', encoding='utf-8-sig') as infile:
            reader = csv.reader(infile)
            rows = list(reader)

        if rows and ('日期' in rows[0][0] or 'Date' in rows[0][0]):
            rows = rows[1:]

        # 這個檔案上次跑到第幾列了 (0-based)，沒有紀錄就是 0
        start_row = self.checkpoint.get_resume_row(stock, year)
        if start_row > 0:
            print(f"⏩ 偵測到上次中斷紀錄，從第 {start_row + 1} 列開始接續...")

        # 有接續進度 -> 用 append 模式，不要重寫表頭
        # 從頭開始 -> 用 write 模式，寫入表頭
        file_mode = 'a' if start_row > 0 and os.path.exists(output_path) else 'w'
        write_header = not (file_mode == 'a')

        with open(output_path, file_mode, encoding='utf-8-sig', newline='') as outfile:
            writer = csv.writer(outfile)
            if write_header:
                writer.writerow(['日期', '股票代碼', '連結'])

            total = len(rows)
            print(f"🔄 開始處理 {total} 筆資料 (已完成 {start_row} 筆)...\n")

            for i in range(start_row, total):
                row = rows[i]
                if len(row) < 3:
                    continue

                date = row[0]
                stock_id = row[1]
                original_url = row[2]

                print(f"   [{i + 1}/{total}] 股票: {stock_id} | 日期: {date}")

                try:
                    actual_url = self.get_actual_url(original_url)
                except Exception as e:
                    print(f"        ⚠️ 發生未預期錯誤，保留原網址: {e}")
                    actual_url = original_url

                if actual_url != original_url:
                    print(f"✓ 最終網址: {actual_url[:80]}...")
                else:
                    print(f"❌ 無法解開，保留原網址")

                writer.writerow([date, stock_id, actual_url])
                outfile.flush()
                os.fsync(outfile.fileno())  # 立刻落地，避免中斷時資料還停留在緩衝區沒寫入

                # 每處理完一列就更新斷點紀錄
                self.checkpoint.update_progress(stock, year, rows_done=i + 1, last_date=date)

        # 整個檔案跑完，標記為已完成
        self.checkpoint.mark_file_completed(stock, year)
        print(f"\n✅ 處理完成，已儲存至: {output_path}")

    def __del__(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    stockList = [2317, 2327, 3481, 3711, 6182]  # [2303, 2308, 2330, 2408, 2454]

    resolver = URLResolver()

    yearList = [2024, 2025, 2026]

    for stock in stockList:
        for year in yearList:
            if resolver.checkpoint.is_file_completed(stock, year):
                print(f"⏭️  {stock}_{year} 先前已完成，跳過")
                continue

            input_csv = f"data/csv/{stock}_news_{year}.csv"
            output_csv = f"data/csv/{stock}_news_{year}_resolved.csv"

            resolver.process_and_save_csv(input_csv, output_csv, stock, year)

    print("\n🎉 全部股票、全部年度都已處理完畢！")