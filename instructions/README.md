# instructions/ 폴더 사용 규칙

이 폴더는 **사자(Manus)**가 **아사(OpenClaw)**에게 전달하는 지시문 전용 폴더입니다.

## 작동 방식

1. 사자가 `instructions/` 폴더에 지시문 파일을 push
2. Commander가 아사에게 "pull 받아" 한마디
3. 아사가 `git pull` 후 `instructions/` 폴더의 최신 지시문을 읽고 실행
4. 아사가 작업 완료 후 결과를 push
5. 사자가 직접 pull해서 검수

## 파일 명명 규칙

- 형식: `YYYYMMDD_순번_작업명.md`
- 예시: `20260413_01_phase3_strategy_engine.md`

## 상태 표시

- 파일명 끝에 상태 없음 = 신규 지시
- 아사가 실행 완료 후 → 파일 내 상단에 `상태: 완료` 추가
