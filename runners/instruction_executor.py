#!/usr/bin/env python3
"""
instruction_executor.py - 트리거 파일 감시 및 지시문 자동 실행

auto_pull_watcher가 새 지시문을 감지하면 트리거 파일을 생성한다.
이 스크립트는 트리거 파일을 감시하여, 발견 즉시 아사(OpenClaw)의
텔레그램 채팅에 지시문 내용을 전달하여 자동 실행을 유도한다.

작동 방식:
  1. 5초마다 /tmp/autotrade_trigger.json 존재 여부 확인
  2. 트리거 파일 발견 시 지시문 파일 읽기
  3. 아사봇 토큰으로 Commander 채팅에 지시문 요약 전송
     → Commander가 아사에게 전달하거나, 아사가 직접 처리
  4. 트리거 파일 삭제 (중복 실행 방지)
  5. 실행 결과를 로그에 기록

환경변수 (.env):
  TELEGRAM_ASSA_TOKEN   - 아사봇 토큰 (아사에게 직접 전달용)
  TELEGRAM_ALARM_TOKEN  - 알림봇 토큰 (Commander 알림용)
  TELEGRAM_CHAT_ID      - Commander 채팅 ID
  TRIGGER_FILE          - 트리거 파일 경로 (기본값: /tmp/autotrade_trigger.json)
  EXECUTOR_INTERVAL     - 감시 주기 (초, 기본값 5)
  REPO_PATH             - autotrade-core 저장소 경로
"""

import os
import sys
import time
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime


# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
logger = logging.getLogger("instruction_executor")


