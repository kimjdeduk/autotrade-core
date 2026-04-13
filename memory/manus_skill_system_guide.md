# Manus 스킬 시스템 가이드

**작성자**: 사자 (Manus AI)
**작성일**: 2026년 4월 13일

이 문서는 Manus의 핵심 확장 기능인 **스킬(Skills) 시스템**의 내부 구조, 작동 원리, 그리고 생성 및 관리 방법을 상세히 정리한 가이드입니다. Commander의 `autotrade-core` 프로젝트에 맞춤형 스킬을 도입하기 위한 참고 자료로 활용됩니다.

## 1. 스킬(Skill)이란 무엇인가?

Manus 스킬은 특정 기능, 워크플로, 도구 통합, 도메인 지식을 캡슐화한 **모듈식 파일 시스템 기반 리소스**입니다 [1]. 범용 AI 에이전트인 Manus에게 특정 분야(예: 재무 분석, 문서 작성, 자동매매 시스템 제어)에서 정밀하고 일관성 있게 작업할 수 있도록 절차적 지식을 제공하는 "온보딩 가이드" 역할을 합니다.

### 주요 이점
*   **전문화**: 특정 도메인에 맞게 Manus의 동작과 지식을 조정합니다.
*   **재사용성**: 성공적인 워크플로를 한 번 캡처하여 여러 세션에서 재사용함으로써 일관된 결과를 보장합니다.
*   **구성 가능성**: 여러 스킬을 결합하여 복잡한 다단계 프로세스를 자동화합니다.

## 2. 스킬의 내부 구조 (Anatomy of a Skill)

모든 스킬은 `/home/ubuntu/skills/<skill-name>/` 디렉토리에 저장되며, 필수 파일인 `SKILL.md`와 선택적 리소스 폴더로 구성됩니다 [2].

```text
skill-name/
├── SKILL.md (필수)
│   ├── YAML Frontmatter (메타데이터: name, description)
│   └── Markdown 본문 (지침 및 워크플로)
└── 선택적 리소스 (Bundled Resources)
    ├── scripts/          - 실행 가능한 코드 (Python, Bash 등)
    ├── references/       - 필요할 때만 로드되는 상세 문서 (API 문서, 스키마 등)
    └── templates/        - 출력물 생성에 사용되는 템플릿, 이미지, 폰트 등
```

### 2.1. 점진적 공개 (Progressive Disclosure)
Manus는 컨텍스트 창(Context Window)의 효율적인 사용을 위해 스킬 정보를 3단계로 나누어 로드합니다 [2].

1.  **메타데이터 (`SKILL.md`의 Frontmatter)**: 항상 컨텍스트에 로드되어 있으며, Manus가 언제 이 스킬을 트리거할지 결정하는 데 사용됩니다.
2.  **`SKILL.md` 본문**: 스킬이 트리거되었을 때만 로드됩니다. 핵심 워크플로와 내비게이션 정보만 포함해야 하며, 500줄 이하로 유지하는 것이 권장됩니다.
3.  **번들 리소스 (`references/` 등)**: `SKILL.md`의 지시에 따라 특정 작업 단계에서 필요할 때만 로드됩니다.

## 3. 스킬 생성 프로세스

새로운 스킬을 생성하려면 내장된 `skill-creator` 스킬의 도구를 사용해야 합니다 [2].

### 1단계: 스킬 초기화
샌드박스 환경에서 다음 명령어를 실행하여 스킬의 기본 뼈대를 생성합니다. 스킬 이름은 소문자와 하이픈만 사용해야 합니다 (예: `autotrade-optimizer`).

```bash
python /home/ubuntu/skills/skill-creator/scripts/init_skill.py <skill-name>
```

이 스크립트는 지정된 이름의 디렉토리를 생성하고, `SKILL.md` 템플릿과 예제 리소스 폴더(`scripts/`, `references/`, `templates/`)를 자동으로 구성합니다 [3].

### 2단계: 리소스 작성 및 배치
*   반복적으로 사용되는 파이썬 스크립트나 셸 스크립트는 `scripts/`에 저장합니다.
*   API 명세서나 복잡한 정책 문서는 `references/`에 마크다운 형태로 저장합니다.
*   결과물 생성에 필요한 기본 양식은 `templates/`에 저장합니다.

### 3단계: SKILL.md 작성
`SKILL.md` 파일의 상단 YAML Frontmatter에 스킬의 이름과 **정확한 트리거 조건(description)**을 명시합니다. 본문에는 Manus가 따라야 할 단계별 워크플로를 명령문 형태로 명확하게 작성합니다.

### 4단계: 스킬 검증
작성이 완료되면 다음 명령어를 통해 스킬의 구조와 메타데이터가 규칙에 맞는지 검증합니다 [4].

```bash
python /home/ubuntu/skills/skill-creator/scripts/quick_validate.py <skill-name>
```

### 5단계: 스킬 등록 및 공유
검증이 완료된 스킬은 `message` 도구를 통해 사용자에게 `/home/ubuntu/skills/<skill-name>/SKILL.md` 경로를 전송함으로써 전달할 수 있습니다. 시스템이 이를 감지하여 사용자 인터페이스에 스킬 추가/다운로드 카드를 표시합니다 [2].

## 4. autotrade-core 프로젝트 적용 방안

앞서 조사한 "크레딧 50% 절감 기법"이나 "아사(OpenClaw) 연동 워크플로"를 스킬로 구현할 수 있습니다.

*   **크레딧 최적화 스킬 (`autotrade-efficiency`)**:
    *   `description`: "자동매매 시스템 관련 작업 시 크레딧 소모를 최소화하기 위한 지침. 데이터 검색이나 코드 작성 시 반드시 이 스킬을 먼저 로드할 것."
    *   `SKILL.md` 본문: Batch-Processing, Internal Knowledge Prioritization, Efficiency Veto 원칙을 명시.
*   **아사 제어 스킬 (`openclaw-controller`)**:
    *   `scripts/`: 아사 봇 API와 통신하는 파이썬 스크립트 포함.
    *   `references/`: 아사 봇의 명령어 목록 및 응답 스키마 문서화.

---

### References
[1] Manus Documentation: Manus 스킬. https://manus.im/docs/ko/features/skills
[2] Manus Internal Skill: `skill-creator/SKILL.md`
[3] Manus Internal Script: `skill-creator/scripts/init_skill.py`
[4] Manus Internal Script: `skill-creator/scripts/quick_validate.py`
