from __future__ import annotations

import json
import urllib.parse
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PYTHON_ROOT / "scripts"
SAMPLE_DATA_DIR = PYTHON_ROOT / "sample_data"
SESSION_SAMPLE_PATH = SAMPLE_DATA_DIR / "sample_session.json"
MARKET_STATUS_SAMPLE_PATH = SAMPLE_DATA_DIR / "cse_public_api_sample_market_status.json"
TODAY_SHARE_PRICE_SAMPLE_PATH = SAMPLE_DATA_DIR / "cse_public_api_sample_today_share_price.json"
TRADE_SUMMARY_SAMPLE_PATH = SAMPLE_DATA_DIR / "cse_public_api_sample_trade_summary.json"
TEST_TMP_ROOT = PYTHON_ROOT / ".tmp-test-output"
sys.path.insert(0, str(SCRIPTS_DIR))

from cse_public_api_probe import (  # noqa: E402
    BASE_URL,
    MAX_DISCOVERY_ATTEMPTS,
    ProbeError,
    build_discovery_dry_run_payload,
    build_discovery_payloads,
    build_dry_run_payload,
    build_endpoint_url,
    build_form_payload,
    compare_with_atrad_session,
    encode_form_payload,
    execute_probe,
    execute_discovery,
    find_security_records,
    format_schema_summary,
    normalize_cse_record,
    parse_cli_params,
    prepare_probe_request,
    summarize_schema,
)


def make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / uuid4().hex
    path.mkdir()
    return path


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_endpoint_url_construction() -> None:
    assert build_endpoint_url("marketStatus") == f"{BASE_URL}marketStatus"
    assert build_endpoint_url("todaySharePrice") == f"{BASE_URL}todaySharePrice"


def test_form_encoded_post_payload_construction() -> None:
    assert build_form_payload("marketStatus") == {}
    assert encode_form_payload({}) == b""


def test_repeated_param_parsing() -> None:
    parsed = parse_cli_params(["page=1", "size=50"])

    assert parsed == {"page": "1", "size": "50"}


def test_params_json_parsing() -> None:
    parsed = parse_cli_params(params_json='{"page":1,"size":50,"active":true}')

    assert parsed == {"page": "1", "size": "50", "active": "true"}


def test_prepare_probe_request_uses_single_post_request_with_timeout() -> None:
    prepared = prepare_probe_request("marketStatus", 10)

    assert prepared.method == "POST"
    assert prepared.timeout_seconds == 10
    assert prepared.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert prepared.url == f"{BASE_URL}marketStatus"


def test_params_are_included_in_form_body() -> None:
    prepared = prepare_probe_request("todaySharePrice", 10, {"page": "1", "size": "50"})

    assert prepared.form_payload == {"page": "1", "size": "50"}
    assert urllib.parse.parse_qs(prepared.encoded_payload.decode("utf-8")) == {
        "page": ["1"],
        "size": ["50"],
    }


def test_dry_run_does_not_call_network() -> None:
    prepared = prepare_probe_request("marketStatus", 10)
    payload = build_dry_run_payload(prepared)

    assert payload["mode"] == "dry-run"
    assert payload["looping"] is False
    assert payload["retrying"] is False


def test_dry_run_with_params_preserves_payload_without_network() -> None:
    prepared = prepare_probe_request("todaySharePrice", 10, {"page": "1", "size": "50"})
    payload = build_dry_run_payload(prepared)

    assert payload["formPayload"] == {"page": "1", "size": "50"}
    assert payload["encodedPayload"] in {"page=1&size=50", "size=50&page=1"}


def test_schema_summary_detects_keys_and_lists() -> None:
    payload = load_json(TODAY_SHARE_PRICE_SAMPLE_PATH)

    summary = summarize_schema("todaySharePrice", payload, 200)

    assert summary.top_level_keys == ["reqTodaySharePrice", "responseTime"]
    assert summary.detected_list_lengths["reqTodaySharePrice"] == 2
    assert summary.bid_ask_depth_fields_present is True


def test_schema_summary_detects_ticker_price_volume_fields() -> None:
    payload = load_json(TODAY_SHARE_PRICE_SAMPLE_PATH)

    summary = summarize_schema("todaySharePrice", payload, 200)
    rendered = format_schema_summary(summary)

    assert "reqTodaySharePrice[0].symbol" in summary.possible_ticker_fields
    assert "reqTodaySharePrice[0].lastTradedPrice" in summary.possible_price_fields
    assert "reqTodaySharePrice[0].sharevolume" in summary.possible_volume_fields
    assert "reqTodaySharePrice[0].turnover" in summary.possible_turnover_fields
    assert "possible ticker/security fields:" in rendered


def test_find_security_records_detects_sample_rows() -> None:
    payload = load_json(TODAY_SHARE_PRICE_SAMPLE_PATH)

    records = find_security_records(payload)

    assert len(records) == 2


def test_compare_atrad_session_handles_missing_fields_gracefully() -> None:
    payload = load_json(MARKET_STATUS_SAMPLE_PATH)

    result = compare_with_atrad_session(payload, SESSION_SAMPLE_PATH)

    assert "no security-like records" in result.lower()
    assert "market status from CSE payload: OPEN" in result


