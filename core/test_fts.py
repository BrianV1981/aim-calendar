import lancedb
import json
db = lancedb.connect("./talker_cartridge.lance")
tbl = db.open_table("fragments")

print("FTS Search for Ariana...")
df = tbl.search("Ariana").limit(10).to_pandas()
for _, row in df.iterrows():
    meta = json.loads(row['metadata'])
    print(f"DATE: {meta.get('date')} | CONTACT: {meta.get('contact')}")
    print(row['content'])
    print("---")
