# 파일명 규칙

이 프로젝트의 파일명 규칙은 아래와 같다.

## 1. 기본 원칙
- 파일명은 가능하면 영어 소문자와 언더스코어(_)를 사용한다.
- 공백은 사용하지 않는다.
- 한글 파일명은 가급적 사용하지 않는다.
- 파일명만 보고 역할을 알 수 있게 만든다.

## 2. 실행 파일 규칙
형식:
- run_기능명.py
- 예: run_backtest.py
- 예: run_signal_today.py
- 예: run_collect_market_data.py

원칙:
- runners 폴더 안의 실행 파일은 run_으로 시작한다.
- 실행 파일은 직접 실행용이라는 의미가 분명해야 한다.

## 3. 수집 파일 규칙
형식:
- collect_기능명.py
- get_기능명.py

예:
- collect_kis_daily.py
- get_market_data.py

원칙:
- collectors 폴더 안의 파일은 수집 목적이 보이게 만든다.

## 4. 전략 파일 규칙
형식:
- strategy_전략명.py
- signal_기능명.py

예:
- strategy_theme_leader.py
- signal_today.py

원칙:
- 전략 계산과 신호 계산 파일임을 이름에서 바로 알 수 있어야 한다.

## 5. 백테스트 파일 규칙
형식:
- backtest_전략명.py

예:
- backtest_theme_leader.py
- backtest_ma_cross.py

원칙:
- backtests 폴더 안의 파일은 backtest_로 시작한다.

## 6. 리포트 파일 규칙
형식:
- report_기능명.py
- summary_기능명.py

예:
- report_today.py
- summary_backtest.py

## 7. 테스트 파일 규칙
형식:
- test_기능명.py

예:
- test_signal_today.py
- test_collect_kis_daily.py

원칙:
- tests 폴더 안의 파일은 test_로 시작한다.

## 8. 설정 파일 규칙
형식:
- settings.yaml
- config_기능명.yaml
- params_전략명.yaml

예:
- config_backtest.yaml
- params_theme_leader.yaml

## 9. 출력 파일 규칙
형식:
- today_signals.json
- backtest_summary.json
- report_today.md
- error_log.json
- run_status.json

원칙:
- outputs 폴더 안의 파일은 사람이 봐도 바로 뜻이 보이게 만든다.
- json은 기계가 읽는 결과
- md는 사람이 읽는 보고서
- csv는 표 데이터 저장용으로 사용한다.

## 10. 금지 원칙
- final.py, new.py, test2.py 같은 의미 없는 이름 금지
- 파일명에 날짜를 습관적으로 붙여 중복 파일을 계속 만드는 방식 금지
- 한 파일이 여러 역할을 하도록 애매한 이름 사용 금지

## 11. 권장 예시
- collectors/get_market_data.py
- strategies/strategy_theme_leader.py
- backtests/backtest_theme_leader.py
- runners/run_signal_today.py
- reports/report_today.py
- tests/test_signal_today.py
- outputs/today_signals.json
