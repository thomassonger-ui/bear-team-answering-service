import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.environ.get('BASE_URL', 'https://bear-team-answering-service.onrender.com')
def ping():
    try:
        response = requests.get(BASE_URL + '/status', timeout=10)
        print(f"Pinged {BASE_URL} - Status: {response.status_code}")
    except Exception as e:
        print(f"Ping failed: {e}")

if __name__ == "__main__":
    print(f"Keeping {BASE_URL} awake - pinging every 10 minutes...")
    while True:
        ping()
        time.sleep(600)  # 10 minutes
