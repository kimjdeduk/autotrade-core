import os
import requests
from dotenv import load_dotenv

class TelegramNotifier:
    def __init__(self):
        load_dotenv(dotenv_path='config/.env')
        self.bot_token = os.getenv('TELEGRAM_ALARM_BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, message, parse_mode="Markdown"):
        if not self.bot_token or not self.chat_id:
            print("Telegram credentials not configured.")
            return False
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": parse_mode}
        try:
            response = requests.post(url, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send telegram message: {e}")
            return False

    def notify_success(self, task_name, details=""):
        msg = f"작업 완료 알림\n\n작업명: {task_name}\n상태: 성공\n\n{details}"
        return self.send_message(msg)

    def notify_error(self, task_name, error_msg):
        msg = f"에러 발생 알림\n\n작업명: {task_name}\n상태: 실패\n에러 내용:\n{error_msg}"
        return self.send_message(msg)