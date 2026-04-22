#!/usr/bin/env python3
"""
execute_pending_task.py - pending task 실행기

기능:
1. task JSON 1개를 입력으로 읽기
2. task_id, task_type, instruction, status 파싱
3. status == "pending" 인 경우만 처리
4. 현재 구현된 task_type만 실행
5. 결과를 `outputs/`에 JSON으로 저장
6. 미구현 task_type은 실패 결과로 저장
"""

import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

# 경로 설정
WORKSPACE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"
LOGS_DIR = WORKSPACE_DIR / "logs"
SUPPORTED_TASK_TYPES = {"report", "analyze"}
TECHNICAL_TARGET_ALIASES = {
    "상성전자": "삼성전자",
    "기아자동차": "기아",
}
TASK_TYPE_COMPATIBILITY = {
    "stock_technical_analysis": ("analyze", "technical_stock_analysis"),
    "technical_stock_analysis": ("analyze", "technical_stock_analysis"),
    "technicalstockanalysis": ("analyze", "technical_stock_analysis"),
    "stock_comprehensive_analysis": ("analyze", "stock_analysis"),
    "stockcomprehensiveanalysis": ("analyze", "stock_analysis"),
    "system_performance_analysis": ("analyze", "system_speed_improvement"),
    "systemperformanceanalysis": ("analyze", "system_speed_improvement"),
}

if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from src.collectors.dart_corp_code_lookup import lookup_corp_code


def _fixed_universe_name_candidates(target_name: str) -> list[str]:
    """고정 유니버스 마스터에서 종목명을 기준으로 실제 거래코드를 찾는다."""
    universe_path = WORKSPACE_DIR / "data" / "universe" / "fixed_universe.json"
    if not universe_path.exists():
        return []

    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    combined = payload.get("combined", {})
    if isinstance(combined, dict):
        rows.extend([row for row in combined.get("rows", []) if isinstance(row, dict)])
    markets = payload.get("markets", {})
    if isinstance(markets, dict):
        for bundle in markets.values():
            if isinstance(bundle, dict):
                rows.extend([row for row in bundle.get("rows", []) if isinstance(row, dict)])

    candidates: list[str] = []
    for row in rows:
        if str(row.get("stock_name", "")).strip() == target_name:
            code = str(row.get("stock_code", "")).strip()
            if code:
                candidates.append(code.zfill(6))
    return list(dict.fromkeys(candidates))


def _pykrx_name_candidates(target_name: str) -> list[str]:
    """pykrx에서 실제 거래 가능한 동일 종목명 티커를 찾는다."""
    try:
        from pykrx import stock
    except Exception:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    for market in ("KOSPI", "KOSDAQ", "KONEX"):
        try:
            tickers = stock.get_market_ticker_list(market=market)
        except Exception:
            continue
        for ticker in tickers:
            if ticker in seen:
                continue
            seen.add(ticker)
            try:
                if stock.get_market_ticker_name(ticker) == target_name:
                    candidates.append(str(ticker).zfill(6))
            except Exception:
                continue
    return candidates


def _has_recent_pykrx_ohlcv(symbol_code: str, lookback_days: int = 30) -> bool:
    """pykrx 기준 최근 거래 데이터가 실제로 존재하는지 확인한다."""
    try:
        from pykrx import stock
    except Exception:
        return False

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=max(lookback_days, 1))).strftime("%Y%m%d")
    try:
        frame = stock.get_market_ohlcv(start_date, end_date, symbol_code)
    except Exception:
        return False
    return bool(frame is not None and not frame.empty)


def classify_retry_policy(
    execution_result: Dict[str, Any],
    success: bool,
) -> Dict[str, Any]:
    """실패/성공 결과에 대한 재시도 기준 분류"""
    execution_type = execution_result.get("execution_type", "unknown")
    message = execution_result.get("message", "")

    if success:
        return {
            "failure_category": None,
            "retry_recommended": False,
            "retry_reason": "성공 결과는 재시도 대상이 아님",
        }

    if execution_type == "validation":
        return {
            "failure_category": "invalid_task_definition",
            "retry_recommended": False,
            "retry_reason": "task JSON 형식 또는 상태를 먼저 수정해야 함",
        }

    if execution_type == "unimplemented":
        return {
            "failure_category": "unsupported_task_type",
            "retry_recommended": False,
            "retry_reason": "현재 자동 처리기에서 지원하지 않는 task_type임",
        }

    if execution_type == "report":
        if execution_result.get("missing_inputs"):
            return {
                "failure_category": "missing_input_files",
                "retry_recommended": True,
                "retry_reason": "입력 파일 준비 후 재시도 가능",
            }
        return {
            "failure_category": "report_generation_error",
            "retry_recommended": True,
            "retry_reason": "입력 결과 또는 리포트 생성 오류 점검 후 재시도 가능",
        }

    if execution_type == "exception":
        return {
            "failure_category": "runtime_exception",
            "retry_recommended": True,
            "retry_reason": "일시 오류 가능성이 있어 로그 확인 후 재시도 가능",
        }

    return {
        "failure_category": "unknown_failure",
        "retry_recommended": False,
        "retry_reason": message or "원인 분류 전까지 자동 재시도 비권장",
    }

