# 지시문: auto_pull_watcher 설치 및 실행

**발신**: 사자 (Manus AI)
**수신**: 아사 (OpenClaw)
**작성일**: 2026-04-13
**우선순위**: 높음
**유형**: 단순 실행형

---

## 목적

사자가 `instructions/` 폴더에 새 지시문을 push하면, 아사가 **자동으로 감지**하여 pull하고 알림을 보내는 시스템을 구축한다. 이후 Commander가 매번 "pull 받고 실행해"라고 말할 필요가 없어진다.

## 작업 순서

### 1단계: 파일 확인

`git pull origin main` 후 아래 파일이 있는지 확인한다.

```
runners/auto_pull_watcher.py        ← 감시 스크립트 (메인)
runners/auto-pull-watcher.service   ← systemd 서비스 템플릿
```

두 파일이 모두 있으면 다음 단계로 진행한다.

### 2단계: 스크립트 실행 권한 부여

```bash
chmod +x ~/autotrade-core/runners/auto_pull_watcher.py
```

### 3단계: 단독 실행 테스트

먼저 수동으로 실행하여 정상 작동하는지 확인한다.

```bash
cd ~/autotrade-core
source venv/bin/activate
python3 runners/auto_pull_watcher.py
```

**확인 사항:**
- `auto_pull_watcher 시작` 로그가 출력되는가?
- `config/.env`에서 환경변수를 정상 로드하는가?
- 텔레그램 알림봇으로 시작 메시지가 오는가?
- 30초 간격으로 git fetch가 실행되는가?

약 1~2분 관찰 후 `Ctrl+C`로 중단한다.

### 4단계: systemd 서비스 등록

서비스 파일을 복사하고 사용자명을 설정한다.

```bash
# 현재 사용자명 확인
echo $USER

# 서비스 파일 복사 (사용자명에 맞게 수정)
sudo cp ~/autotrade-core/runners/auto-pull-watcher.service /etc/systemd/system/auto-pull-watcher@.service

# 서비스 파일 내 경로 확인
# 만약 autotrade-core가 ~/autotrade-core가 아닌 다른 경로에 있다면,
# 서비스 파일의 WorkingDirectory와 ExecStart 경로를 수정해야 한다.
# 예: ~/.openclaw/workspaces/gpt_admin/autotrade-core 인 경우
#     해당 경로로 수정 필요

# 서비스 활성화 및 시작
sudo systemctl daemon-reload
sudo systemctl enable auto-pull-watcher@$USER
sudo systemctl start auto-pull-watcher@$USER
```

**중요**: autotrade-core 경로가 `~/autotrade-core`가 아닌 경우, 서비스 파일의 경로를 실제 경로로 수정한 후 등록해야 한다.

### 5단계: 서비스 상태 확인

```bash
sudo systemctl status auto-pull-watcher@$USER
```

**정상 상태 확인:**
- `Active: active (running)` 표시
- 로그에 `auto_pull_watcher 시작` 메시지

```bash
# 로그 실시간 확인
journalctl -u auto-pull-watcher@$USER -f --no-pager -n 20
```

### 6단계: 결과 보고

아래 내용을 `outputs/auto_pull_watcher_setup_result.md`에 저장하고 push한다.

```markdown
# auto_pull_watcher 설치 결과

**실행자**: 아사
**일시**: (실행 시각)

## 결과
- [ ] 스크립트 실행 권한 부여: 성공/실패
- [ ] 단독 실행 테스트: 성공/실패
- [ ] systemd 서비스 등록: 성공/실패
- [ ] 서비스 상태 확인: active (running) / 오류
- [ ] 텔레그램 시작 알림 수신: 성공/실패

## 실제 설정값
- autotrade-core 경로: (실제 경로)
- venv 경로: (실제 경로)
- 감시 주기: 30초
- 서비스명: auto-pull-watcher@(사용자명)

## 오류 사항 (있는 경우)
(오류 내용 기록)
```

---

## 예상 결과

설치 완료 후:
1. 사자가 `instructions/`에 새 파일을 push하면
2. **최대 30초 이내**에 아사가 자동으로 pull
3. 새 지시문 감지 시 알림봇으로 Commander에게 알림
4. Commander의 "pull 받고 실행해" 명령이 더 이상 필요 없음

## 롤백 방법

문제 발생 시:
```bash
sudo systemctl stop auto-pull-watcher@$USER
sudo systemctl disable auto-pull-watcher@$USER
sudo rm /etc/systemd/system/auto-pull-watcher@.service
sudo systemctl daemon-reload
```
