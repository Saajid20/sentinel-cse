from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_URL = "https://www.cse.lk/api/"
SUPPORTED_ENDPOINTS = {
    "marketStatus": "marketStatus",
    "todaySharePrice": "todaySharePrice",
    "tradeSummary": "tradeSummary",
    "marketSummery": "marketSummery",
    "aspiData": "aspiData",
    "snpData": "snpData",
    "approvedAnnouncement": "approvedAnnouncement",
    "getFinancialAnnouncement": "getFinancialAnnouncement",
}
TICKER_KEYS = ("ticker", "symbol", "security", "securityCode", "securitycode", "scode", "code")
PRICE_KEYS = ("last", "lastprice", "ltp", "price", "close", "open", "high", "low")
VOLUME_KEYS = ("volume", "qty", "quantity", "sharevolume", "tradevolume")
TURNOVER_KEYS = ("turnover", "value", "tradevalue")
STATUS_KEYS = ("marketstatus", "status")
TIMESTAMP_TOKENS = ("date", "time", "timestamp", "updated", "tradingday")
BID_ASK_TOKENS = ("bid", "ask", "offer", "depth")
MAX_DISCOVERY_ATTEMPTS = 8
DISCOVERY_PARAMETER_SETS = (
    {},
    {"page": "1"},
    {"page": "1", "size": "50"},
    {"page": "0", "size": "50"},
    {"start": "0", "length": "50"},
    {"offset": "0", "limit": "50"},
    {"draw": "1", "start": "0", "length": "50"},
)


class ProbeError(ValueError):
    """Raised for invalid CLI or response handling in the research probe."""


@dataclass(frozen=True)
class PreparedProbeRequest:
    endpoint: str
    url: str
    method: str
    headers: dict[str, str]
    form_payload: dict[str, str]
    encoded_payload: bytes
    timeout_seconds: float


@dataclass(frozen=True)
class SchemaSummary:
    endpoint: str
    http_status: int | None
    top_level_keys: list[str]
    detected_list_lengths: dict[str, int]
    possible_ticker_fields: list[str]
    possible_price_fields: list[str]
    possible_volume_fields: list[str]
    possible_turnover_fields: list[str]
    timestamp_fields: list[str]
    market_status_fields: list[str]
    bid_ask_depth_fields_present: bool
    bid_ask_depth_fields: list[str]


@dataclass(frozen=True)
class ProbeAttemptResult:
    request_params: dict[str, str]
    http_status: int | None
    summary: SchemaSummary
    response: Any


def validate_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()
    if normalized not in SUPPORTED_ENDPOINTS:
        raise ProbeError(
            f"Unsupported endpoint {endpoint!r}. Supported endpoints: {', '.join(sorted(SUPPORTED_ENDPOINTS))}."
        )
    return normalized


def build_endpoint_url(endpoint: str) -> str:
    normalized = validate_endpoint(endpoint)
    return urllib.parse.urljoin(BASE_URL, SUPPORTED_ENDPOINTS[normalized])


def build_form_payload(endpoint: str, params: dict[str, str] | None = None) -> dict[str, str]:
    validate_endpoint(endpoint)
    return dict(params or {})


def encode_form_payload(payload: dict[str, str]) -> bytes:
    return urllib.parse.urlencode(payload).encode("utf-8")


def prepare_probe_request(
    endpoint: str,
    timeout_seconds: float,
    params: dict[str, str] | None = None,
) -> PreparedProbeRequest:
    if timeout_seconds <= 0:
        raise ProbeError("timeout-seconds must be greater than zero.")

    payload = build_form_payload(endpoint, params)
    return PreparedProbeRequest(
        endpoint=validate_endpoint(endpoint),
        url=build_endpoint_url(endpoint),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        form_payload=payload,
        encoded_payload=encode_form_payload(payload),
        timeout_seconds=timeout_seconds,
    )


def parse_cli_params(
    repeated_params: list[str] | None = None,
    params_json: str | None = None,
) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if params_json:
        try:
            decoded = json.loads(params_json)
        except json.JSONDecodeError as error:
            raise ProbeError(f"Malformed --params-json payload: {error}") from error
        if not isinstance(decoded, dict):
            raise ProbeError("--params-json must decode to an object.")
        for key, value in decoded.items():
            if not isinstance(key, str) or not key.strip():
                raise ProbeError("--params-json keys must be non-empty strings.")
            parsed[key.strip()] = stringify_param_value(value)

    for raw_param in repeated_params or []:
        if "=" not in raw_param:
            raise ProbeError(f"Invalid --param value {raw_param!r}. Expected KEY=VALUE.")
        key, value = raw_param.split("=", 1)
        key = key.strip()
        if not key:
            raise ProbeError(f"Invalid --param value {raw_param!r}. KEY must be non-empty.")
        parsed[key] = value

    return parsed


