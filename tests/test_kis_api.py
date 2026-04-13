import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.kis_client import KISClient
from src.utils.notifier import TelegramNotifier

def run_test():
    print("Testing KIS API Client...")
    notifier = TelegramNotifier()
    client = KISClient()
    success = client.get_access_token()
    if success:
        notifier.notify_success("KIS API 연동 테스트", "토큰 발급 성공")
    else:
        notifier.notify_error("KIS API 연동 테스트", "토큰 발급 실패 (키 설정 필요)")

if __name__ == "__main__":
    run_test()