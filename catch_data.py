import requests
import pandas as pd
import time
import json
import os
import sys
from datetime import datetime, timedelta

url = "https://api.finmindtrade.com/api/v4/data"
token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkYXRlIjoiMjAyNi0wMy0xMyAwMjoyMDo0NyIsInVzZXJfaWQiOiJ6enoiLCJlbWFpbCI6ImltYWdpbmUuemVyby4yMDIwQGdtYWlsLmNvbSIsImlwIjoiMzYuMjMwLjg3LjYyIn0.Ygnee5F24pATX8xVHui30afUEHyRK0RV9K_S3gPEYGs"
headers = {"Authorization": f"Bearer {token}"}

PROGRESS_FILE = "data/csv/fetch_progress.json"

# ────── 斷點續傳：讀取/更新進度 ──────
def load_progress():
    """讀取每支股票目前抓到哪一天了，格式：{"2327": "2025-03-15", ...}"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(progress):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ────── 判斷是否遇到 API 呼叫上限 ──────
def is_rate_limited(response, data: dict) -> bool:
    if response.status_code == 402:
        return True

    msg = str(data.get('msg', '')).lower()
    rate_limit_keywords = ['limit', '402', 'too many', 'quota', 'exceed']
    return any(kw in msg for kw in rate_limit_keywords)

# ────── 依年份取得對應的 CSV 路徑 ──────
def get_csv_path(stock, year):
    return f"data/csv/{stock}_news_{year}.csv"
 
 
# ────── 主流程 ──────
def fetch_stock_news(stock, start_date, end_date, progress):
    date_str_key = str(stock)
 
    # ── 依 start_date ~ end_date 算出橫跨哪些年份，先印出來讓你知道會產生哪些檔案 ──
    years = list(range(start_date.year, end_date.year + 1))
    print(f"📁 {stock} 的資料橫跨 {years[0]} ~ {years[-1]} 年，將產生以下檔案：")
    for y in years:
        print(f"   - {get_csv_path(stock, y)}")
 
    # ── 檢查進度，決定從哪一天開始 ──
    resume_date_str = progress.get(date_str_key)
    if resume_date_str:
        current_date = datetime.strptime(resume_date_str, "%Y-%m-%d") + timedelta(days=1)
        print(f"📌 偵測到 {stock} 上次抓到 {resume_date_str}，將從 {current_date.strftime('%Y-%m-%d')} 繼續")
    else:
        current_date = start_date
 
    if current_date > end_date:
        print(f"✅ {stock} 已經抓取完畢（{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}），跳過")
        return
 
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"正在抓取 {stock} {date_str} 的資料...")
 
        parameter = {
            "dataset": "TaiwanStockNews",
            "data_id": stock,
            "start_date": date_str,
            "end_date": date_str
        }
 
        try:
            response = requests.get(url, headers=headers, params=parameter)
            data = response.json()
 
            # ── 遇到 API 呼叫上限：存進度、直接終止整個程式 ──
            if is_rate_limited(response, data):
                print(f"\n🛑 偵測到 API 呼叫上限（status_code={response.status_code}, msg={data.get('msg')}）")
                print(f"📌 已儲存進度：{stock} 抓到 {current_date - timedelta(days=1)} 為止")
                print("程式即將終止，請稍後重新執行即可自動從中斷點繼續。")
                save_progress(progress)
                sys.exit(1)  # 直接終止整個程式
 
            if data.get('msg') == 'success' and len(data.get('data', [])) > 0:
                day_data = data['data']
                df_day = pd.DataFrame(day_data)[['date', 'stock_id', 'link']]
                df_day.columns = ['日期', '股票代碼', '連結']
 
                # ── 依「這一天所屬的年份」決定要寫進哪個檔案 ──
                year = current_date.year
                csv_path = get_csv_path(stock, year)
                os.makedirs(os.path.dirname(csv_path), exist_ok=True)
 
                # 每次都即時檢查該年度檔案是否已存在，決定要不要寫表頭
                # （這樣即使是斷點續傳、跨次執行，也不會重複寫表頭或蓋掉舊資料）
                file_exists = os.path.exists(csv_path)
 
                # ── 每天抓完就立刻寫入 CSV（append），避免資料留在記憶體裡遺失 ──
                df_day.to_csv(
                    csv_path,
                    mode='a',
                    index=False,
                    encoding='utf-8-sig',
                    header=not file_exists,
                )
                print(f"  {date_str} 抓到 {len(df_day)} 筆，已寫入 {csv_path}")
            else:
                print(f"  {date_str} 沒有新聞資料或 API 回傳錯誤。")
 
        except SystemExit:
            raise  # 讓上面的 sys.exit 正常往外拋出，不要被下面的 except 攔截
        except Exception as e:
            print(f"  {date_str} 抓取發生錯誤: {e}")
 
        # ── 這一天處理完（不論成功或失敗），更新進度並存檔 ──
        progress[date_str_key] = date_str
        save_progress(progress)
 
        time.sleep(1.5)
        current_date += timedelta(days=1)
 
    print(f"\n✅ {stock} 全部抓取完畢，資料已依年份分別儲存於：")
    for y in years:
        path = get_csv_path(stock, y)
        if os.path.exists(path):
            print(f"   - {path}")

# ────── 執行 ──────
if __name__ == "__main__":
    start_date = datetime.strptime("2024-01-01", "%Y-%m-%d")
    end_date = datetime.strptime("2026-06-30", "%Y-%m-%d")

    progress = load_progress()

    stockList =  # [2303, 2308, 2317, 2327, 2330, 2408, 2454, 3481, 3711, 6182]

    for stock in stockList:
        fetch_stock_news(stock, start_date, end_date, progress)


    print("\n🎉 所有股票抓取完畢！")