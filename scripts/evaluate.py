"""Offline evaluation. Run from the project root:  python -m scripts.evaluate"""
import json
import sys

from backend.app import db, services
from backend.app.seed import seed_if_empty

if __name__ == "__main__":
    conn = db.connect()
    db.init_db(conn)
    seed_if_empty(conn)
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(json.dumps(services.evaluation(conn, k=k), indent=2))