def test_compare_atrad_session_matches_overlapping_fields() -> None:
    payload = load_json(TODAY_SHARE_PRICE_SAMPLE_PATH)

    result = compare_with_atrad_session(payload, SESSION_SAMPLE_PATH, "todaySharePrice")

    assert "- matched tickers: 2" in result
    assert "ALFA.N0000: lastPrice=41.9/41.9" in result
    assert "volume=16,000/16,000" in result


def test_trade_summary_normalization_uses_sharevolume_for_volume() -> None:
    payload = load_json(TRADE_SUMMARY_SAMPLE_PATH)
    record = payload["reqTradeSummery"][0]

    normalized = normalize_cse_record(record, "tradeSummary")

    assert normalized is not None
    assert normalized.ticker == "ALFA.N0000"
    assert normalized.last_price == 41.9
    assert normalized.volume == 10246
    assert normalized.turnover == 1042468
    assert normalized.trades == 85
    assert normalized.timestamp == "2026-05-18T07:50:16Z"
    assert normalized.status == "OPEN"


def test_compare_atrad_session_trade_summary_prefers_sharevolume_over_quantity() -> None:
    payload = load_json(TRADE_SUMMARY_SAMPLE_PATH)

    result = compare_with_atrad_session(payload, SESSION_SAMPLE_PATH, "tradeSummary")

    assert "- matched tickers: 2" in result
    assert "ALFA.N0000: lastPrice=41.9/41.9" in result
    assert "volume=10,246/16,000" in result
    assert "volume=2/16,000" not in result
    assert "trades=85/unavailable" in result
    assert "timestamp=2026-05-18T07:50:16Z" in result
    assert "status=OPEN" in result


def test_compare_atrad_session_trade_summary_nested_req_trade_summery_uses_normalized_fields() -> None:
    payload = load_json(TRADE_SUMMARY_SAMPLE_PATH)

    records = find_security_records(payload)
    result = compare_with_atrad_session(payload, SESSION_SAMPLE_PATH, "tradeSummary")

    assert len(records) == 2
    assert "- cse security-like records detected: 2" in result
    assert "volume=10,246/16,000" in result
    assert "turnover=1,042,468/670,400" in result


def test_execute_probe_uses_one_network_call() -> None:
    payload = load_json(MARKET_STATUS_SAMPLE_PATH)
    prepared = prepare_probe_request("marketStatus", 10)
    calls: list[tuple[str, bytes, float]] = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.data, timeout))
        return FakeResponse(payload)

    status, response = execute_probe(prepared, urlopen=fake_urlopen)

    assert status == 200
    assert response == payload
    assert calls == [(f"{BASE_URL}marketStatus", b"", 10)]


def test_discovery_dry_run_builds_bounded_payloads() -> None:
    payload = build_discovery_dry_run_payload("todaySharePrice", 10, {"market": "equity"})

    assert payload["mode"] == "dry-run-discovery"
    assert payload["boundedAttemptCount"] <= MAX_DISCOVERY_ATTEMPTS
    assert len(payload["attempts"]) == payload["boundedAttemptCount"]
    assert payload["attempts"][0]["formPayload"] == {"market": "equity"}


def test_discovery_attempt_count_is_capped() -> None:
    payloads = build_discovery_payloads("todaySharePrice", {"market": "equity"})

    assert len(payloads) <= MAX_DISCOVERY_ATTEMPTS
    assert payloads[0] == {"market": "equity"}


def test_execute_discovery_runs_bounded_attempts_without_retries() -> None:
    payload = load_json(TODAY_SHARE_PRICE_SAMPLE_PATH)
    calls: list[tuple[str, bytes, float]] = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.data, timeout))
        return FakeResponse(payload)

    attempts = execute_discovery("todaySharePrice", 10, {"market": "equity"}, urlopen=fake_urlopen)

    assert 1 <= len(attempts) <= MAX_DISCOVERY_ATTEMPTS
    assert len(calls) == len(attempts)
    assert attempts[0].request_params == {"market": "equity"}
    assert attempts[0].summary.http_status == 200


def test_invalid_endpoint_is_rejected() -> None:
    with pytest.raises(ProbeError, match="Unsupported endpoint"):
        prepare_probe_request("unknownEndpoint", 10)


def test_invalid_key_value_param_is_rejected() -> None:
    with pytest.raises(ProbeError, match="Expected KEY=VALUE"):
        parse_cli_params(["page"])


def test_malformed_params_json_is_rejected() -> None:
    with pytest.raises(ProbeError, match="Malformed --params-json payload"):
        parse_cli_params(params_json='{"page":1')


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ProbeError, match="greater than zero"):
        prepare_probe_request("marketStatus", 0)


def test_no_loops_or_high_frequency_behavior_are_introduced() -> None:
    source = (SCRIPTS_DIR / "cse_public_api_probe.py").read_text(encoding="utf-8")

    assert "time.sleep" not in source
    assert "while True" not in source
    assert ".schedule(" not in source


def test_output_json_path_can_be_created_without_network() -> None:
    directory = make_temp_dir()
    try:
        payload = build_dry_run_payload(prepare_probe_request("marketStatus", 10))
        output = directory / "probe.json"
        output.write_text(json.dumps(payload), encoding="utf-8")

        saved = json.loads(output.read_text(encoding="utf-8"))
        assert saved["endpoint"] == "marketStatus"
    finally:
        shutil.rmtree(directory, ignore_errors=True)