def setup_logging(log_dir: Path):
    """로그 디렉토리 생성 및 로거 설정"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "instruction_executor.log"

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

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
# 텔레그램 메시지 전송
# ──────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """텔레그램 메시지 전송"""
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
                logger.info("텔레그램 전송 성공")
                return True
            else:
                logger.error(f"텔레그램 API 오류: {result}")
                return False
    except Exception as e:
        logger.error(f"텔레그램 전송 실패: {e}")
        return False


# ──────────────────────────────────────────────
# 지시문 파싱
# ──────────────────────────────────────────────
def parse_instruction(filepath: Path) -> dict:
    """지시문 .md 파일을 파싱하여 핵심 정보 추출"""
    try:
        content = filepath.read_text(encoding="utf-8")

        # 제목 추출 (첫 번째 # 라인)
        title = ""
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # 유형 추출
        task_type = "알수없음"
        for line in content.split("\n"):
            if "유형" in line and ":" in line:
                task_type = line.split(":")[-1].strip().strip("*")
                break

        # 우선순위 추출
        priority = "보통"
        for line in content.split("\n"):
            if "우선순위" in line and ":" in line:
                priority = line.split(":")[-1].strip().strip("*")
                break

        return {
            "title": title,
            "type": task_type,
            "priority": priority,
            "content": content,
            "content_preview": content[:1500],
            "filepath": str(filepath),
            "filename": filepath.name
        }
    except Exception as e:
        logger.error(f"지시문 파싱 실패: {e}")
        return {
            "title": filepath.name,
            "type": "파싱실패",
            "priority": "알수없음",
            "content": "",
            "content_preview": "",
            "filepath": str(filepath),
            "filename": filepath.name
        }


# ──────────────────────────────────────────────
# 지시문 실행
# ──────────────────────────────────────────────
def execute_instruction(instruction: dict, assa_token: str, alarm_token: str,
                        chat_id: str, repo_path: Path) -> dict:
    """
    지시문을 아사에게 전달하여 실행을 유도한다.

    현재 방식: 아사봇 토큰으로 Commander 채팅에 지시문 내용을 전송
    → 아사(OpenClaw)가 이 메시지를 수신하여 처리

    향후 확장: OpenClaw Gateway HTTP API 직접 호출
    """
    filename = instruction["filename"]
    title = instruction["title"]
    priority = instruction["priority"]
    content_preview = instruction["content_preview"]

    logger.info(f"지시문 실행 시작: {filename}")

    result = {
        "filename": filename,
        "title": title,
        "status": "실패",
        "executed_at": datetime.now().isoformat(),
        "method": "telegram_forward"
    }

    # 아사봇 토큰으로 Commander 채팅에 지시문 전달
    # (아사가 이 채팅의 메시지를 읽고 처리)
    if assa_token and chat_id:
        msg = (
            f"🤖 *자동 실행 지시문*\n\n"
            f"📄 파일: `{filename}`\n"
            f"📋 제목: {title}\n"
            f"🔴 우선순위: {priority}\n\n"
            f"───────────────\n"
            f"아래 지시문을 읽고 실행해 주세요:\n\n"
            f"```\n{content_preview[:800]}\n```\n\n"
            f"📂 전체 내용: `instructions/{filename}`"
        )

        success = send_telegram(assa_token, chat_id, msg)
        if success:
            result["status"] = "전달완료"
            logger.info(f"지시문 전달 성공: {filename}")
        else:
            result["status"] = "전달실패"
            logger.error(f"지시문 전달 실패: {filename}")

    # 알림봇으로 Commander에게도 알림
    if alarm_token and chat_id:
        alarm_msg = (
            f"🚀 *instruction\\_executor 실행*\n\n"
            f"📄 `{filename}`\n"
            f"상태: {result['status']}\n"
            f"시각: {datetime.now().strftime('%H:%M:%S')}"
        )
        send_telegram(alarm_token, chat_id, alarm_msg)

    return result


# ──────────────────────────────────────────────
# 실행 기록
# ──────────────────────────────────────────────
def save_execution_log(log_file: Path, results: list):
    """실행 결과를 JSON 로그로 저장"""
    existing = []
    if log_file.exists():
        try:
            with open(log_file, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing.extend(results)

    # 최근 100건만 유지
    if len(existing) > 100:
        existing = existing[-100:]

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    logger.info(f"실행 로그 저장: {log_file} (총 {len(existing)}건)")


# ──────────────────────────────────────────────
# 메인 루프
# ──────────────────────────────────────────────
def main():
    # 경로 설정
    script_dir = Path(__file__).resolve().parent
    default_repo = script_dir.parent

    repo_path = Path(os.environ.get("REPO_PATH", str(default_repo)))
    trigger_file = Path(os.environ.get("TRIGGER_FILE", "/tmp/autotrade_trigger.json"))
    executor_interval = int(os.environ.get("EXECUTOR_INTERVAL", "5"))

    # .env 로드
    env_vars = load_env(repo_path)

    # 환경변수 우선순위: OS > .env
    assa_token = os.environ.get("TELEGRAM_ASSA_TOKEN", env_vars.get("TELEGRAM_ASSA_TOKEN", ""))
    alarm_token = os.environ.get("TELEGRAM_ALARM_TOKEN", env_vars.get("TELEGRAM_ALARM_TOKEN", ""))
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", env_vars.get("TELEGRAM_CHAT_ID", ""))

    if "TRIGGER_FILE" in env_vars and not os.environ.get("TRIGGER_FILE"):
        trigger_file = Path(env_vars["TRIGGER_FILE"])

    # 로깅 설정
    log_dir = repo_path / "logs"
    setup_logging(log_dir)

    # 실행 로그 파일
    execution_log = repo_path / "logs" / "execution_history.json"

    logger.info("=" * 50)
    logger.info("instruction_executor 시작")
    logger.info(f"  저장소: {repo_path}")
    logger.info(f"  트리거 파일: {trigger_file}")
    logger.info(f"  감시 주기: {executor_interval}초")
    logger.info(f"  아사봇: {'설정됨' if assa_token else '미설정'}")
    logger.info(f"  알림봇: {'설정됨' if alarm_token else '미설정'}")
    logger.info("=" * 50)

    # 시작 알림
    if alarm_token and chat_id:
        send_telegram(
            alarm_token, chat_id,
            "⚡ *instruction\\_executor 시작*\n"
            f"트리거 감시 주기: {executor_interval}초\n"
            f"아사봇 연동: {'✅' if assa_token else '❌'}\n"
            f"대기 중..."
        )

    # 메인 감시 루프
    while True:
        try:
            # 트리거 파일 존재 확인
            if trigger_file.exists():
                logger.info(f"트리거 파일 감지: {trigger_file}")

                # 트리거 파일 읽기
                try:
                    with open(trigger_file, "r", encoding="utf-8") as f:
                        trigger_data = json.load(f)
                except Exception as e:
                    logger.error(f"트리거 파일 읽기 실패: {e}")
                    trigger_file.unlink(missing_ok=True)
                    time.sleep(executor_interval)
                    continue

                # 트리거 파일 즉시 삭제 (중복 실행 방지)
                trigger_file.unlink(missing_ok=True)
                logger.info("트리거 파일 삭제 완료 (중복 방지)")

                # 지시문 목록 추출
                instructions = trigger_data.get("instructions", [])
                trigger_repo = Path(trigger_data.get("repo_path", str(repo_path)))

                if not instructions:
                    logger.warning("트리거에 지시문 없음, 스킵")
                    time.sleep(executor_interval)
                    continue

                # 각 지시문 실행
                results = []
                for inst_info in instructions:
                    filepath = Path(inst_info.get("filepath", ""))

                    if not filepath.exists():
                        # repo_path 기준으로 재시도
                        filepath = trigger_repo / "instructions" / inst_info.get("filename", "")

                    if filepath.exists():
                        parsed = parse_instruction(filepath)
                        result = execute_instruction(
                            parsed, assa_token, alarm_token, chat_id, trigger_repo
                        )
                        results.append(result)
                    else:
                        logger.error(f"지시문 파일 없음: {filepath}")
                        results.append({
                            "filename": inst_info.get("filename", "unknown"),
                            "status": "파일없음",
                            "executed_at": datetime.now().isoformat()
                        })

                # 실행 로그 저장
                save_execution_log(execution_log, results)

                # 종합 결과 알림
                success_count = sum(1 for r in results if r["status"] == "전달완료")
                fail_count = len(results) - success_count

                if alarm_token and chat_id:
                    summary = (
                        f"📊 *실행 결과 요약*\n\n"
                        f"전체: {len(results)}건\n"
                        f"성공: {success_count}건\n"
                        f"실패: {fail_count}건\n"
                        f"시각: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    send_telegram(alarm_token, chat_id, summary)

        except KeyboardInterrupt:
            logger.info("사용자 중단 (Ctrl+C)")
            if alarm_token and chat_id:
                send_telegram(alarm_token, chat_id, "⏹ *instruction\\_executor 중지됨*")
            break

        except Exception as e:
            logger.error(f"예외 발생: {e}", exc_info=True)

        # 대기
        time.sleep(executor_interval)

    logger.info("instruction_executor 종료")


if __name__ == "__main__":
    main()
