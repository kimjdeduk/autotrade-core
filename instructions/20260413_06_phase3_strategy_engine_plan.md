# Phase 3: 전략 엔진 개발 계획서

**작성자**: 사자 (Manus AI)
**보고 대상**: Commander (김재덕)
**작성일**: 2026-04-13

---

## 1. 개요

본 문서는 `autotrade-core` 프로젝트의 **Phase 3: 전략 엔진 개발**을 위한 실행 계획서입니다. Phase 1~2를 통해 구축된 데이터 수집 인프라와 사자-아사 간의 완전 자동화 파이프라인을 기반으로, 실제 매매 신호를 생성하는 핵심 엔진을 설계하고 구현하는 것을 목표로 합니다.

이 계획은 프로젝트의 [표준 폴더 구조](../standards/04_standard_folder_structure_표준폴더구조.md) 및 [시스템 구축 실행 계획](../standards/11_execution_plan_시스템구축실행계획.md)의 원칙을 엄격히 준수하여 작성되었습니다.

## 2. Phase 3 목표

Phase 3의 핵심 목표는 수집된 OHLCV 데이터를 분석하여 **매수/매도/관망(Buy/Sell/Hold)** 신호를 도출하는 독립적인 모듈을 완성하는 것입니다.

1. **전략 인터페이스 확립**: 다양한 매매 전략을 일관된 방식으로 플러그인할 수 있는 기본 구조(Base Strategy) 설계
2. **기본 기술적 지표 구현**: 이동평균선(MA), 상대강도지수(RSI), 볼린저 밴드(Bollinger Bands) 등 널리 쓰이는 지표 계산 로직 확보
3. **첫 번째 실전 전략 구현**: 이동평균선 교차(Golden/Dead Cross) 기반의 단순하지만 검증 가능한 전략 모듈 개발
4. **신호 생성 및 저장**: 계산된 매매 신호를 `outputs/today_signals.json` 형태로 표준화하여 저장하는 파이프라인 구축

## 3. 아키텍처 설계 (역할 분리 원칙)

표준 폴더 구조 원칙에 따라, 전략 엔진은 철저하게 **계산(Calculation)** 역할만 수행합니다. 데이터 수집이나 실제 주문 실행과는 완전히 분리됩니다.

| 폴더 | 역할 | 구현 대상 파일 (예시) |
|------|------|-----------------------|
| `strategies/` | **계산 및 신호 판별** | `base_strategy.py`, `ma_cross_strategy.py`, `indicators.py` |
| `runners/` | **실행 진입점** | `run_strategy.py` |
| `outputs/` | **결과물 저장** | `today_signals.json` |
| `config/` | **파라미터 설정** | `settings.yaml` (전략 변수 추가) |

## 4. 단계별 실행 계획

Phase 3는 한 번에 거대한 시스템을 만드는 대신, 작고 검증 가능한 단위로 쪼개어 점진적으로 구현합니다.

### Step 1: 전략 기반 구조(Base) 및 지표 계산기 개발
- **목표**: 모든 전략이 공통으로 상속받을 인터페이스와 기술적 지표 계산 유틸리티 생성
- **작업 내용**:
  - `strategies/base_strategy.py`: `generate_signals(df)` 추상 메서드를 가진 기본 클래스 정의
  - `strategies/indicators.py`: Pandas/NumPy를 활용한 SMA, EMA, RSI, MACD 계산 함수 구현
- **검증**: 단위 테스트(`tests/test_indicators.py`)를 통해 지표 계산의 정확성 확인

### Step 2: 첫 번째 매매 전략 (MA Cross) 구현
- **목표**: 이동평균선 골든크로스/데드크로스 기반의 실제 동작하는 전략 모듈 완성
- **작업 내용**:
  - `strategies/ma_cross_strategy.py` 구현
  - 단기 이평선(예: 5일)이 장기 이평선(예: 20일)을 상향 돌파 시 'Buy', 하향 돌파 시 'Sell' 신호 생성 로직 작성
  - `config/settings.yaml`에 단기/장기 기간 파라미터 분리

### Step 3: 전략 실행기(Runner) 및 결과 저장 파이프라인 구축
- **목표**: 수집된 데이터를 읽어 전략을 통과시키고, 최종 신호를 파일로 저장하는 흐름 완성
- **작업 내용**:
  - `runners/run_strategy.py` 작성
  - 흐름: `data/raw/`에서 최신 CSV 읽기 → `MACrossStrategy` 적용 → 오늘 날짜의 최종 신호 추출 → `outputs/today_signals.json`에 저장
- **출력 포맷 예시**:
  ```json
  {
    "date": "2026-04-13",
    "symbol": "005930",
    "strategy": "MACross",
    "signal": "BUY",
    "confidence": 0.85,
    "indicators": {"sma_5": 81000, "sma_20": 80500}
  }
  ```

### Step 4: 백테스트 프레임워크 초안 (Phase 3.5)
- **목표**: 구현된 전략이 과거 데이터에서 어떤 성과를 냈는지 검증하는 도구 마련
- **작업 내용**:
  - `backtests/simple_backtester.py` 구현
  - 과거 신호를 바탕으로 가상의 수익률(Return), 승률(Win Rate), 최대 낙폭(MDD) 계산
  - 결과를 `outputs/backtest_summary.json`으로 저장

## 5. 협업 및 자동화 연동 방안

Phase 3의 모든 개발은 방금 완성된 **완전 자동화 파이프라인**을 통해 진행됩니다.

1. **사자(Manus)**가 위 Step 1~4를 각각 개별 지시문(예: `20260414_01_implement_base_strategy.md`)으로 작성하여 GitHub에 push합니다.
2. **auto_pull_watcher**가 이를 감지하고 트리거를 생성합니다.
3. **instruction_executor**가 아사(OpenClaw)에게 실행을 지시합니다.
4. **아사(OpenClaw)**가 코드를 작성하고, 로컬 테스트를 거친 후 결과를 push합니다.
5. **사자(Manus)**가 push된 코드를 검수하고 다음 Step으로 넘어갑니다.

이 과정에서 Commander의 수동 개입은 필요하지 않으며, 알림봇을 통해 진행 상황만 모니터링하시면 됩니다.

---

**Commander 승인 요청**:
위 Phase 3 계획에 동의하시면, 바로 **Step 1 (전략 기반 구조 및 지표 계산기 개발)** 지시문을 작성하여 자동화 파이프라인에 태우겠습니다. 승인 여부를 알려주십시오.