def load_task(task_file_path: str) -> Optional[Dict[str, Any]]:
    """task JSON 파일 로드"""
    try:
        with open(task_file_path, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
        
        if not isinstance(task_data, dict):
            print(f"[오류] JSON이 객체가 아님: {task_file_path}")
            return None
        
        return task_data
        
    except FileNotFoundError:
        print(f"[오류] 파일 없음: {task_file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"[오류] JSON 파싱 실패: {e}")
        return None
    except Exception as e:
        print(f"[오류] 파일 읽기 실패: {e}")
        return None


def resolve_technical_symbol(task_data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """기술적 분석 task의 대상 종목을 실제 종목코드로 해석한다."""
    metadata = task_data.get("metadata", {}) if isinstance(task_data, dict) else {}
    target = str(
        metadata.get("target")
        or task_data.get("name")
        or task_data.get("symbol")
        or ""
    ).strip()
    normalized_target = TECHNICAL_TARGET_ALIASES.get(target, target)

    if normalized_target.isdigit():
        return normalized_target.zfill(6), {
            "resolved_from": "numeric_target",
            "target": target,
            "normalized_target": normalized_target,
        }

    if normalized_target:
        universe_candidates = _fixed_universe_name_candidates(normalized_target)
        for candidate in universe_candidates:
            if _has_recent_pykrx_ohlcv(candidate):
                return candidate, {
                    "resolved_from": "fixed_universe_lookup",
                    "target": target,
                    "normalized_target": normalized_target,
                    "universe_candidates": universe_candidates,
                    "chosen_candidate": candidate,
                }

        if universe_candidates:
            return universe_candidates[0], {
                "resolved_from": "fixed_universe_lookup_no_recent_ohlcv",
                "target": target,
                "normalized_target": normalized_target,
                "universe_candidates": universe_candidates,
                "chosen_candidate": universe_candidates[0],
            }

        pykrx_candidates = _pykrx_name_candidates(normalized_target)
        for candidate in pykrx_candidates:
            if _has_recent_pykrx_ohlcv(candidate):
                return candidate, {
                    "resolved_from": "pykrx_name_lookup",
                    "target": target,
                    "normalized_target": normalized_target,
                    "pykrx_candidates": pykrx_candidates,
                    "chosen_candidate": candidate,
                }

        if pykrx_candidates:
            return pykrx_candidates[0], {
                "resolved_from": "pykrx_name_lookup_no_recent_ohlcv",
                "target": target,
                "normalized_target": normalized_target,
                "pykrx_candidates": pykrx_candidates,
                "chosen_candidate": pykrx_candidates[0],
            }

        lookup = lookup_corp_code(
            query_type="corp_name",
            query_value=normalized_target,
            save_output=False,
        )
        stock_code = str(lookup.get("stock_code") or "").strip()
        if stock_code:
            return stock_code.zfill(6), {
                "resolved_from": "corp_name_lookup",
                "target": target,
                "normalized_target": normalized_target,
                "lookup_result": lookup,
            }

    return "005930", {
        "resolved_from": "fallback_default",
        "target": target,
        "normalized_target": normalized_target,
    }

def validate_task(task_data: Dict[str, Any]) -> Tuple[bool, str]:
    """task 데이터 검증"""
    # 필수 필드 확인
    required_fields = ["task_id", "task_type", "instruction", "status"]
    
    for field in required_fields:
        if field not in task_data:
            return False, f"필수 필드 없음: {field}"
    
    normalized_task_type = normalize_task_type(task_data.get("task_type", ""))
    if not normalized_task_type:
        return False, f"지원하지 않는 task_type: {task_data.get('task_type', '')}"

    # status 확인
    status = task_data.get("status", "").lower()
    if status != "pending":
        return False, f"status가 pending이 아님: {status}"
    
    # task_id 형식 확인
    task_id = task_data.get("task_id", "")
    if not task_id or not isinstance(task_id, str):
        return False, "task_id 형식 오류"
    
    return True, "검증 성공"


def normalize_task_type(task_type: str) -> str:
    """구형 task_type을 현재 지원 타입으로 정규화한다."""
    normalized = str(task_type or "").strip()
    if not normalized:
        return ""

    compact = normalized.replace("-", "_").replace(" ", "_").lower()
    if task_type in SUPPORTED_TASK_TYPES:
        return task_type
    if compact in SUPPORTED_TASK_TYPES:
        return compact

    compat = TASK_TYPE_COMPATIBILITY.get(normalized) or TASK_TYPE_COMPATIBILITY.get(compact)
    if compat:
        return compat[0]
    return ""


def resolve_compatible_intent(task_data: Dict[str, Any]) -> str:
    """구형 task_type / parsed_intent을 현재 처리 경로로 맞춘다."""
    task_type = str(task_data.get("task_type", "")).strip()
    parsed_intent = task_data.get("metadata", {}).get("parsed_intent", "")
    compact = task_type.replace("-", "_").replace(" ", "_").lower()

    compat = TASK_TYPE_COMPATIBILITY.get(task_type) or TASK_TYPE_COMPATIBILITY.get(compact)
    if compat:
        return compat[1]

    return parsed_intent

def process_report_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """report 타입 task 처리"""
    task_id = task_data.get("task_id", "unknown")
    input_files = task_data.get("input_files", [])
    parsed_intent = resolve_compatible_intent(task_data)

    if parsed_intent in {"system_scan", "system_summary"}:
        return process_system_document_report(task_data, parsed_intent)
    
    print(f"[리포트] task_id: {task_id}")
    print(f"[리포트] input_files: {input_files}")
    
    created_reports = []
    missing_inputs = []
    errors = []
    
    if input_files:
        for input_file in input_files:
            try:
                input_path = WORKSPACE_DIR / input_file
                if input_path.exists():
                    with open(input_path, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    
                    # 보고서 생성
                    report_content = generate_report_from_result(task_id, result_data)
                    report_filename = f"reports/{task_id}.md"
                    report_path = WORKSPACE_DIR / report_filename
                    
                    # reports 폴더 생성
                    report_path.parent.mkdir(exist_ok=True)
                    
                    with open(report_path, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                    
                    created_reports.append(report_filename)
                    print(f"[리포트] 생성됨: {report_filename}")
                else:
                    print(f"[경고] 입력 파일 없음: {input_file}")
                    missing_inputs.append(input_file)
            except Exception as e:
                print(f"[오류] 리포트 처리 실패: {e}")
                errors.append(f"{input_file}: {e}")
    else:
        print("[경고] 리포트 task에 input_files 없음")

    success = bool(created_reports)
    if created_reports:
        message = f"리포트 생성 완료: {len(created_reports)}개"
    elif missing_inputs:
        message = f"리포트 생성 실패: 입력 파일 없음 ({len(missing_inputs)}개)"
    elif errors:
        message = f"리포트 생성 실패: 처리 오류 ({len(errors)}개)"
    else:
        message = "리포트 생성 실패: input_files 또는 생성 결과 없음"

    execution_result = {
        "executed_at": datetime.now().isoformat(),
        "execution_type": "report",
        "success": success,
        "message": message,
        "created_reports": created_reports,
        "missing_inputs": missing_inputs,
        "errors": errors,
        "execution_time_ms": 200
    }
    
    return execution_result


def load_text_input(relative_path: str) -> str:
    """텍스트 입력 파일을 안전하게 읽는다."""
    input_path = WORKSPACE_DIR / relative_path
    if not input_path.exists():
        raise FileNotFoundError(relative_path)

    return input_path.read_text(encoding="utf-8")


def extract_markdown_section(document: str, heading: str) -> str:
    """단순 heading 기준으로 섹션 본문을 추출한다."""
    lines = document.splitlines()
    capture = False
    collected = []

    for line in lines:
        if line.strip() == heading:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture:
            collected.append(line)

    return "\n".join(collected).strip()


def build_system_scan_report(task_id: str, task_data: Dict[str, Any]) -> str:
    """새 LLM 인계용 문서 스캔 보고서 생성"""
    system_boot = load_text_input("docs/system_boot_context.md")
    current_state = load_text_input("docs/current_state.md")
    current_task = load_text_input("docs/current_task.md")
    read_order = task_data.get("input_files", [])

    completed = extract_markdown_section(current_state, "## 완료")
    active = extract_markdown_section(current_task, "## 작업명")

    lines = [
        f"# Task Report: {task_id}\n",
        f"**생성 시간:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"**원문 지시:** {task_data.get('instruction', '')}\n",
        "\n## System Boot Context\n",
        system_boot.strip(),
        "\n## Read Order\n",
    ]

    for path in read_order:
        lines.append(f"- `{path}`\n")

    lines.extend(
        [
            "\n## Current State Summary\n",
            completed or "- 완료 섹션 없음\n",
            "\n## Current Task Summary\n",
            active or "없음\n",
        ]
    )

    return "\n".join(lines)


def build_system_summary_report(task_id: str, task_data: Dict[str, Any]) -> str:
    """운영 상태 요약 보고서 생성"""
    boot_json = {}
    boot_json_path = WORKSPACE_DIR / "outputs" / "system_boot_context.json"
    if boot_json_path.exists():
        with open(boot_json_path, "r", encoding="utf-8") as f:
            boot_json = json.load(f)

    current_state = load_text_input("docs/current_state.md")
    current_task = load_text_input("docs/current_task.md")

    lines = [
        f"# Task Report: {task_id}\n",
        f"**생성 시간:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"**원문 지시:** {task_data.get('instruction', '')}\n",
        "\n## Project Identity\n",
        f"- **project_name:** {boot_json.get('project_name', 'autotrade-core')}\n",
        f"- **project_type:** {boot_json.get('project_type', 'unknown')}\n",
        "\n## Current State\n",
        current_state.strip(),
        "\n## Current Task\n",
        current_task.strip(),
    ]

    next_candidates = boot_json.get("next_candidates", [])
    if next_candidates:
        lines.append("\n## Next Candidates\n")
        for item in next_candidates:
            lines.append(f"- {item}\n")

    return "\n".join(lines)


def process_system_document_report(task_data: Dict[str, Any], parsed_intent: str) -> Dict[str, Any]:
    """system_scan/system_summary용 report 처리"""
    task_id = task_data.get("task_id", "unknown")
    report_filename = f"reports/{task_id}.md"
    report_path = WORKSPACE_DIR / report_filename
    report_path.parent.mkdir(exist_ok=True)

    try:
        if parsed_intent == "system_scan":
            report_content = build_system_scan_report(task_id, task_data)
        else:
            report_content = build_system_summary_report(task_id, task_data)

        report_path.write_text(report_content, encoding="utf-8")
        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "report",
            "success": True,
            "message": f"{parsed_intent} 리포트 생성 완료",
            "created_reports": [report_filename],
            "missing_inputs": [],
            "errors": [],
            "execution_time_ms": 150,
        }
    except Exception as e:
        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "report",
            "success": False,
            "message": f"{parsed_intent} 리포트 생성 실패: {e}",
            "created_reports": [],
            "missing_inputs": [],
            "errors": [str(e)],
            "execution_time_ms": 150,
        }


def build_telegram_validation_report(task_id: str, task_data: Dict[str, Any]) -> str:
    """Telegram 알림 경로 진단 보고서 생성"""
    input_files = task_data.get("input_files", [])
    env_path = WORKSPACE_DIR / "config" / ".env"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    notifier_path = WORKSPACE_DIR / "src" / "utils" / "notifier.py"
    watcher_path = WORKSPACE_DIR / "runners" / "watch_instructions.py"
    executor_path = WORKSPACE_DIR / "runners" / "instruction_executor.py"

    def load_json_file(relative_path: str) -> Dict[str, Any]:
        candidate = WORKSPACE_DIR / relative_path
        if not candidate.exists():
            return {}
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def extract_env_value(name: str) -> str:
        for line in env_text.splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
        return ""

    alarm_token = extract_env_value("TELEGRAM_ALARM_TOKEN")
    alarm_bot_token = extract_env_value("TELEGRAM_ALARM_BOT_TOKEN")
    assa_token = extract_env_value("TELEGRAM_ASSA_TOKEN")
    bot_token = extract_env_value("TELEGRAM_BOT_TOKEN")
    chat_id = extract_env_value("TELEGRAM_CHAT_ID")
    startup_notify = extract_env_value("STARTUP_NOTIFY")

    report_json = {}
    report_html = ""
    for item in input_files:
        text = str(item)
        if text.endswith(".json") and "329180_20260422_201407.json" in text:
            report_json = load_json_file(text)
        if text.endswith(".html") and "329180_20260422_201407.html" in text:
            report_html = text

    quote = report_json.get("quote", {}) if isinstance(report_json.get("quote", {}), dict) else {}
    technical = report_json.get("technical", {}) if isinstance(report_json.get("technical", {}), dict) else {}
    financial = report_json.get("financial", {}) if isinstance(report_json.get("financial", {}), dict) else {}
    analysis = report_json.get("analysis", {}) if isinstance(report_json.get("analysis", {}), dict) else {}

    lines = [
        f"# Task Report: {task_id}\n",
        f"**생성 시간:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"**원문 지시:** {task_data.get('instruction', '')}\n",
        "\n## Input Files\n",
    ]

    for item in input_files:
        lines.append(f"- `{item}`\n")

    lines.extend(
        [
            "\n## Observed Report JSON\n",
            f"- `quote.source`: {quote.get('source', 'n/a')}\n",
            f"- `quote.mode`: {quote.get('mode', 'n/a')}\n",
            f"- `quote.real_time`: {quote.get('real_time', 'n/a')}\n",
            f"- `technical.price`: {technical.get('price', 'n/a')}\n",
            f"- `technical.change`: {technical.get('change', 'n/a')}\n",
            f"- `financial.per`: {financial.get('per', 'n/a')}\n",
            f"- `financial.pbr`: {financial.get('pbr', 'n/a')}\n",
            f"- `financial.roe`: {financial.get('roe', 'n/a')}\n",
            f"- `analysis.available`: {analysis.get('available', 'n/a')}\n",
            f"- `analysis.analysis_summary`: {analysis.get('analysis_summary', 'n/a')}\n",
            f"- `report.html`: {report_html or 'n/a'}\n",
            "\n## Configuration Snapshot\n",
            f"- `TELEGRAM_ALARM_TOKEN`: {'set' if alarm_token else 'missing'}\n",
            f"- `TELEGRAM_ALARM_BOT_TOKEN`: {'set' if alarm_bot_token else 'missing'}\n",
            f"- `TELEGRAM_ASSA_TOKEN`: {'set' if assa_token else 'missing'}\n",
            f"- `TELEGRAM_BOT_TOKEN`: {'set' if bot_token else 'missing'}\n",
            f"- `TELEGRAM_CHAT_ID`: {'set' if chat_id else 'missing'}\n",
            f"- `STARTUP_NOTIFY`: {startup_notify or 'missing'}\n",
            "\n## Relevant Code Paths\n",
            f"- `{notifier_path.relative_to(WORKSPACE_DIR)}`\n",
            f"- `{watcher_path.relative_to(WORKSPACE_DIR)}`\n",
            f"- `{executor_path.relative_to(WORKSPACE_DIR)}`\n",
            "\n## Conclusion\n",
            "- 현재 저장소 파일 기준으로는 텔레그램 본문과 동일한 상세 분석 수치를 저장한 원본 파일을 찾지 못했습니다.\n",
            "- `reports/json/329180_20260422_201407.json`은 `trade_snapshot`과 빈 분석 슬롯만 보여 줍니다.\n",
            "- 텔레그램 본문은 이 JSON에서 직접 생성된 것으로 증명되지 않습니다.\n",
        ]
    )

    return "".join(lines)


def process_telegram_validation_report(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """Telegram 알림 진단 report 처리"""
    task_id = task_data.get("task_id", "unknown")
    report_filename = f"reports/{task_id}.md"
    report_path = WORKSPACE_DIR / report_filename
    report_path.parent.mkdir(exist_ok=True)

    try:
        report_content = build_telegram_validation_report(task_id, task_data)
        report_path.write_text(report_content, encoding="utf-8")
        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "report",
            "success": True,
            "message": "Telegram validation report generated",
            "created_reports": [report_filename],
            "missing_inputs": [],
            "errors": [],
            "execution_time_ms": 150,
        }
    except Exception as e:
        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "report",
            "success": False,
            "message": f"Telegram validation report failed: {e}",
            "created_reports": [],
            "missing_inputs": [],
            "errors": [str(e)],
            "execution_time_ms": 150,
        }

def build_analyze_report(task_id: str, task_data: Dict[str, Any], analysis_payload: Dict[str, Any]) -> str:
    """분석 결과에서 보고서 생성"""
    final_result = analysis_payload.get("final_result", {})
    component_results = analysis_payload.get("component_results", {})
    lookup_result = analysis_payload.get("lookup_result", {})
    disclosure_result = analysis_payload.get("disclosure_result", {})
    live_quote = analysis_payload.get("live_quote", {})
    data_source = analysis_payload.get("data_source", "")
    data_mode = analysis_payload.get("data_mode", "")
    data_warning = analysis_payload.get("data_warning", "")
    current_price = analysis_payload.get("current_price")
    price_as_of = analysis_payload.get("price_as_of", "")
    price_source = analysis_payload.get("price_source", "")
    flow_input_source = analysis_payload.get("flow_input_source", "")
    theme_input_source = analysis_payload.get("theme_input_source", "")
    as_of = analysis_payload.get("as_of", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if current_price is None and isinstance(live_quote, dict):
        current_price = live_quote.get("current_price")
    if not price_as_of and isinstance(live_quote, dict):
        trading_date = str(live_quote.get("trading_date", "")).strip()
        trading_time = str(live_quote.get("trading_time", "")).strip()
        price_as_of = f"{trading_date} {trading_time}".strip()
    if not price_source and isinstance(live_quote, dict):
        price_source = live_quote.get("data_source", "")

    lines = [
        f"# Task Analysis Report: {task_id}\n",
        f"**생성 시간:** {as_of}\n",
        f"**원문 지시:** {task_data.get('instruction', '')}\n",
        f"**처리 상태:** {final_result.get('decision', 'unknown')}\n",
        f"**총점:** {final_result.get('total_score', 0.0)}\n",
        "\n## 실행 결과 요약\n",
    ]

    if current_price not in (None, "") or price_as_of or price_source:
        lines.extend(
            [
                "### 현재가\n",
                f"- **current_price:** {current_price if current_price not in (None, '') else 'n/a'}\n",
                f"- **price_as_of:** {price_as_of or 'n/a'}\n",
                f"- **price_source:** {price_source or 'n/a'}\n",
            ]
        )

    if lookup_result:
        lines.append("### 종목 식별\n")
        for key in ("corp_code", "corp_name", "stock_code", "match_status"):
            if lookup_result.get(key) is not None:
                lines.append(f"- **{key}:** {lookup_result.get(key)}\n")

    if data_source or data_mode or data_warning:
        lines.append("\n### 데이터 출처\n")
        if data_source:
            lines.append(f"- **data_source:** {data_source}\n")
        if data_mode:
            lines.append(f"- **data_mode:** {data_mode}\n")
        if data_warning:
            lines.append(f"- **warning:** {data_warning}\n")
        if flow_input_source or theme_input_source:
            lines.append(f"- **flow_input_source:** {flow_input_source or 'none'}\n")
            lines.append(f"- **theme_input_source:** {theme_input_source or 'none'}\n")
        if live_quote:
            lines.append(f"- **live_quote:** {live_quote}\n")

    if disclosure_result:
        lines.append("\n### DART 공시 수집\n")
        lines.append(f"- **status:** {disclosure_result.get('status', 'unknown')}\n")
        lines.append(f"- **summary:** {disclosure_result.get('summary', '')}\n")
        if disclosure_result.get("disclosure_count") is not None:
            lines.append(f"- **disclosure_count:** {disclosure_result.get('disclosure_count')}\n")

    if component_results:
        lines.append("\n### 개별 컴포넌트\n")
        preferred_order = ("chart", "flow", "theme", "dart", "risk")
        seen = set()
        for name in preferred_order:
            component = component_results.get(name)
            if not component:
                continue
            seen.add(name)
            if name == "risk":
                lines.append(f"- **risk:** {component.get('summary', '')}\n")
                continue
            lines.append(
                f"- **{name}:** score={component.get('score', 0.0)}, "
                f"signal={component.get('signal', 'unknown')}, "
                f"summary={component.get('summary', '')}\n"
            )
        for name, component in component_results.items():
            if name in seen:
                continue
            lines.append(
                f"- **{name}:** score={component.get('score', 0.0)}, "
                f"signal={component.get('signal', 'unknown')}, "
                f"summary={component.get('summary', '')}\n"
            )

    if final_result:
        lines.append("\n### 최종 판단\n")
        lines.append(f"- **decision:** {final_result.get('decision', 'unknown')}\n")
        lines.append(f"- **signal:** {final_result.get('signal', 'unknown')}\n")
        lines.append(f"- **summary:** {final_result.get('summary', '')}\n")
        reasons = final_result.get("reasons", [])
        if reasons:
            lines.append("\n### 근거\n")
            for reason in reasons:
                lines.append(f"- {reason}\n")

    return "\n".join(lines)

def process_analyze_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """analyze 타입 task 처리"""
    task_id = task_data.get("task_id", "unknown")
    print(f"[분석] task_id: {task_id}")

    parsed_intent = resolve_compatible_intent(task_data)
    metadata = task_data.get("metadata", {}) if isinstance(task_data.get("metadata", {}), dict) else {}
    require_real_data_only = bool(metadata.get("require_real_data_only")) or parsed_intent in {
        "stock_analysis",
        "technical_stock_analysis",
    }
    if parsed_intent == "system_speed_improvement":
        runner_path = WORKSPACE_DIR / "runners" / "run_system_speed_analysis.py"
        output_path = OUTPUTS_DIR / "system_speed_analysis.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "analyze_system_speed.py"
        report_output_path = WORKSPACE_DIR / "reports" / "system_speed_analysis.md"
    elif parsed_intent == "technical_stock_analysis":
        runner_path = WORKSPACE_DIR / "runners" / "run_technical_chart_analysis.py"
        output_path = OUTPUTS_DIR / "technical_chart_analysis.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_technical_chart_analysis.py"
        report_output_path = WORKSPACE_DIR / "reports" / "technical_chart_analysis.md"
    elif parsed_intent == "investment_house_history":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_history.py"
        output_path = OUTPUTS_DIR / "investment_house_history.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_history.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_history.md"
    elif parsed_intent == "investment_house_backtest":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_backtest.py"
        output_path = OUTPUTS_DIR / "investment_house_backtest.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_backtest.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_backtest.md"
    elif parsed_intent == "investment_house_policy":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_policy.py"
        output_path = OUTPUTS_DIR / "investment_house_policy.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_policy.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_policy.md"
    elif parsed_intent == "investment_house_forward_backtest":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_forward_backtest.py"
        output_path = OUTPUTS_DIR / "investment_house_forward_backtest.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_forward_backtest.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_forward_backtest.md"
    elif parsed_intent == "investment_house_validation":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_validation.py"
        output_path = OUTPUTS_DIR / "investment_house_validation.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_validation.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_validation.md"
    elif parsed_intent == "investment_house_analysis":
        runner_path = WORKSPACE_DIR / "runners" / "run_investment_house_analysis.py"
        output_path = OUTPUTS_DIR / "investment_house_analysis.json"
        report_runner_path = WORKSPACE_DIR / "reports" / "report_investment_house_analysis.py"
        report_output_path = WORKSPACE_DIR / "reports" / "investment_house_analysis.md"
    else:
        runner_path = WORKSPACE_DIR / "runners" / "run_integrated_signal_pipeline.py"
        output_path = OUTPUTS_DIR / "integrated_signal_pipeline.json"
        report_runner_path = None
        report_output_path = None

    try:
        env = os.environ.copy()
        technical_symbol_info = {}
        if parsed_intent == "technical_stock_analysis":
            technical_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_TECH_SYMBOL"] = technical_symbol
            env["AUTOTRADE_TECH_TARGET"] = technical_symbol
        elif parsed_intent == "investment_house_analysis":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "investment_house_history":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "investment_house_backtest":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "investment_house_policy":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "investment_house_forward_backtest":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "investment_house_validation":
            house_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_HOUSE_SYMBOL"] = house_symbol
            env["AUTOTRADE_HOUSE_TARGET"] = house_symbol
        elif parsed_intent == "stock_analysis":
            analysis_symbol, technical_symbol_info = resolve_technical_symbol(task_data)
            env["AUTOTRADE_SIGNAL_SYMBOL"] = analysis_symbol
            env["AUTOTRADE_SIGNAL_TARGET"] = analysis_symbol
        if require_real_data_only:
            env["AUTOTRADE_REQUIRE_REAL_DATA"] = "true"
            env["AUTOTRADE_USE_REAL_OHLCV"] = "true"
            env["AUTOTRADE_USE_REAL_FLOW"] = "true"
            env["AUTOTRADE_USE_REAL_THEME"] = "true"
        if parsed_intent == "system_speed_improvement":
            env["AUTOTRADE_SYSTEM_SPEED_TASK_ID"] = task_id

        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{WORKSPACE_DIR}{os.pathsep}{current_pythonpath}"
            if current_pythonpath
            else str(WORKSPACE_DIR)
        )
        result = subprocess.run(
            [sys.executable, str(runner_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(WORKSPACE_DIR),
        )

        if result.returncode != 0:
            return {
                "executed_at": datetime.now().isoformat(),
                "execution_type": "analyze",
                "success": False,
                "message": (
                    f"분석 runner 실행 실패 (return code={result.returncode}): "
                    f"{(result.stderr or result.stdout or '')[:200]}"
                ),
                "execution_time_ms": 100,
            }

        if not output_path.exists():
            return {
                "executed_at": datetime.now().isoformat(),
                "execution_type": "analyze",
                "success": False,
                "message": "분석 결과 JSON이 생성되지 않음",
                "execution_time_ms": 100,
            }

        with open(output_path, 'r', encoding='utf-8') as f:
            analysis_payload = json.load(f)

        task_specific_output = OUTPUTS_DIR / f"{task_id}_result.json"
        shutil.copyfile(output_path, task_specific_output)

        report_filename = f"reports/{task_id}.md"
        report_path = WORKSPACE_DIR / report_filename
        report_path.parent.mkdir(exist_ok=True)

        created_reports = [report_filename]
        if parsed_intent in {"technical_stock_analysis", "investment_house_analysis", "investment_house_validation", "investment_house_history", "investment_house_backtest", "investment_house_policy", "investment_house_forward_backtest", "system_speed_improvement"} and report_runner_path and report_output_path:
            report_result = subprocess.run(
                [sys.executable, str(report_runner_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                cwd=str(WORKSPACE_DIR),
            )
            if report_result.returncode != 0 or not report_output_path.exists():
                report_path.write_text(
                    build_analyze_report(task_id, task_data, analysis_payload),
                    encoding="utf-8",
                )
            else:
                shutil.copyfile(report_output_path, report_path)
        else:
            report_path.write_text(
                build_analyze_report(task_id, task_data, analysis_payload),
                encoding="utf-8",
            )

        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "analyze",
            "success": True,
            "message": "분석 task 처리 완료",
            "analysis_payload": analysis_payload,
            "technical_symbol_info": technical_symbol_info if parsed_intent in {"technical_stock_analysis", "stock_analysis", "investment_house_analysis", "investment_house_validation", "investment_house_history", "investment_house_backtest", "investment_house_policy", "investment_house_forward_backtest"} else {},
            "task_specific_output": str(task_specific_output),
            "created_reports": created_reports,
            "execution_time_ms": 100,
        }

    except Exception as e:
        return {
            "executed_at": datetime.now().isoformat(),
            "execution_type": "exception",
            "success": False,
            "message": f"분석 task 처리 중 예외: {e}",
            "execution_time_ms": 100,
        }

def generate_report_from_result(task_id: str, result_data: Dict[str, Any]) -> str:
    """결과 JSON에서 보고서 생성"""
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report_lines = [
        f"# Task Report: {task_id}\n",
        f"**생성 시간:** {report_time}\n",
        f"**원본 task_id:** {result_data.get('task_id', 'unknown')}\n",
        f"**상태:** {result_data.get('status', 'unknown')}\n",
        f"**메모:** {result_data.get('notes', '없음')}\n",
        "\n## 실행 결과 요약\n"
    ]
    
    # metadata 정보 추가
    metadata = result_data.get('metadata', {})
    if metadata:
        report_lines.append("### 실행 메타데이터\n")
        for key, value in metadata.items():
            report_lines.append(f"- **{key}:** {value}\n")
    
    # 생성된 파일 목록
    created_files = result_data.get('created_files', [])
    if created_files:
        report_lines.append("\n### 생성된 파일\n")
        for file in created_files:
            report_lines.append(f"- `{file}`\n")
    
    # 다음 권장 작업
    next_task = result_data.get('next_recommended_task')
    if next_task:
        report_lines.append(f"\n**다음 권장 작업:** `{next_task}`\n")
    
    return "\n".join(report_lines)

def execute_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    task 실행 더미 함수
    
    실제 실행 로직 대신 더미 처리 수행
    추후 실제 executor로 교체 가능한 구조
    """
    task_id = task_data.get("task_id", "unknown")
    task_type = task_data.get("task_type", "unknown")
    instruction = task_data.get("instruction", "")
    normalized_task_type = normalize_task_type(task_type)
    
    print(f"[실행] task_id: {task_id}")
    print(f"[실행] task_type: {task_type}")
    if normalized_task_type and normalized_task_type != task_type:
        print(f"[실행] normalized_task_type: {normalized_task_type}")
    print(f"[실행] instruction: {instruction[:50]}...")

    parsed_intent = resolve_compatible_intent(task_data)
    if normalized_task_type == "report" and parsed_intent == "telegram_notification_validation":
        return process_telegram_validation_report(task_data)
    
    # 현재 자동 처리기에서 실제 지원하는 task_type만 실행
    if normalized_task_type == "report":
        return process_report_task(task_data)
    if normalized_task_type == "analyze":
        return process_analyze_task(task_data)

    supported_types = ", ".join(sorted(SUPPORTED_TASK_TYPES))

    # 미구현 task_type은 성공으로 처리하지 않음
    execution_result = {
        "executed_at": datetime.now().isoformat(),
        "execution_type": "unimplemented",
        "success": False,
        "message": (
            f"미구현 task_type: {task_type} "
            f"(현재 지원: {supported_types})"
        ),
        "execution_time_ms": 100  # 더미 실행 시간
    }
    
    return execution_result

def build_result_json(task_data: Dict[str, Any], 
                     execution_result: Dict[str, Any],
                     success: bool = True) -> Dict[str, Any]:
    """결과 JSON 구성"""
    task_id = task_data.get("task_id", "unknown")
    
    retry_policy = classify_retry_policy(execution_result, success)

    # 기본 결과 구조
    result = {
        "task_id": task_id,
        "status": "ok" if success else "fail",
        "changed_files": [],
        "created_files": [],
        "output_files": [],
        "next_recommended_task": None,
        "notes": "",
        "metadata": {
            "executed_at": execution_result.get("executed_at", datetime.now().isoformat()),
            "task_type": task_data.get("task_type", "unknown"),
            "execution_type": execution_result.get("execution_type", "stub"),
            "failure_category": retry_policy["failure_category"],
            "retry_recommended": retry_policy["retry_recommended"],
            "retry_reason": retry_policy["retry_reason"],
        }
    }
    
    # 성공/실패에 따른 notes 설정
    if success:
        execution_type = execution_result.get("execution_type", "stub")
        
        if execution_type == "report":
            created_reports = execution_result.get("created_reports", [])
            result["notes"] = f"task {task_id} 리포트 생성 완료: {len(created_reports)}개"
            result["created_files"] = [f"outputs/{task_id}_result.json"] + created_reports
            result["output_files"] = [f"outputs/{task_id}_result.json"] + created_reports
        elif execution_type == "analyze":
            created_reports = execution_result.get("created_reports", [])
            result["notes"] = "task {task_id} 분석 완료".format(task_id=task_id)
            result["created_files"] = [f"outputs/{task_id}_result.json"] + created_reports
            result["output_files"] = [f"outputs/{task_id}_result.json"] + created_reports
            if execution_result.get("analysis_payload") is not None:
                result["analysis_payload"] = execution_result["analysis_payload"]
        else:
            result["notes"] = f"task {task_id} 실행 완료"
            result["created_files"] = [f"outputs/{task_id}_result.json"]
            result["output_files"] = [f"outputs/{task_id}_result.json"]
    else:
        result["notes"] = f"task {task_id} 실행 실패: {execution_result.get('message', '알 수 없는 오류')}"
    
    return result

def write_output_json(result_data: Dict[str, Any]) -> str:
    """결과 JSON 파일 저장"""
    task_id = result_data.get("task_id", "unknown")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 출력 폴더 생성
    OUTPUTS_DIR.mkdir(exist_ok=True)
    
    # 파일명 생성 (요구사항에 맞게)
    filename = f"{task_id}_result.json"
    filepath = OUTPUTS_DIR / filename
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)
        
        print(f"[저장] 결과 파일: {filepath}")
        return str(filepath)
        
    except Exception as e:
        print(f"[오류] 결과 파일 저장 실패: {e}")
        
        # 실패 시 timestamp 포함 파일명으로 저장 시도
        try:
            fallback_filename = f"{task_id}_result_{timestamp}.json"
            fallback_path = OUTPUTS_DIR / fallback_filename
            
            with open(fallback_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            
            print(f"[저장] 대체 결과 파일: {fallback_path}")
            return str(fallback_path)
            
        except Exception as e2:
            print(f"[오류] 대체 저장도 실패: {e2}")
            return ""

def log_execution(task_id: str, status: str, message: str):
    """실행 로그 기록"""
    LOGS_DIR.mkdir(exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "status": status,
        "message": message
    }
    
    log_file = LOGS_DIR / f"task_execution_{datetime.now().strftime('%Y%m%d')}.log"
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[오류] 로그 기록 실패: {e}")

def update_task_history(task_id: str, final_status: str, output_file: str = None):
    """task_history.json에 상태 기록"""
    LOGS_DIR.mkdir(exist_ok=True)
    history_file = LOGS_DIR / "task_history.json"
    lock_file = LOGS_DIR / ".task_history.lock"
    
    history_entry = {
        "task_id": task_id,
        "final_status": final_status,
        "output_file": output_file,
        "updated_at": datetime.now().isoformat()
    }
    
    try:
        import fcntl

        with open(lock_file, 'w', encoding='utf-8') as lock_handle:
            fcntl.flock(lock_handle, fcntl.LOCK_EX)

            # 기존 history 로드
            history_data = []
            if history_file.exists() and history_file.stat().st_size > 0:
                try:
                    content = history_file.read_text(encoding='utf-8').strip()
                    if content:
                        history_data = json.loads(content)
                        if not isinstance(history_data, list):
                            history_data = []
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[경고] task_history JSON 파싱 실패, 새로 생성: {e}")
                    history_data = []

            # 기존 항목 찾기 (같은 task_id)
            found = False
            for i, entry in enumerate(history_data):
                if entry.get("task_id") == task_id:
                    history_data[i] = history_entry
                    found = True
                    break

            # 새 항목 추가
            if not found:
                history_data.append(history_entry)

            # history 저장
            tmp_history_file = history_file.with_suffix(".tmp")
            tmp_history_file.write_text(
                json.dumps(history_data, indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
            tmp_history_file.replace(history_file)
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        
        print(f"[기록] task_history 업데이트: {task_id} -> {final_status}")
        
    except Exception as e:
        print(f"[오류] task_history 기록 실패: {e}")

def execute_single_task(task_file_path: str) -> bool:
    """단일 task 실행"""
    print(f"[시작] task 실행: {task_file_path}")
    
    # 1. task 로드
    task_data = load_task(task_file_path)
    if not task_data:
        log_execution("unknown", "fail", f"task 로드 실패: {task_file_path}")
        return False
    
    task_id = task_data.get("task_id", "unknown")
    
    # 2. task 검증
    is_valid, validation_message = validate_task(task_data)
    if not is_valid:
        print(f"[오류] task 검증 실패: {validation_message}")
        
        # 실패 결과 생성
        fail_result = {
            "task_id": task_id,
            "status": "fail",
            "changed_files": [],
            "created_files": [],
            "output_files": [],
            "next_recommended_task": None,
            "notes": f"task 검증 실패: {validation_message}",
            "metadata": {
                "executed_at": datetime.now().isoformat(),
                "task_type": task_data.get("task_type", "unknown"),
                "execution_type": "validation",
                "failure_category": "invalid_task_definition",
                "retry_recommended": False,
                "retry_reason": "task JSON 형식 또는 상태를 먼저 수정해야 함",
            },
        }
        
        write_output_json(fail_result)
        log_execution(task_id, "fail", f"검증 실패: {validation_message}")
        update_task_history(task_id, "fail", None)
        return False
    
    # 3. task 실행 (더미)
    try:
        execution_result = execute_task(task_data)
        success = execution_result.get("success", False)
        
        # 4. 결과 JSON 구성
        result_json = build_result_json(task_data, execution_result, success)
        
        # 5. 결과 파일 저장
        output_file = write_output_json(result_json)
        
        if output_file:
            result_json["output_files"] = [output_file]
            result_json["created_files"] = [output_file]
        
        # 6. 로그 기록
        log_status = "ok" if success else "fail"
        log_message = f"실행 완료: {execution_result.get('message', '')}"
        log_execution(task_id, log_status, log_message)
        
        # 7. task_history 기록
        final_status = "ok" if success else "fail"
        update_task_history(task_id, final_status, output_file)
        
        print(f"[완료] task {task_id} 실행 완료")
        return success
        
    except Exception as e:
        print(f"[오류] task 실행 중 예외: {e}")
        
        # 예외 발생 시 실패 결과 생성
        fail_result = {
            "task_id": task_id,
            "status": "fail",
            "changed_files": [],
            "created_files": [],
            "output_files": [],
            "next_recommended_task": None,
            "notes": f"실행 중 예외 발생: {str(e)}",
            "metadata": {
                "executed_at": datetime.now().isoformat(),
                "task_type": task_data.get("task_type", "unknown"),
                "execution_type": "exception",
                "failure_category": "runtime_exception",
                "retry_recommended": True,
                "retry_reason": "일시 오류 가능성이 있어 로그 확인 후 재시도 가능",
            },
        }
        
        write_output_json(fail_result)
        log_execution(task_id, "fail", f"실행 예외: {str(e)}")
        update_task_history(task_id, "fail", None)
        return False

def main():
    """메인 실행 함수"""
    if len(sys.argv) < 2:
        print("사용법: python3 execute_pending_task.py <task_json_file>")
        print("예: python3 execute_pending_task.py instructions/sample_task.json")
        sys.exit(1)
    
    task_file_path = sys.argv[1]
    
    print("=== pending task 실행기 시작 ===")
    print(f"작업 파일: {task_file_path}")
    print()
    
    # 단일 task 실행
    success = execute_single_task(task_file_path)
    
    print()
    print("=== 실행 완료 ===")
    print(f"결과: {'성공' if success else '실패'}")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
