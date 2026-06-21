import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 1800))
DB_NAME = os.getenv("DB_NAME", "data/database.db")