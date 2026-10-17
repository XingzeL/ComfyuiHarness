"""Small per-module client; no polling or service lifecycle actions."""
import uuid
from urllib.parse import urlsplit

import requests


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    def __init__(self, base_url: str):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ComfyUIError("需要不含凭据的 HTTP(S) base_url")
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.session = requests.Session()
        self.session.trust_env = False
        self.last_post_rejected = False

    def get(self, path):
        response = self.session.get(self.base_url + path, timeout=30)
        response.raise_for_status()
        return response.json()

    def preflight(self, prompt):
        self.get("/system_stats")
        info = self.get("/object_info")
        for node_id, node in prompt.items():
            schema = info.get(node["class_type"])
            if schema is None:
                raise ComfyUIError(f"缺少节点类型 {node['class_type']}")
            fields = {**schema.get("input", {}).get("required", {}),
                      **schema.get("input", {}).get("optional", {})}
            for required in schema.get("input", {}).get("required", {}):
                if required not in node["inputs"]:
                    raise ComfyUIError(f"节点 {node_id} 缺少字段 {required}")
            for name, value in node["inputs"].items():
                if name not in fields:
                    raise ComfyUIError(f"节点字段不匹配 {node_id}.{name}")
                definition = fields[name]
                if not definition:
                    raise ComfyUIError(f"无法检查节点字段 {node_id}.{name}")
                if isinstance(definition[0], list) and not isinstance(value, list):
                    choices = definition[0]
                    matched = [choice for choice in choices if choice == value or (
                        isinstance(choice, str) and isinstance(value, str)
                        and choice.replace("\\", "/") == value.replace("\\", "/"))]
                    if not matched:
                        raise ComfyUIError(f"模型或枚举不可用 {node_id}.{name}={value}")
                    node["inputs"][name] = matched[0]

    def queue_prompt(self, prompt, front=False):
        payload = {"prompt": prompt, "client_id": self.client_id}
        if front:
            payload["front"] = True
        response = self.session.post(self.base_url + "/prompt", json=payload, timeout=60)
        self.last_post_rejected = 400 <= response.status_code < 500
        response.raise_for_status()
        result = response.json()
        if not result.get("prompt_id"):
            raise ComfyUIError(f"没有返回 prompt_id: {result}")
        return result

    def close(self):
        self.session.close()
