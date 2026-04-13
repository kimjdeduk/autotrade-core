#!/usr/bin/env python3
"""
auto_pull_watcher.py - GitHub 자동 pull & 지시문 실행 감시기

사자(Manus)가 instructions/ 폴더에 새 지시문을 push하면,
이 스크립트가 자동으로 감지하여 아사(OpenClaw)에게 알려줍니다.

작동 방식:
  1. 30초마다 git fetch 수행
  2. 원격 브랜치에 새 커밋이 있으면 git pull
  3. instructions/ 폴더에 새 파일이 있는지 확인
  4. 새 지시문 발견 시 알림봇으로 Commander에게 알림
  5. 처리된 지시문 목록을 로컬에 기록하여 중복 실행 방지

환경변수 (.env):
  TELEGRAM_ALARM_TOKEN  - 알림봇 토큰
  TELEGRAM_CHAT_ID      - Commander 채팅 ID
  REPO_PATH             - autotrade-core 저장소 경로
  POLL_INTERVAL         - 감시 주기 (초, 기본값 30)
"""

import os
import sys
import time
import json
import subprocess
import logging
import hashlib
from pathlib import Path
from datetime import datetime

# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
LOG_DIR = None  # setup()에서 설정
logger = logging.getLogger("auto_pull_watcher")


