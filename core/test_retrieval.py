import sys
import os
import lancedb
import json
aim_memory_path = os.environ.get("AIM_MEMORY_PATH", "../aim-memory")
sys.path.append(os.path.abspath(aim_memory_path))
from aim_memory.embeddings import get_embedding

db = lancedb.connect("./talker_cartridge.lance")
tbl = db.open_table("fragments")

vec = get_embedding("Ariana", task_type="RETRIEVAL_QUERY")
df = tbl.search(vec).limit(10).to_pandas()
print("SEMANIC SEARCH FOR 'Ariana'")
for _, row in df.iterrows():
    meta = json.loads(row['metadata'])
    print(f"DATE: {meta.get('date')} | CONTACT: {meta.get('contact')} | SCORE: {row.get('_distance')}")
    print(row['content'])
    print("---")
