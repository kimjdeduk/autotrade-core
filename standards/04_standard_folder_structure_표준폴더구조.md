# 표준 폴더 구조

이 프로젝트의 외부 개발 표준 폴더 구조는 아래와 같다.

```text
autotrade-core/
├─ config/
├─ data/
├─ collectors/
├─ strategies/
├─ backtests/
├─ runners/
├─ reports/
├─ logs/
├─ tests/
└─ outputs/
```

## 각 폴더 역할

### 1. config/
- 설정 파일 보관
- API 설정
- 전략 파라미터 설정
- 경로 설정

### 2. data/
- 원천 데이터 저장
- 수집 데이터 저장
- 임시 데이터 저장

### 3. collectors/
- 데이터 수집 코드
- API 호출 코드
- 데이터 정리 코드

### 4. strategies/
- 전략 계산 코드
- 신호 계산 코드
- 조건 판별 코드

### 5. backtests/
- 과거 데이터 검증 코드
- 전략 성능 검증 코드

### 6. runners/
- 실제 실행용 파일
- 수집 실행
- 신호 실행
- 백테스트 실행

### 7. reports/
- 결과 문서 생성 코드
- 요약 리포트 생성 코드

### 8. logs/
- 실행 로그 저장
- 오류 로그 저장
- 작업 기록 저장

### 9. tests/
- 테스트 코드
- 기능 검증 코드

### 10. outputs/
- 실행 결과 보관
- today_signals.json
- backtest_summary.json
- report_today.md

## 원칙
- collectors는 수집만 담당한다.
- strategies는 계산만 담당한다.
- runners는 실행만 담당한다.
- reports는 정리만 담당한다.
- outputs는 결과만 저장한다.
- 한 파일 안에 여러 역할을 섞지 않는다.