def stringify_param_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ProbeError("Parameter values must be scalar JSON values.")


def build_discovery_payloads(
    endpoint: str,
    base_params: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    validate_endpoint(endpoint)
    base = dict(base_params or {})
    payloads: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for candidate in DISCOVERY_PARAMETER_SETS:
        payload = {**base, **candidate}
        identity = tuple(sorted(payload.items()))
        if identity in seen:
            continue
        seen.add(identity)
        payloads.append(payload)
        if len(payloads) >= MAX_DISCOVERY_ATTEMPTS:
            break
    return payloads


def execute_probe(
    prepared: PreparedProbeRequest,
    urlopen: Any = urllib.request.urlopen,
) -> tuple[int, Any]:
    request = urllib.request.Request(
        prepared.url,
        data=prepared.encoded_payload,
        headers=prepared.headers,
        method=prepared.method,
    )
    try:
        with urlopen(request, timeout=prepared.timeout_seconds) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ProbeError(f"HTTP {error.code} from {prepared.url}: {body[:200]}") from error
    except urllib.error.URLError as error:
        raise ProbeError(f"Network error for {prepared.url}: {error.reason}") from error

    try:
        return int(status), json.loads(body)
    except json.JSONDecodeError as error:
        raise ProbeError(f"Response from {prepared.url} was not valid JSON: {error}") from error


def execute_discovery(
    endpoint: str,
    timeout_seconds: float,
    base_params: dict[str, str] | None = None,
    urlopen: Any = urllib.request.urlopen,
) -> list[ProbeAttemptResult]:
    attempts: list[ProbeAttemptResult] = []
    for payload in build_discovery_payloads(endpoint, base_params):
        prepared = prepare_probe_request(endpoint, timeout_seconds, payload)
        http_status, response_data = execute_probe(prepared, urlopen=urlopen)
        attempts.append(
            ProbeAttemptResult(
                request_params=payload,
                http_status=http_status,
                summary=summarize_schema(endpoint, response_data, http_status),
                response=response_data,
            )
        )
    return attempts


def summarize_schema(endpoint: str, response_data: Any, http_status: int | None) -> SchemaSummary:
    top_level_keys = sorted(response_data.keys()) if isinstance(response_data, dict) else []
    list_lengths: dict[str, int] = {}
    ticker_fields: set[str] = set()
    price_fields: set[str] = set()
    volume_fields: set[str] = set()
    turnover_fields: set[str] = set()
    timestamp_fields: set[str] = set()
    market_status_fields: set[str] = set()
    bid_ask_fields: set[str] = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = normalize_key(key)
                key_path = f"{path}.{key}" if path else key
                classify_key_path(
                    normalized,
                    key_path,
                    ticker_fields,
                    price_fields,
                    volume_fields,
                    turnover_fields,
                    timestamp_fields,
                    market_status_fields,
                    bid_ask_fields,
                )
                walk(nested, key_path)
            return

        if isinstance(value, list):
            list_lengths[path or "<root>"] = len(value)
            for index, item in enumerate(value[:3]):
                walk(item, f"{path}[{index}]" if path else f"[{index}]")

    walk(response_data, "")

    return SchemaSummary(
        endpoint=endpoint,
        http_status=http_status,
        top_level_keys=top_level_keys,
        detected_list_lengths=dict(sorted(list_lengths.items())),
        possible_ticker_fields=sorted(ticker_fields),
        possible_price_fields=sorted(price_fields),
        possible_volume_fields=sorted(volume_fields),
        possible_turnover_fields=sorted(turnover_fields),
        timestamp_fields=sorted(timestamp_fields),
        market_status_fields=sorted(market_status_fields),
        bid_ask_depth_fields_present=bool(bid_ask_fields),
        bid_ask_depth_fields=sorted(bid_ask_fields),
    )


def classify_key_path(
    normalized_key: str,
    key_path: str,
    ticker_fields: set[str],
    price_fields: set[str],
    volume_fields: set[str],
    turnover_fields: set[str],
    timestamp_fields: set[str],
    market_status_fields: set[str],
    bid_ask_fields: set[str],
) -> None:
    if any(token == normalized_key or token in normalized_key for token in TICKER_KEYS):
        ticker_fields.add(key_path)
    if any(token in normalized_key for token in PRICE_KEYS):
        price_fields.add(key_path)
    if any(token in normalized_key for token in VOLUME_KEYS):
        volume_fields.add(key_path)
    if any(token in normalized_key for token in TURNOVER_KEYS):
        turnover_fields.add(key_path)
    if any(token in normalized_key for token in TIMESTAMP_TOKENS):
        timestamp_fields.add(key_path)
    if any(token == normalized_key or token in normalized_key for token in STATUS_KEYS):
        market_status_fields.add(key_path)
    if any(token in normalized_key for token in BID_ASK_TOKENS):
        bid_ask_fields.add(key_path)


def normalize_key(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def format_schema_summary(summary: SchemaSummary) -> str:
    lines = [
        "Sentinel-CSE CSE public API probe",
        f"endpoint: {summary.endpoint}",
        f"http status: {summary.http_status if summary.http_status is not None else 'n/a'}",
        f"top-level keys: {format_list(summary.top_level_keys)}",
        f"detected list lengths: {format_mapping(summary.detected_list_lengths)}",
        f"possible ticker/security fields: {format_list(summary.possible_ticker_fields)}",
        f"possible price fields: {format_list(summary.possible_price_fields)}",
        f"possible volume fields: {format_list(summary.possible_volume_fields)}",
        f"possible turnover fields: {format_list(summary.possible_turnover_fields)}",
        f"timestamp/date fields: {format_list(summary.timestamp_fields)}",
        f"market status fields: {format_list(summary.market_status_fields)}",
        f"bid/ask/depth fields present: {'yes' if summary.bid_ask_depth_fields_present else 'no'}",
        f"bid/ask/depth field paths: {format_list(summary.bid_ask_depth_fields)}",
    ]
    return "\n".join(lines)


def find_security_records(response_data: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if extract_ticker_from_record(value) is not None:
                records.append(value)
            for nested in value.values():
                walk(nested)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(response_data)
    deduplicated: list[dict[str, Any]] = []
    seen: set[int] = set()
    for record in records:
        identity = id(record)
        if identity not in seen:
            seen.add(identity)
            deduplicated.append(record)
    return deduplicated


def extract_ticker_from_record(record: dict[str, Any]) -> str | None:
    preferred_order = (
        "ticker",
        "symbol",
        "securitycode",
        "scode",
        "code",
        "security",
    )
    candidates: list[tuple[int, str]] = []
    for key, value in record.items():
        normalized = normalize_key(key)
        if not isinstance(value, str) or not value.strip():
            continue
        if any(token == normalized or token in normalized for token in TICKER_KEYS):
            priority = preferred_order.index(normalized) if normalized in preferred_order else len(preferred_order)
            candidates.append((priority, value.strip().upper()))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][1]
    return None


def extract_numeric_record_value(record: dict[str, Any], token_set: tuple[str, ...]) -> float | None:
    for key, value in record.items():
        normalized = normalize_key(key)
        if any(token in normalized for token in token_set):
            parsed = numeric_value(value)
            if parsed is not None:
                return parsed
    return None


def extract_status_from_payload(response_data: Any) -> str | None:
    if isinstance(response_data, dict):
        for key, value in response_data.items():
            normalized = normalize_key(key)
            if any(token == normalized or token in normalized for token in STATUS_KEYS):
                if isinstance(value, str) and value.strip():
                    return value.strip()
            status = extract_status_from_payload(value)
            if status is not None:
                return status
    elif isinstance(response_data, list):
        for item in response_data:
            status = extract_status_from_payload(item)
            if status is not None:
                return status
    return None


def load_atrad_session(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ProbeError(f"Unable to read ATrad session file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ProbeError(f"ATrad session file {path} is not valid JSON: {error}") from error

    if not isinstance(data, dict) or not isinstance(data.get("snapshots"), list):
        raise ProbeError(f"ATrad session file {path} does not look like a recorded session JSON.")
    return data


def compare_with_atrad_session(response_data: Any, atrad_session_path: str | Path) -> str:
    session = load_atrad_session(atrad_session_path)
    latest_atrad = latest_atrad_snapshots_by_ticker(session)
    cse_records = find_security_records(response_data)
    cse_status = extract_status_from_payload(response_data)

    lines = [
        "ATrad comparison:",
        f"- atrad session path: {atrad_session_path}",
        f"- atrad tickers available: {len(latest_atrad)}",
        f"- cse security-like records detected: {len(cse_records)}",
    ]

    if not cse_records:
        lines.append("- matched tickers: 0")
        lines.append("- comparison note: no security-like records with ticker/security fields were detected in the CSE payload.")
        if cse_status is not None:
            lines.append(f"- market status from CSE payload: {cse_status}")
        return "\n".join(lines)

    matches: list[str] = []
    unmatched_cse = 0
    for record in cse_records:
        ticker = extract_ticker_from_record(record)
        if ticker is None:
            continue
        atrad_snapshot = latest_atrad.get(ticker)
        if atrad_snapshot is None:
            unmatched_cse += 1
            continue

        cse_last = extract_numeric_record_value(record, PRICE_KEYS)
        cse_volume = extract_numeric_record_value(record, VOLUME_KEYS)
        cse_turnover = extract_numeric_record_value(record, TURNOVER_KEYS)
        atrad_last = numeric_value(atrad_snapshot.get("lastPrice"))
        atrad_volume = numeric_value(atrad_snapshot.get("volume"))
        atrad_turnover = numeric_value(atrad_snapshot.get("totalTurnover"))
        matches.append(
            f"- {ticker}: lastPrice={format_compare_pair(cse_last, atrad_last)}, "
            f"volume={format_compare_pair(cse_volume, atrad_volume)}, "
            f"turnover={format_compare_pair(cse_turnover, atrad_turnover)}"
        )

    lines.append(f"- matched tickers: {len(matches)}")
    lines.append(f"- unmatched CSE records: {unmatched_cse}")
    if cse_status is not None:
        lines.append(f"- market status from CSE payload: {cse_status}")
    if matches:
        lines.append("- overlapping field comparison:")
        lines.extend(matches[:10])
    else:
        lines.append("- comparison note: CSE records were detected, but none matched ATrad ticker fields.")
    return "\n".join(lines)


def latest_atrad_snapshots_by_ticker(session: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for raw_snapshot in session.get("snapshots", []):
        if not isinstance(raw_snapshot, dict):
            continue
        ticker = raw_snapshot.get("ticker")
        timestamp = raw_snapshot.get("timestamp")
        if not isinstance(ticker, str) or not isinstance(timestamp, (int, float)):
            continue
        existing = latest.get(ticker)
        if existing is None or timestamp >= existing.get("timestamp", float("-inf")):
            latest[ticker] = raw_snapshot
    return latest


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def format_compare_pair(cse_value: float | None, atrad_value: float | None) -> str:
    if cse_value is None and atrad_value is None:
        return "unavailable/unavailable"
    if cse_value is None:
        return f"unavailable/{format_number(atrad_value)}"
    if atrad_value is None:
        return f"{format_number(cse_value)}/unavailable"
    return f"{format_number(cse_value)}/{format_number(atrad_value)}"


def format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def write_json_output(path: str | Path, payload: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_dry_run_payload(prepared: PreparedProbeRequest) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "endpoint": prepared.endpoint,
        "url": prepared.url,
        "method": prepared.method,
        "headers": prepared.headers,
        "formPayload": prepared.form_payload,
        "encodedPayload": prepared.encoded_payload.decode("utf-8"),
        "timeoutSeconds": prepared.timeout_seconds,
        "looping": False,
        "retrying": False,
    }


def build_discovery_dry_run_payload(
    endpoint: str,
    timeout_seconds: float,
    base_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for payload in build_discovery_payloads(endpoint, base_params):
        prepared = prepare_probe_request(endpoint, timeout_seconds, payload)
        attempts.append(build_dry_run_payload(prepared))
    return {
        "mode": "dry-run-discovery",
        "endpoint": endpoint,
        "url": build_endpoint_url(endpoint),
        "requestParams": dict(base_params or {}),
        "boundedAttemptCount": len(attempts),
        "attempts": attempts,
        "looping": False,
        "retrying": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe unofficial public CSE website API endpoints for Sentinel-CSE research."
    )
    parser.add_argument("--endpoint", required=True, help="Endpoint name under https://www.cse.lk/api/.")
    parser.add_argument("--output-json", help="Optional output path for raw probe result JSON.")
    parser.add_argument("--summary-only", action="store_true", help="Print schema summary only.")
    parser.add_argument("--timeout-seconds", type=float, default=10, help="Single-request timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Print the prepared request without calling the network.")
    parser.add_argument(
        "--param",
        action="append",
        help="Form-encoded POST body parameter in KEY=VALUE form. Repeatable.",
    )
    parser.add_argument(
        "--params-json",
        help='JSON object of form-encoded POST body parameters, for example \'{"page":1,"size":50}\'.',
    )
    parser.add_argument(
        "--discover-pagination",
        action="store_true",
        help="Run a bounded one-off parameter discovery sequence for unofficial pagination research.",
    )
    parser.add_argument(
        "--compare-atrad-session",
        help="Optional recorded ATrad session JSON path for overlap comparison.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request_params = parse_cli_params(args.param, args.params_json)

    if args.discover_pagination and args.compare_atrad_session:
        raise ProbeError("--discover-pagination cannot be combined with --compare-atrad-session.")

    if args.discover_pagination:
        payload = build_discovery_dry_run_payload(args.endpoint, args.timeout_seconds, request_params)
        if args.dry_run:
            if args.output_json:
                write_json_output(args.output_json, payload)
            print("Sentinel-CSE CSE public API probe")
            print(f"dry run discovery: endpoint={args.endpoint}")
            print(f"bounded attempts: {payload['boundedAttemptCount']}")
            for index, attempt in enumerate(payload["attempts"], start=1):
                print(f"attempt {index}: payload={attempt['formPayload']}")
            print("network calls: skipped")
            print("looping: disabled")
            print("retrying: disabled")
            return 0

        attempts = execute_discovery(args.endpoint, args.timeout_seconds, request_params)
        output_payload = {
            "endpoint": args.endpoint,
            "url": build_endpoint_url(args.endpoint),
            "requestParams": request_params,
            "discoveryMode": True,
            "attemptCount": len(attempts),
            "attempts": [
                {
                    "requestParams": attempt.request_params,
                    "httpStatus": attempt.http_status,
                    "summary": attempt.summary.__dict__,
                    "response": attempt.response,
                }
                for attempt in attempts
            ],
        }
        if args.output_json:
            write_json_output(args.output_json, output_payload)

        print("Sentinel-CSE CSE public API probe")
        print(f"endpoint: {args.endpoint}")
        print(f"discovery mode: bounded pagination/parameter discovery ({len(attempts)} attempts)")
        for index, attempt in enumerate(attempts, start=1):
            root_list_length = len(attempt.response) if isinstance(attempt.response, list) else "n/a"
            print(f"attempt {index}: payload={attempt.request_params}")
            print(f"  http status: {attempt.http_status}")
            print(f"  root list length: {root_list_length}")
            print(f"  top-level keys: {format_list(attempt.summary.top_level_keys)}")
            print(f"  detected list lengths: {format_mapping(attempt.summary.detected_list_lengths)}")
        return 0

    prepared = prepare_probe_request(args.endpoint, args.timeout_seconds, request_params)

    if args.dry_run:
        payload = build_dry_run_payload(prepared)
        if args.output_json:
            write_json_output(args.output_json, payload)
        print("Sentinel-CSE CSE public API probe")
        print(f"dry run: endpoint={prepared.endpoint}")
        print(f"url: {prepared.url}")
        print(f"method: {prepared.method}")
        print(f"request params: {prepared.form_payload}")
        print("network call: skipped")
        print("looping: disabled")
        print("retrying: disabled")
        return 0

    http_status, response_data = execute_probe(prepared)
    summary = summarize_schema(prepared.endpoint, response_data, http_status)
    output_payload = {
        "endpoint": prepared.endpoint,
        "url": prepared.url,
        "requestParams": prepared.form_payload,
        "httpStatus": http_status,
        "summary": summary.__dict__,
        "response": response_data,
    }
    if args.output_json:
        write_json_output(args.output_json, output_payload)

    print(format_schema_summary(summary))
    if args.compare_atrad_session:
        print()
        print(compare_with_atrad_session(response_data, args.compare_atrad_session))
    elif not args.summary_only:
        records = find_security_records(response_data)
        print()
        print(f"security-like records detected: {len(records)}")
        if records:
            print(f"first detected ticker/security: {extract_ticker_from_record(records[0]) or 'n/a'}")
    return 0


def format_list(values: list[str]) -> str:
    return "none" if not values else ", ".join(values)


def format_mapping(values: dict[str, int]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in values.items())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as error:
        print(f"CSE public API probe failed: {error}")
        raise SystemExit(1) from error
