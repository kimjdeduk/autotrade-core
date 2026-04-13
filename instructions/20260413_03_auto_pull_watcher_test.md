# 지시문: auto_pull_watcher 자동 감지 테스트

**발신**: 사자 (Manus AI)
**수신**: 아사 (OpenClaw)
**작성일**: 2026-04-13
**우선순위**: 낮음
**유형**: 단순 실행형

---

## 목적

이 지시문은 auto_pull_watcher의 **자동 감지 기능 검증**을 위한 테스트이다.
사자가 이 파일을 push하면, 아사의 auto_pull_watcher가 30초 이내에 자동으로 감지해야 한다.

## 작업 순서

### 1단계: 이 파일을 읽었다는 것을 확인

아래 내용을 `outputs/auto_pull_test_result.md`에 저장한다.

```markdown
# auto_pull_watcher 자동 감지 테스트 결과

**실행자**: 아사
**일시**: (현재 시각)

## 결과
- 자동 감지: 성공
- 감지 시각: (auto_pull_watcher 로그에서 확인)
- 이 파일 확인 시각: (현재 시각)

## 확인 방법
이 파일은 Commander의 수동 명령 없이,
auto_pull_watcher가 자동으로 감지하여 아사가 읽은 것입니다.
```

### 2단계: 알림봇으로 Commander에게 보고

알림봇으로 아래 메시지를 전송한다.

```
✅ auto_pull_watcher 자동 감지 테스트 성공!
사자가 push한 지시문을 자동으로 감지했습니다.
Commander의 수동 명령 없이 작동 확인 완료.
```

### 3단계: 결과 push

`outputs/auto_pull_test_result.md`를 GitHub에 push한다.

---

## 성공 기준

1. Commander가 아사에게 아무 말도 하지 않았는데 아사가 이 지시문을 감지함
2. 알림봇으로 테스트 성공 메시지가 도착함
3. `outputs/auto_pull_test_result.md`가 GitHub에 push됨
