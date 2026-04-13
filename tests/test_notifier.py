import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.notifier import TelegramNotifier

def run_test():
    print("Testing Telegram Notifier...")
    notifier = TelegramNotifier()
    success = notifier.notify_success(task_name="Alarmbot 연동 테스트", details="자동 알림 시스템이 정상 구축되었습니다.")
    if success:
        print("Test message sent successfully!")
    else:
        print("Failed. Check .env configuration.")

if __name__ == "__main__":
 run_test()
