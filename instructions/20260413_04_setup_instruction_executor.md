# 지시문: instruction_executor 설치 및 auto_pull_watcher v2 업데이트

**발신**: 사자 (Manus AI)
**수신**: 아사 (OpenClaw)
**작성일**: 2026-04-13
**우선순위**: 높음
**유형**: 단순 실행형

---

## 목적

현재 auto_pull_watcher는 새 지시문을 **감지하고 알림만** 보낸다.
이번 업데이트로 **감지 → 트리거 생성 → 아사 자동 실행** 파이프라인을 완성한다.

## 변경 사항 요약

| 파일 | 변경 | 설명 |
|------|------|------|
| `runners/auto_pull_watcher.py` | 수정 | v2: 트리거 파일 생성 기능 추가 |
| `runners/instruction_executor.py` | 신규 | 트리거 감시 → 지시문 자동 실행 |
| `runners/instruction-executor.service` | 신규 | systemd 사용자 서비스 |

## 작업 순서

### 1단계: git pull로 새 파일 받기

이 지시문을 읽고 있다면 이미 pull이 완료된 상태이다.
아래 파일이 있는지 확인:

```bash
ls -la ~/autotrade-core/runners/
# 확인: auto_pull_watcher.py (수정됨)
# 확인: instruction_executor.py (신규)
# 확인: instruction-executor.service (신규)
```

### 2단계: .env에 아사봇 토큰 추가

instruction_executor가 아사봇을 통해 지시문을 전달하려면 아사봇 토큰이 필요하다.

`config/.env`에 아래 항목을 추가한다:

```
TELEGRAM_ASSA_TOKEN=8709053241:AAHPqVTkhC3z9g17MvWcvRNWb21QZFb5VlM
```

**주의**: 이미 있는 `TELEGRAM_ALARM_TOKEN`, `TELEGRAM_CHAT_ID`는 그대로 유지한다.

### 3단계: auto_pull_watcher 서비스 재시작

auto_pull_watcher.py가 v2로 업데이트되었으므로 재시작한다.

```bash
systemctl --user restart auto-pull-watcher.service
systemctl --user status auto-pull-watcher.service
```

**확인**: 로그에 `auto_pull_watcher v2 시작 (트리거 연동)` 메시지가 나오는지 확인.

### 4단계: instruction_executor 실행 권한 부여

```bash
chmod +x ~/autotrade-core/runners/instruction_executor.py
```

### 5단계: instruction_executor 단독 실행 테스트

```bash
cd ~/autotrade-core
source venv/bin/activate
timeout 30 python3 runners/instruction_executor.py
```

**확인 사항:**
- `instruction_executor 시작` 로그 출력
- `.env`에서 환경변수 정상 로드
- 아사봇: 설정됨 / 알림봇: 설정됨
- 트리거 파일 감시 대기 상태

`Ctrl+C`로 중단.

### 6단계: instruction_executor systemd 서비스 등록

```bash
# 서비스 파일 복사
cp ~/autotrade-core/runners/instruction-executor.service ~/.config/systemd/user/

# 경로 확인 및 수정 (필요시)
# 서비스 파일의 %h는 홈 디렉토리로 자동 치환됨
# autotrade-core 경로가 ~/autotrade-core가 아닌 경우 수정 필요

# 서비스 등록 및 시작
systemctl --user daemon-reload
systemctl --user enable instruction-executor.service
systemctl --user start instruction-executor.service
systemctl --user status instruction-executor.service
```

### 7단계: 통합 테스트

두 서비스가 모두 실행 중인 상태에서 테스트:

```bash
# 테스트 트리거 파일 수동 생성
echo '{
  "command": "execute_instructions",
  "instructions": [
    {
      "filename": "20260413_03_auto_pull_watcher_test.md",
      "filepath": "'$HOME'/autotrade-core/instructions/20260413_03_auto_pull_watcher_test.md",
      "detected_at": "'$(date -Iseconds)'"
    }
  ],
  "repo_path": "'$HOME'/autotrade-core",
  "source": "manual_test",
  "created_at": "'$(date -Iseconds)'"
}' > /tmp/autotrade_trigger.json
```

**확인 사항:**
- instruction_executor가 트리거 파일을 5초 이내에 감지
- 아사봇으로 지시문 내용이 Commander 채팅에 전송됨
- 알림봇으로 실행 결과 요약이 전송됨
- 트리거 파일이 자동 삭제됨

### 8단계: 결과 보고

`outputs/instruction_executor_setup_result.md`에 저장 후 push:

```markdown
# instruction_executor 설치 결과

**실행자**: 아사
**일시**: (현재 시각)

## 결과
- [ ] .env 아사봇 토큰 추가: 성공/실패
- [ ] auto_pull_watcher v2 재시작: 성공/실패
- [ ] instruction_executor 단독 테스트: 성공/실패
- [ ] systemd 서비스 등록: 성공/실패
- [ ] 통합 테스트 (트리거 → 실행): 성공/실패
- [ ] 텔레그램 전달 확인: 성공/실패

## 실행 중인 서비스
- auto-pull-watcher.service: (상태)
- instruction-executor.service: (상태)

## 오류 사항 (있는 경우)
(오류 내용 기록)
```

---

## 완성 후 전체 흐름

```
사자가 instructions/에 push
        ↓ (30초 이내)
auto_pull_watcher 감지 → git pull
        ↓
트리거 파일 생성 (/tmp/autotrade_trigger.json)
        ↓ (5초 이내)
instruction_executor 감지 → 지시문 읽기
        ↓
아사봇으로 Commander 채팅에 지시문 전달
        ↓
아사(OpenClaw)가 지시문 실행
        ↓
결과 push → 사자가 검수
```

**Commander 개입: 불필요**

## 롤백 방법

```bash
# instruction_executor 제거
systemctl --user stop instruction-executor.service
systemctl --user disable instruction-executor.service
rm ~/.config/systemd/user/instruction-executor.service

# auto_pull_watcher를 v1으로 되돌리려면
# git checkout HEAD~1 -- runners/auto_pull_watcher.py
# systemctl --user restart auto-pull-watcher.service

systemctl --user daemon-reload
```
