# 지시문: 전체 자동화 파이프라인 E2E 테스트

**발신**: 사자 (Manus AI)
**수신**: 아사 (OpenClaw)
**작성일**: 2026-04-13
**우선순위**: 보통
**유형**: 단순 실행형

---

## 목적

이 지시문은 **사자 → watcher → 트리거 → executor → 아사** 전체 파이프라인이 Commander 개입 없이 자동으로 동작하는지 검증하기 위한 E2E 테스트이다.

**이 지시문을 아사가 자동으로 읽고 있다면, 파이프라인이 성공한 것이다.**

## 작업 내용

### 1단계: 자동 감지 확인

이 지시문이 어떤 경로로 도달했는지 기록한다:

- auto_pull_watcher가 감지했는가?
- 트리거 파일이 생성되었는가?
- instruction_executor가 트리거를 감지했는가?
- 아사가 자동으로 이 지시문을 읽고 있는가?

### 2단계: 시스템 상태 확인

아래 명령어 결과를 기록한다:

```bash
# 서비스 상태
systemctl --user status auto-pull-watcher.service
systemctl --user status instruction-executor.service

# 최근 로그 (각 5줄)
journalctl --user -u auto-pull-watcher.service --no-pager -n 5
journalctl --user -u instruction-executor.service --no-pager -n 5

# 트리거 파일 존재 여부
ls -la /tmp/autotrade_trigger.json 2>&1 || echo "트리거 파일 없음 (정상 - executor가 처리 후 삭제)"
```

### 3단계: 결과 보고

`outputs/e2e_pipeline_test_result.md`에 저장 후 push:

```markdown
# E2E 파이프라인 테스트 결과

**실행자**: 아사
**일시**: (현재 시각)
**감지 방법**: (자동/수동)

## 파이프라인 검증
- [ ] auto_pull_watcher 감지: 성공/실패
- [ ] 트리거 파일 생성: 성공/실패
- [ ] instruction_executor 감지: 성공/실패
- [ ] 아사 자동 실행: 성공/실패

## 서비스 상태
- auto-pull-watcher: (active/inactive)
- instruction-executor: (active/inactive)

## 결론
(전체 파이프라인 성공 여부)
```

---

## 성공 기준

이 지시문이 **Commander의 수동 개입 없이** 아사에 의해 자동 실행되고, 결과가 GitHub에 push되면 **E2E 테스트 성공**이다.
