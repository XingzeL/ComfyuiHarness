"""Workflow mapping, task records and collection. All paths are package-relative."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import re
import secrets
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import Image, ImageStat

from .client import Client, HarnessError, TransportError
from .image_limits import require_pixel_limit, check_image_pixels


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_digest(value) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,100}", value):
        raise HarnessError(f"无效标识: {value!r}")
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        raise HarnessError("标识不能使用 Windows 设备名")
    return value


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise HarnessError(f"路径越出包目录: {relative}")
    return path


def is_link(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and type(value[1]) is int


def validate_graph(graph):
    if not isinstance(graph, dict) or not graph or "nodes" in graph:
        raise HarnessError("需要节点 ID 为键的 API 工作流，不接受 UI 工作流")
    for node_id, node in graph.items():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict) or not isinstance(node.get("class_type"), str):
            raise HarnessError(f"节点 {node_id} 缺少 class_type / inputs")
    visited, active = set(), set()

    def visit(node_id):
        if node_id in active:
            raise HarnessError(f"工作流存在循环: {node_id}")
        if node_id in visited:
            return
        active.add(node_id)
        for value in graph[node_id]["inputs"].values():
            if is_link(value):
                if value[0] not in graph or value[1] < 0:
                    raise HarnessError(f"节点 {node_id} 引用了不存在的节点或负输出编号")
                visit(value[0])
        active.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)


def target_input(graph, target):
    node_id = str(target["node"])
    node = graph.get(node_id)
    if not node or node.get("class_type") != target["class_type"]:
        raise HarnessError(f"映射节点类型不匹配: {node_id}")
    if target["input"] not in node["inputs"]:
        raise HarnessError(f"映射输入不存在: {node_id}.{target['input']}")
    if is_link(node["inputs"][target["input"]]):
        raise HarnessError(f"参数不能覆盖连接: {node_id}.{target['input']}")
    return node["inputs"]


def check_value(name, value, spec):
    kind = spec.get("type", "string")
    ok = {"string": isinstance(value, str), "integer": type(value) is int,
          "number": type(value) in (int, float), "boolean": type(value) is bool}.get(kind)
    if not ok or (type(value) is float and not math.isfinite(value)):
        raise HarnessError(f"参数 {name} 的类型必须为 {kind}")
    for bound, compare in (("min", lambda x, y: x < y), ("max", lambda x, y: x > y)):
        if bound in spec and compare(value, spec[bound]):
            raise HarnessError(f"参数 {name} 超出 {bound}={spec[bound]}")
    if "choices" in spec and value not in spec["choices"]:
        raise HarnessError(f"参数 {name} 不在允许值中")


def build(root: Path, task: dict, registry: dict, run_id: str | None = None) -> dict:
    """Pure local build: does not write, upload, or contact ComfyUI."""
    workflow_id = safe_id(task["workflow"])
    folder = inside(root, f"workflows/{workflow_id}")
    descriptor = read_json(folder / "workflow.spec.json")
    if descriptor["id"] != workflow_id:
        raise HarnessError("工作流目录名与 id 不一致")
    graph = copy.deepcopy(read_json(inside(folder, descriptor["template"])))
    validate_graph(graph)
    params = task.get("parameters", {})
    specs = descriptor["parameters"]
    unknown = set(params) - set(specs)
    if unknown:
        raise HarnessError(f"未知参数: {sorted(unknown)}")
    entries = registry.get("resources", [])
    resources = {item["id"]: item for item in entries}
    if len(entries) != len(resources):
        raise HarnessError("资源 ID 重复")
    effective, used, uploads, occupied = {}, [], [], set()
    for name, spec in specs.items():
        if name not in params and "default" not in spec:
            raise HarnessError(f"缺少参数: {name}")
        value = params.get(name, spec.get("default"))
        if value is None and spec.get("random_seed"):
            low = spec.get("min", 0)
            high = spec.get("max", 2**63 - 1)
            if type(low) is not int or type(high) is not int or low < 0 or high < low:
                raise HarnessError(f"参数 {name} 的随机种子范围无效")
            value = low + secrets.randbelow(high - low + 1)
        check_value(name, value, spec)
        effective[name] = value
        if spec.get("resource_kind"):
            resource = resources.get(value)
            if not resource:
                raise HarnessError(f"资源未登记: {value}")
            if resource.get("kind") != spec["resource_kind"]:
                raise HarnessError(f"资源类型不匹配: {value}")
            if not descriptor.get("family") or resource.get("family") != descriptor["family"]:
                raise HarnessError(f"资源基底不兼容或未知: {value}")
            value = resource["filename"]
            validate_relative(value)
            used.append(copy.deepcopy(resource))
        if not spec.get("targets"):
            raise HarnessError(f"参数 {name} 未定义映射")
        for target in spec["targets"]:
            key = (str(target["node"]), target["input"])
            if key in occupied:
                raise HarnessError(f"参数重复映射到 {key}")
            occupied.add(key)
            inputs = target_input(graph, target)
            if spec.get("image"):
                path = inside(root, str(value))
                if not path.is_file():
                    raise HarnessError(f"输入图不存在: {value}")
                with Image.open(path) as image:
                    image.verify()
                uploads.append({"source": path.relative_to(root.resolve()).as_posix(),
                                "sha256": digest(path.read_bytes()), "target": target})
                inputs[target["input"]] = path.name
            else:
                inputs[target["input"]] = value
    output_nodes = descriptor.get("outputs", [])
    if not output_nodes or len(set(output_nodes)) != len(output_nodes):
        raise HarnessError("必须声明唯一的 SaveImage 输出节点")
    actual_saves = {key for key, value in graph.items() if value["class_type"] == "SaveImage"}
    if set(output_nodes) != actual_saves:
        raise HarnessError("outputs 必须包含全部且仅包含标准 SaveImage 节点；其他保存方式需专用适配")
    run_id = safe_id(run_id or datetime.now().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:12])
    date = datetime.now().strftime("%Y%m%d")
    prefix = f"HarnessUI/{workflow_id}/{date}/{run_id}"
    for index, node_id in enumerate(output_nodes):
        graph[node_id]["inputs"]["filename_prefix"] = f"{prefix}/image_{index:02d}"
    return {"run_id": run_id, "workflow_id": workflow_id, "date": date,
            "workflow_sha256": json_digest(graph), "descriptor": descriptor,
            "prompt": graph, "parameters": effective, "resources": used, "uploads": uploads}


def validate_relative(value: str):
    normalized = value.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized or ".." in PurePosixPath(normalized).parts:
        raise HarnessError(f"必须使用安全的相对名称: {value!r}")


def check_dependencies(built: dict, info: dict) -> list[str]:
    """Check against live node schemas; normalize enum spelling to server values."""
    errors = []
    graph = built["prompt"]
    image_targets = {(str(u["target"]["node"]), u["target"]["input"]) for u in built["uploads"]}
    for node_id, node in graph.items():
        schema = info.get(node["class_type"])
        if not schema:
            errors.append(f"缺少节点类型: {node['class_type']}")
            continue
        if schema.get("output_node") and node["class_type"] != "SaveImage":
            errors.append(f"输出节点 {node['class_type']} 需要专用收集适配")
        definitions = schema.get("input", {})
        fields = {**definitions.get("required", {}), **definitions.get("optional", {})}
        for field in definitions.get("required", {}):
            if field not in node["inputs"]:
                errors.append(f"节点 {node_id} 缺少输入 {field}")
        for field, value in node["inputs"].items():
            label = f"{node_id}.{field}"
            if field not in fields:
                errors.append(f"未知节点输入 {label}")
                continue
            raw = fields[field]
            if not isinstance(raw, list) or not raw:
                errors.append(f"无法识别输入 schema: {label}")
                continue
            expected = raw[0]
            if is_link(value):
                origin = info.get(graph[value[0]]["class_type"], {})
                outputs = origin.get("output", [])
                if value[1] >= len(outputs):
                    errors.append(f"连接输出编号越界: {label}")
                elif isinstance(expected, str) and expected != "*" and outputs[value[1]] not in (expected, "*"):
                    errors.append(f"连接类型不匹配: {label}")
            elif (node_id, field) in image_targets:
                continue  # Uploaded immediately before POST /prompt, not in the old enum yet.
            elif isinstance(expected, list):
                matches = [item for item in expected if item == value or (
                    isinstance(item, str) and isinstance(value, str) and item.replace("\\", "/") == value.replace("\\", "/"))]
                if not matches:
                    errors.append(f"资源或枚举不可用: {label}={value}")
                else:
                    node["inputs"][field] = matches[0]
            elif expected in ("INT", "FLOAT", "STRING", "BOOLEAN"):
                limits = raw[1] if len(raw) > 1 and isinstance(raw[1], dict) else {}
                rule = {"type": {"INT": "integer", "FLOAT": "number", "STRING": "string", "BOOLEAN": "boolean"}[expected]}
                if expected in ("INT", "FLOAT"):
                    rule.update({key: limits[key] for key in ("min", "max") if key in limits})
                try:
                    check_value(label, value, rule)
                except HarnessError as exc:
                    errors.append(str(exc))
            else:
                errors.append(f"输入 {label} 需要连接或专用类型适配: {expected}")
    return errors


def inspect_service(client: Client, built: dict | None = None) -> dict:
    stats = client.json("GET", "/system_stats")
    info = client.json("GET", "/object_info")
    model_fields = {"ckpt_name", "unet_name", "vae_name", "clip_name", "lora_name"}
    models = {}
    for name, node in info.items():
        for group in ("required", "optional"):
            for field, raw in node.get("input", {}).get(group, {}).items():
                if field in model_fields and raw and isinstance(raw[0], list):
                    models[f"{name}.{field}"] = raw[0]
    errors = check_dependencies(built, info) if built else []
    return {"service_reachable": True, "system": stats, "node_types": sorted(info),
            "discoverable_models": models, "dependency_errors": errors,
            "dependency_check": "failed" if errors else ("passed" if built else "not_requested"),
            "compatibility_note": "文件可枚举不代表权重与模型兼容；family 来自人工核验的登记档案。"}


def submit(root: Path, task: dict, registry: dict, client: Client, retry_of: str | None = None,
           *, environment: dict | None = None) -> dict:
    if retry_of:
        read_json(inside(root, f"runs/{safe_id(retry_of)}/manifest.json"))
    built = build(root, task, registry)
    if environment is None:
        env_path = root / "config/environment.local.json"
        environment = read_json(env_path) if env_path.is_file() else {}
    try:
        require_pixel_limit(environment)
        parameters = built["parameters"]
        checks = []
        if "width" in parameters and "height" in parameters:
            checks.append(check_image_pixels(environment, parameters["width"], parameters["height"], "main_sampling"))
        for upload in built["uploads"]:
            with Image.open(inside(root, upload["source"])) as image:
                checks.append(check_image_pixels(environment, image.width, image.height, "input_image"))
        if not checks:
            raise ValueError("此工作流尚未提供可检查的尺寸，请由 Agent 补齐尺寸预算检查后投递。")
    except ValueError as exc:
        raise HarnessError(str(exc)) from exc
    folder = inside(root, f"runs/{built['run_id']}")
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {"version": 1, "run_id": built["run_id"], "workflow_id": built["workflow_id"],
                "date": built["date"], "created_at": timestamp(), "base_url": client.base_url,
                "client_id": str(uuid.uuid4()), "prompt_id": None, "retry_of": retry_of,
                "execution_status": "prepared", "collection_status": "not_collected", "files": [],
                "output_nodes": built["descriptor"]["outputs"], "parameters": built["parameters"],
                "resources": built["resources"], "uploads": built["uploads"],
                "workflow_sha256": built["workflow_sha256"]}
    manifest["pixel_limit_checks"] = checks
    write_json(folder / "task.json", {"workflow": task["workflow"], "parameters": built["parameters"]})
    write_json(folder / "workflow.spec.json", built["descriptor"])
    write_json(folder / "prompt.json", built["prompt"])
    write_json(folder / "manifest.json", manifest)
    posting = False
    try:
        inspection = inspect_service(client, built)
        write_json(folder / "preflight.json", {key: inspection[key] for key in ("dependency_check", "dependency_errors")})
        if inspection["dependency_errors"]:
            raise HarnessError("; ".join(inspection["dependency_errors"]))
        for index, upload in enumerate(built["uploads"]):
            source = inside(root, upload["source"])
            snapshot = folder / "inputs" / f"{index:02d}{source.suffix.lower()}"
            snapshot.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, snapshot)
            if digest(snapshot.read_bytes()) != upload["sha256"]:
                raise HarnessError("输入在 build 后发生变化，请重新提交")
            name = client.upload(snapshot, built["run_id"], index)
            validate_relative(name)
            target = upload["target"]
            built["prompt"][str(target["node"])]["inputs"][target["input"]] = name
            upload["uploaded_name"] = name
        manifest["workflow_sha256"] = json_digest(built["prompt"])
        manifest["execution_status"] = "submitting"
        write_json(folder / "prompt.json", built["prompt"])
        write_json(folder / "manifest.json", manifest)
        posting = True
        result = client.json("POST", "/prompt", json={"prompt": built["prompt"], "client_id": manifest["client_id"]})
        if not result.get("prompt_id"):
            raise HarnessError(f"未收到 prompt_id: {result}")
        if result.get("node_errors"):
            manifest["submission_node_errors"] = result["node_errors"]
        manifest["prompt_id"] = result["prompt_id"]
        manifest["execution_status"] = "submitted"
    except (HarnessError, OSError, ValueError) as exc:
        rejected = isinstance(exc, TransportError) and exc.status is not None and 400 <= exc.status < 500
        manifest["execution_status"] = "submission_unknown" if posting and not rejected else "submit_failed"
        manifest["error"] = str(exc)
    write_json(folder / "manifest.json", manifest)
    return manifest


@contextmanager
def run_lock(folder: Path):
    lock = folder / ".operation.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise HarnessError("同一任务已有操作；若进程已退出，确认后仅移除 .operation.lock") from exc
    try:
        handle.write(timestamp())
        handle.close()
        yield
    finally:
        handle.close()
        lock.unlink()


def refresh(manifest: dict, client: Client):
    prompt_id = manifest.get("prompt_id")
    if not prompt_id:
        return None
    history = client.json("GET", f"/history/{prompt_id}").get(prompt_id)
    if history is not None:
        state = history.get("status", {})
        messages = state.get("messages", [])
        if state.get("status_str") == "error" or any(m[0] in ("execution_error", "execution_interrupted") for m in messages if m):
            execution = "failed"
        elif state.get("completed") is True and state.get("status_str") == "success":
            execution = "succeeded"
        else:
            execution = "unknown"
        manifest["history_status"] = state
    else:
        queue = client.json("GET", "/queue")
        execution = "unknown"
        for key, label in (("queue_pending", "queued"), ("queue_running", "running")):
            if any(len(item) > 1 and item[1] == prompt_id for item in queue.get(key, [])):
                execution = label
        # History may be cleared after collection; retain the last observed terminal result.
        if execution == "unknown" and manifest["execution_status"] in ("succeeded", "failed"):
            execution = manifest["execution_status"]
    manifest["execution_status"] = execution
    manifest["checked_at"] = timestamp()
    return history


def status(root: Path, run_id: str, client: Client | None = None) -> dict:
    folder = inside(root, f"runs/{safe_id(run_id)}")
    with run_lock(folder):
        manifest = read_json(folder / "manifest.json")
        refresh(manifest, client or Client(manifest["base_url"]))
        write_json(folder / "manifest.json", manifest)
        return manifest


def validate_image(data: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            gray = image.convert("L")
            low, high = gray.getextrema()
            return {"ok": high > 0, "width": image.width, "height": image.height,
                    "format": image.format, "min": low, "max": high,
                    "mean": ImageStat.Stat(gray).mean[0], "suspicious_black": high == 0}
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return {"ok": False, "error": str(exc)}


def collect(root: Path, run_id: str, client: Client | None = None) -> dict:
    folder = inside(root, f"runs/{safe_id(run_id)}")
    with run_lock(folder):
        manifest = read_json(folder / "manifest.json")
        client = client or Client(manifest["base_url"])
        history = refresh(manifest, client)
        write_json(folder / "manifest.json", manifest)
        if manifest["execution_status"] != "succeeded":
            raise HarnessError(f"任务尚未成功: {manifest['execution_status']}")
        if history is None:
            history_path = folder / "history.json"
            if not history_path.exists():
                raise HarnessError("历史已清除，且没有本地历史快照，无法确定实际输出")
            history = read_json(history_path)
        write_json(folder / "history.json", history)
        output_dir = inside(root, f"outputs/{safe_id(manifest['workflow_id'])}/{safe_id(manifest['date'])}/{safe_id(run_id)}")
        output_dir.mkdir(parents=True, exist_ok=True)
        previous = {item["key"]: item for item in manifest["files"]}
        files, errors = [], []
        for node_index, node_id in enumerate(manifest["output_nodes"]):
            refs = history.get("outputs", {}).get(node_id, {}).get("images", [])
            if not refs:
                errors.append(f"输出节点 {node_id} 没有 images，不能视为结果验证通过")
            for index, ref in enumerate(refs):
                key = f"{node_id}:{index}"
                try:
                    validate_relative(ref["filename"])
                    if ref.get("subfolder"):
                        validate_relative(ref["subfolder"])
                    if ref.get("type", "output") != "output":
                        raise HarnessError("仅收集 output 类型，拒绝把预览当成图")
                    old = previous.get(key)
                    suffix = PurePosixPath(ref["filename"].replace("\\", "/")).suffix.lower()
                    if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
                        raise HarnessError("未知图像扩展名，需要适配收集器")
                    dest = output_dir / f"image_{node_index:02d}_{index:04d}{suffix}"
                    if dest.exists():
                        data = dest.read_bytes()
                        if not old or old["source"] != ref or digest(data) != old["sha256"]:
                            raise HarnessError(f"已有文件与任务记录不一致，拒绝覆盖: {dest.name}")
                    else:
                        data = client.request("GET", "/view", params=ref).content
                        with dest.open("xb") as stream:
                            stream.write(data)
                    validation = validate_image(data)
                    files.append({"key": key, "source": ref, "path": dest.relative_to(root.resolve()).as_posix(),
                                  "sha256": digest(data), "validation": validation})
                    if not validation["ok"]:
                        errors.append(f"输出 {key} 损坏或疑似纯黑，保留文件供检查")
                except (HarnessError, OSError, KeyError) as exc:
                    if key in previous:
                        files.append(previous[key])
                    errors.append(f"{key}: {exc}")
        manifest["files"] = files
        manifest["collection_errors"] = errors
        manifest["collection_status"] = "validation_failed" if errors else "verified"
        manifest["collected_at"] = timestamp()
        write_json(folder / "manifest.json", manifest)
        return manifest
