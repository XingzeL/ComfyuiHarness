"""Per-workflow API: direct asynchronous saving, no collect step required."""
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image

if __package__:
    from .comfy_client import ComfyUIClient, ComfyUIError
    from .models import RunConfig
    from .image_limits import check_image_pixels
    from .workflow_builder import build_prompt
else:
    from comfy_client import ComfyUIClient, ComfyUIError
    from models import RunConfig
    from image_limits import check_image_pixels
    from workflow_builder import build_prompt

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_environment(module_root, environment_path=None):
    if environment_path is not None:
        path = Path(environment_path)
    else:
        path = next((parent / "config/environment.local.json" for parent in (module_root, *module_root.parents)
                     if (parent / "config/environment.local.json").is_file()), None)
    if path is None:
        raise ComfyUIError("未找到本机 environment.local.json；请配置或显式传入 environment_path")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_recent_output(module_root):
    images = list((module_root / "output").glob("[0-9]*/**/*.png"))
    if not images:
        return {"checked": False, "reason": "尚无历史 PNG"}
    latest = max(images, key=lambda path: path.stat().st_mtime)
    try:
        with Image.open(latest) as image:
            image.load()
            low, high = image.convert("L").getextrema()
    except OSError as exc:
        raise ComfyUIError(f"最近输出不可读，请先检查: {latest.name}") from exc
    if high == 0:
        raise ComfyUIError(f"最近输出疑似纯黑，请先按本机恢复规则处理: {latest.name}")
    return {"checked": True, "file": latest.name, "min": low, "max": high}


def run_module(config, *, dry_run=False, front=False, environment_path=None,
               save_prompt_path=None, module_root=None):
    """Return immediately after enqueue. ComfyUI writes the final image itself."""
    module_root = Path(module_root or ROOT).resolve()
    cfg = RunConfig.from_dict(config) if isinstance(config, dict) else config
    workflow = json.loads((module_root / "workflow.json").read_text(encoding="utf-8-sig"))
    built = build_prompt(workflow, cfg, module_root)
    if dry_run:
        if save_prompt_path:
            write_json(Path(save_prompt_path), built["prompt"])
        return {**built, "dry_run": True, "submitted": False, "pixel_limit_checked": False,
                "notice": "离线预览未检查本机像素上限，正式投递前必须确认 limits.max_image_pixels。"}
    env = resolve_environment(module_root, environment_path)
    pixel_check = check_image_pixels(env, cfg.width, cfg.height, "main_sampling")
    folder = module_root / "output/jobs" / built["run_id"]
    folder.mkdir(parents=True, exist_ok=False)
    effective = asdict(cfg)
    effective["seed"] = built["seed"]
    manifest = {key: value for key, value in built.items() if key != "prompt"}
    manifest.update(status="prepared", prompt_id=None, base_url=env["base_url"], front=front,
                    pixel_limit_check=pixel_check,
                    created_at=datetime.now().astimezone().isoformat(), manifest_path=str(folder / "submit_manifest.json"))
    write_json(folder / "task.json", effective)
    write_json(folder / "prompt.json", built["prompt"])
    write_json(folder / "submit_manifest.json", manifest)
    client = None
    posting = False
    try:
        client = ComfyUIClient(env["base_url"])
        manifest["recent_output_check"] = check_recent_output(module_root)
        client.preflight(built["prompt"])
        manifest["client_id"] = client.client_id
        manifest["status"] = "submitting"
        write_json(folder / "prompt.json", built["prompt"])
        if save_prompt_path:
            write_json(Path(save_prompt_path), built["prompt"])
        write_json(folder / "submit_manifest.json", manifest)
        posting = True
        response = client.queue_prompt(built["prompt"], front=front)
        manifest.update(status="submitted", prompt_id=response["prompt_id"], submitted=True)
        if response.get("node_errors"):
            manifest["node_errors"] = response["node_errors"]
    except Exception as exc:
        manifest.update(status="submission_unknown" if posting and client and not client.last_post_rejected else "submit_failed",
                        error=str(exc), submitted=False)
    finally:
        if client is not None:
            client.close()
        write_json(folder / "submit_manifest.json", manifest)
    return manifest
