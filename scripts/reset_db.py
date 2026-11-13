"""Delete the database and rebuild it with fresh seed data.  Run:  python -m scripts.reset_db"""
import os

from backend.app import config, db
from backend.app.seed import seed_if_empty

if __name__ == "__main__":
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    conn = db.connect()
    db.init_db(conn)
    seed_if_empty(conn)
    print("Fresh database created at", config.DB_PATH)