def setup_logging(log_dir: Path):
    """로그 디렉토리 생성 및 로거 설정"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "auto_pull_watcher.log"

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 파일 핸들러 (최대 5MB, 3개 백업)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# ──────────────────────────────────────────────
# 환경변수 로드
# ──────────────────────────────────────────────
def load_env(repo_path: Path) -> dict:
    """config/.env 파일에서 환경변수 로드"""
    env_file = repo_path / "config" / ".env"
    env_vars = {}

    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
        logger.info(f".env 로드 완료: {env_file}")
    else:
        logger.warning(f".env 파일 없음: {env_file}")

    return env_vars


# ──────────────────────────────────────────────
# 텔레그램 알림
# ──────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """알림봇으로 텔레그램 메시지 전송"""
    try:
        import urllib.request
        import urllib.parse

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode("utf-8")

        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                logger.info("텔레그램 알림 전송 성공")
                return True
            else:
                logger.error(f"텔레그램 API 오류: {result}")
                return False
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")
        return False


# ──────────────────────────────────────────────
# Git 작업
# ──────────────────────────────────────────────
def run_git(repo_path: Path, *args) -> tuple:
    """git 명령 실행, (returncode, stdout, stderr) 반환"""
    cmd = ["git", "-C", str(repo_path)] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"git 명령 타임아웃: {' '.join(cmd)}")
        return -1, "", "timeout"
    except Exception as e:
        logger.error(f"git 명령 실패: {e}")
        return -1, "", str(e)


def check_remote_changes(repo_path: Path) -> bool:
    """원격에 새 커밋이 있는지 확인"""
    # fetch
    rc, out, err = run_git(repo_path, "fetch", "origin", "main")
    if rc != 0:
        logger.warning(f"git fetch 실패: {err}")
        return False

    # 로컬 HEAD vs 원격 HEAD 비교
    rc, local_hash, _ = run_git(repo_path, "rev-parse", "HEAD")
    if rc != 0:
        return False

    rc, remote_hash, _ = run_git(repo_path, "rev-parse", "origin/main")
    if rc != 0:
        return False

    if local_hash != remote_hash:
        logger.info(f"새 커밋 감지: local={local_hash[:8]} → remote={remote_hash[:8]}")
        return True

    return False


def pull_changes(repo_path: Path) -> bool:
    """git pull 수행"""
    rc, out, err = run_git(repo_path, "pull", "origin", "main")
    if rc == 0:
        logger.info(f"git pull 성공: {out}")
        return True
    else:
        logger.error(f"git pull 실패: {err}")
        return False


# ──────────────────────────────────────────────
# 지시문 감시
# ──────────────────────────────────────────────
def get_instruction_files(repo_path: Path) -> list:
    """instructions/ 폴더의 .md 파일 목록 반환 (README.md 제외)"""
    inst_dir = repo_path / "instructions"
    if not inst_dir.exists():
        return []

    files = []
    for f in sorted(inst_dir.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        files.append(f)
    return files


def load_processed_list(state_file: Path) -> set:
    """처리 완료된 지시문 목록 로드"""
    if state_file.exists():
        with open(state_file, "r") as f:
            data = json.load(f)
            return set(data.get("processed", []))
    return set()


def save_processed_list(state_file: Path, processed: set):
    """처리 완료된 지시문 목록 저장"""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump({
            "processed": sorted(processed),
            "updated_at": datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)


def check_instruction_status(filepath: Path) -> str:
    """지시문 파일의 상태 확인 (신규/완료/진행중)"""
    try:
        content = filepath.read_text(encoding="utf-8")
        first_lines = content[:500].lower()
        if "상태: 완료" in content or "status: done" in first_lines:
            return "완료"
        elif "상태: 진행중" in content or "status: in_progress" in first_lines:
            return "진행중"
        else:
            return "신규"
    except Exception:
        return "알수없음"


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────
def main():
    # 환경변수에서 경로 결정 (기본값: 스크립트 위치 기준)
    script_dir = Path(__file__).resolve().parent
    default_repo = script_dir.parent  # runners/ → autotrade-core/

    repo_path = Path(os.environ.get("REPO_PATH", str(default_repo)))
    poll_interval = int(os.environ.get("POLL_INTERVAL", "30"))

    # .env 로드
    env_vars = load_env(repo_path)

    # 환경변수 우선순위: OS 환경변수 > .env 파일
    telegram_token = os.environ.get("TELEGRAM_ALARM_TOKEN", env_vars.get("TELEGRAM_ALARM_TOKEN", ""))
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", env_vars.get("TELEGRAM_CHAT_ID", ""))

    # 로깅 설정
    log_dir = repo_path / "logs"
    setup_logging(log_dir)

    # 상태 파일 (처리된 지시문 추적)
    state_file = repo_path / "logs" / ".watcher_state.json"

    logger.info("=" * 50)
    logger.info("auto_pull_watcher 시작")
    logger.info(f"  저장소: {repo_path}")
    logger.info(f"  감시 주기: {poll_interval}초")
    logger.info(f"  알림봇: {'설정됨' if telegram_token else '미설정'}")
    logger.info("=" * 50)

    # 초기 지시문 목록 로드
    processed = load_processed_list(state_file)
    logger.info(f"기존 처리 완료 지시문: {len(processed)}건")

    # 최초 실행 시 현재 파일들을 processed에 등록 (기존 파일 재실행 방지)
    if not processed:
        existing_files = get_instruction_files(repo_path)
        for f in existing_files:
            processed.add(f.name)
        save_processed_list(state_file, processed)
        logger.info(f"초기 등록 완료: {len(existing_files)}건 (기존 파일 스킵)")

    # 시작 알림
    if telegram_token and chat_id:
        send_telegram(
            telegram_token, chat_id,
            "🔄 *auto\\_pull\\_watcher 시작*\n"
            f"감시 주기: {poll_interval}초\n"
            f"저장소: `autotrade-core`\n"
            f"기존 지시문: {len(processed)}건 등록됨"
        )

    # 메인 감시 루프
    consecutive_errors = 0
    while True:
        try:
            # 1. 원격 변경 확인
            has_changes = check_remote_changes(repo_path)

            if has_changes:
                # 2. pull 수행
                if pull_changes(repo_path):
                    consecutive_errors = 0

                    # 3. 새 지시문 확인
                    current_files = get_instruction_files(repo_path)
                    new_instructions = []

                    for f in current_files:
                        if f.name not in processed:
                            status = check_instruction_status(f)
                            if status == "신규":
                                new_instructions.append(f)
                                logger.info(f"새 지시문 발견: {f.name}")

                    # 4. 새 지시문이 있으면 알림
                    if new_instructions:
                        file_list = "\n".join(
                            [f"  📄 `{f.name}`" for f in new_instructions]
                        )
                        msg = (
                            f"📥 *새 지시문 {len(new_instructions)}건 감지*\n\n"
                            f"{file_list}\n\n"
                            f"⏰ 감지 시각: {datetime.now().strftime('%H:%M:%S')}\n"
                            f"🔄 자동 pull 완료, 지시문 확인 중..."
                        )

                        if telegram_token and chat_id:
                            send_telegram(telegram_token, chat_id, msg)

                        # 처리 목록에 추가
                        for f in new_instructions:
                            processed.add(f.name)
                        save_processed_list(state_file, processed)

                        # 5. 지시문 내용을 stdout에 출력 (OpenClaw가 읽을 수 있도록)
                        for f in new_instructions:
                            logger.info(f"--- 지시문 내용: {f.name} ---")
                            content = f.read_text(encoding="utf-8")
                            logger.info(content[:2000])  # 최대 2000자
                            logger.info(f"--- 끝: {f.name} ---")

                    else:
                        logger.info("pull 완료, 새 지시문 없음 (코드/문서 변경)")
                else:
                    consecutive_errors += 1
            else:
                # 변경 없음 - 5분마다 한 번 로그
                pass

            # 에러 누적 시 알림
            if consecutive_errors >= 3:
                if telegram_token and chat_id:
                    send_telegram(
                        telegram_token, chat_id,
                        f"⚠️ *auto\\_pull\\_watcher 경고*\n"
                        f"연속 {consecutive_errors}회 git pull 실패\n"
                        f"수동 확인 필요"
                    )
                consecutive_errors = 0  # 알림 후 리셋

        except KeyboardInterrupt:
            logger.info("사용자 중단 (Ctrl+C)")
            if telegram_token and chat_id:
                send_telegram(telegram_token, chat_id, "⏹ *auto\\_pull\\_watcher 중지됨*")
            break

        except Exception as e:
            logger.error(f"예외 발생: {e}", exc_info=True)
            consecutive_errors += 1

        # 대기
        time.sleep(poll_interval)

    logger.info("auto_pull_watcher 종료")


if __name__ == "__main__":
    main()
