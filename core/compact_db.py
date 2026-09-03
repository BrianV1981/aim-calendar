import lancedb
from datetime import timedelta
db = lancedb.connect("./talker_cartridge.lance")
tbl = db.open_table("fragments")
print("Forcing cleanup of all old versions...")
tbl.optimize(cleanup_older_than=timedelta(seconds=0))
print("Done.")
