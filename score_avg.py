import json
import numpy as np
from collections import defaultdict
from pathlib import Path


def calculate_daily_average_sentiment(input_file_path, output_file_path, threshold=5):
    """
    讀取原始新聞情緒 JSONL 檔案，按每日計算：
      1. confidence 加權後的情感度平均值（含 outlier 過濾）
      2. confidence 加權後的 embedding 平均向量（逐維度加權平均，並重新正規化為單位向量）

    threshold: 與平均差距超過此值的資料會被剔除（outlier 過濾用 raw score）
    """
    # 每個日期存一個 list，裡面是 (score, confidence, embedding) 的 tuple
    aggregated_data = defaultdict(list)

    input_path = Path(input_file_path)
    if not input_path.exists():
        print(f"❌ 找不到輸入檔案：{input_file_path}")
        return

    print(f"🔍 開始讀取並解析檔案: {input_file_path}")

    # 1. 讀取資料（date, sentiment_score, confidence, embedding）
    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                date = data.get('date')
                output_obj = data.get('output')

                if date and isinstance(output_obj, dict):
                    score = output_obj.get('sentiment_score')
                    conf  = output_obj.get('confidence')
                    emb   = output_obj.get('embedding')  # 可能是 None（尚未跑embedding模型）

                    if score is not None:
                        # confidence 若缺失，預設為 1.0（等同不加權）
                        conf_val = float(conf) if conf is not None else 1.0
                        emb_arr  = np.array(emb, dtype=float) if emb is not None else None
                        aggregated_data[date].append((float(score), conf_val, emb_arr))
            except json.JSONDecodeError as e:
                print(f"⚠️ 第 {line_num} 行 JSON 解析失敗，已跳過。錯誤原因: {e}")
                continue

    print(f"📈 正在計算每日加權平均值（含 outlier 過濾）並寫入新檔案: {output_file_path}")

    count = 0
    with open(output_file_path, 'w', encoding='utf-8') as f_out:
        for date in sorted(aggregated_data.keys()):
            records = aggregated_data[date]
            if not records:
                continue

            scores = [r[0] for r in records]

            # 先算初始「未加權」平均，用來判斷 outlier（維持跟原邏輯一致）
            initial_avg = sum(scores) / len(scores)

            # 過濾 outliers：與 initial_avg 差距超過 threshold 的整筆(含embedding)剔除
            filtered = [
                r for r in records if abs(r[0] - initial_avg) <= threshold
            ]

            # 若全部被濾掉（極端情況），就用原始資料
            if not filtered:
                filtered = records

            filtered_scores = np.array([r[0] for r in filtered])
            filtered_confs  = np.array([r[1] for r in filtered])

            # ── confidence 加權平均分數 ──
            # 加權平均 = Σ(score_i * conf_i) / Σ(conf_i)
            weight_sum = filtered_confs.sum()
            if weight_sum > 0:
                final_avg = float(np.sum(filtered_scores * filtered_confs) / weight_sum)
            else:
                # 極端情況：所有信心度都是0，退回簡單平均
                final_avg = float(filtered_scores.mean())
            final_avg = round(final_avg, 2)

            # 順便輸出當日平均信心度，讓你知道這個分數的「可靠程度」
            avg_confidence = round(float(filtered_confs.mean()), 2)

            output_item = {
                "date": date,
                "score": final_avg,
                "confidence": avg_confidence,
                "news_count": len(filtered),
            }

            # ── embedding 加權平均（逐維度）──
            emb_records = [r for r in filtered if r[2] is not None]

            if emb_records:
                # 確保維度一致（避免不同批次用了不同截斷維度混在一起）
                first_dim = len(emb_records[0][2])
                emb_records = [
                    r for r in emb_records if len(r[2]) == first_dim
                ]

                if emb_records:
                    emb_stack = np.stack([r[2] for r in emb_records])
                    emb_confs = np.array([r[1] for r in emb_records])

                    emb_weight_sum = emb_confs.sum()

                    if emb_weight_sum > 0:
                        weighted_emb = np.average(
                            emb_stack,
                            axis=0,
                            weights=emb_confs
                        )
                    else:
                        weighted_emb = emb_stack.mean(axis=0)

                    # 加權平均後重新正規化為單位向量
                    norm = np.linalg.norm(weighted_emb)
                    if norm > 0:
                        weighted_emb_normalized = weighted_emb / norm
                    else:
                        weighted_emb_normalized = weighted_emb
                    
                    weighted_emb_normalized = np.round(weighted_emb_normalized, 6)
                    output_item["embedding"] = weighted_emb_normalized.tolist()

                    # embedding_coherence：正規化前的向量長度，代表當天新聞語意的一致程度
                    output_item["embedding_coherence"] = round(float(norm), 3)

            f_out.write(json.dumps(output_item, ensure_ascii=False) + '\n')
            count += 1

    print(f"✅ 處理完成！共生成 {count} 筆每日平均數據。")


# ────── 執行 ──────
if __name__ == "__main__":
    stockList = [2303, 2308, 2408, 2454, 2330, 2317, 2327, 3481, 3711, 6182]
    for stock in stockList:
        INPUT_FILE = f'data/jsonl/finish_labeled_embedding_temp/qwen_predictions_{stock}_with_embedding.jsonl'
        OUTPUT_FILE = f'data/jsonl/score_temp/{stock}.jsonl'

        calculate_daily_average_sentiment(INPUT_FILE, OUTPUT_FILE, threshold=5)