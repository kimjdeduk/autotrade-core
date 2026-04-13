import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# dotenv 로드 방식 테스트
from dotenv import load_dotenv

def test_env_loading():
    print("Testing environment variable loading...")
    
    # config/.env 파일 로드
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', '.env')
    load_dotenv(dotenv_path=env_path)
    
    # 환경변수 존재 여부 확인
    keys_to_check = ['KIS_APP_KEY', 'KIS_APP_SECRET', 'KIS_ACCOUNT_NO']
    
    for key in keys_to_check:
        value = os.getenv(key)
        if value and not value.startswith('your_'):
            print(f"{key}: 설정됨 (길이: {len(value)}자)")
        else:
            print(f"{key}: 없음")

if __name__ == "__main__":
    test_env_loading()