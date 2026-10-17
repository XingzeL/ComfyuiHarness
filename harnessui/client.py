"""Small HTTP transport. Never retries POST, starts a service, or clears a queue."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import requests


class HarnessError(RuntimeError):
    pass


class TransportError(HarnessError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Client:
    def __init__(self, base_url: str, timeout: float = 30):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise HarnessError("base_url 必须是 HTTP(S) 服务地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HarnessError("base_url 不应包含凭据、查询参数或 fragment")
        if timeout <= 0:
            raise HarnessError("timeout_seconds 必须大于 0")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.trust_env = False

    def request(self, method: str, path: str, **kwargs):
        try:
            response = self.session.request(
                method, self.base_url + path, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise TransportError(f"{method} {path}: {exc}") from exc
        if not response.ok:
            raise TransportError(
                f"{method} {path}: HTTP {response.status_code}: {response.text[:1000]}",
                response.status_code,
            )
        return response

    def json(self, method: str, path: str, **kwargs):
        response = self.request(method, path, **kwargs)
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise TransportError(f"{path}: 返回的不是 JSON") from exc

    def upload(self, path: Path, run_id: str, index: int) -> str:
        with path.open("rb") as stream:
            result = self.json(
                "POST", "/upload/image",
                files={"image": (f"input_{index}{path.suffix.lower()}", stream)},
                data={"subfolder": f"HarnessUI/{run_id}", "type": "input", "overwrite": "false"},
            )
        name = result.get("name")
        if not name:
            raise HarnessError("上传没有返回图像名")
        return "/".join(part for part in (result.get("subfolder", ""), name) if part)
