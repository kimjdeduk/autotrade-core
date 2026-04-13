import os
import requests
import json
from dotenv import load_dotenv

class KISClient:
    def __init__(self):
        load_dotenv(dotenv_path='config/.env')
        self.app_key = os.getenv('KIS_APP_KEY')
        self.app_secret = os.getenv('KIS_APP_SECRET')
        self.account_no = os.getenv('KIS_ACCOUNT_NO')
        # 실제 KIS API URL (모의투자도 동일 URL 사용)
        self.base_url = "https://openapi.koreainvestment.com:9443"
        self.access_token = None

    def get_access_token(self):
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body), timeout=10)
            if res.status_code == 200:
                data = res.json()
                self.access_token = data.get("access_token")
                return True
            else:
                print(f"Token request failed: {res.status_code}")
                return False
        except Exception as e:
            print(f"Token error: {e}")
            return False