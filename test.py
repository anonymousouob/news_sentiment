import json

with open('data/jsonl/score/2303_embedding.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if 'embedding' in data:
            print(f"維度：{len(data['embedding'])}")
        break