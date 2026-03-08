import secrets
from fastapi import Request
from typing import Tuple, Optional, Dict, Any


def generate_internal_correlation_id():
    return secrets.token_hex(16)


def get_correlation_id_and_soeid(request: Request) -> Tuple[str, str]:
    def generate_internal_correlation_id():
        return secrets.token_hex(16)

    if request is None:
        correlation_id = generate_internal_correlation_id()
        soeid = "RDI"
    else:
        correlation_id = request.headers.get("correlation-id", generate_internal_correlation_id())
        soeid = str(request.headers.get("soeid", "NA"))
    return correlation_id, soeid


def get_user_agent(request: Request) -> str:
    if request:
        return request.headers.get("User-Agent", "NA")
    return "NA"


def gen_props(headers: Optional[Dict[str, str]] = None, **kwargs) -> Dict[str, Dict[str, Any]]:
    if headers is None:
        headers = {}
    return {
        "props": {"correlation-id": headers.get("correlation-id", ""), "soeid": headers.get("soeid"),
                  "endpoint": headers.get("endpoint"),
                  "User-Agent": headers.get("User-Agent"), **kwargs}
    }


def gen_headers(request: Optional[Request] = None, endpoint: str = None) -> Dict[str, str]:
    correlation_id, soeid = get_correlation_id_and_soeid(request)
    url = endpoint or "NA"
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "correlation-id": correlation_id,
        "soeid": soeid,
        "User-Agent": get_user_agent(request),
        "endpoint": url
    }