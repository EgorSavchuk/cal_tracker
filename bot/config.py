import json
import os
import dotenv


dotenv.load_dotenv()

DEBUG = os.getenv("DEBUG").strip() == "True"
TOKEN_BOT = os.getenv("TOKEN_BOT")

ADMIN_IDS = json.loads(os.getenv("ADMIN_IDS"))

MONGO_URL = os.getenv("MONGO_URL")
REDIS_URL = os.getenv("REDIS_URL")

ANALYTICS_COLLECTION_NAME = os.getenv("ANALYTICS_COLLECTION_NAME")
