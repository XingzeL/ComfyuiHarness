"""Replace these node mappings when adopting another API workflow."""
import copy
import math
import re
import secrets
import uuid
from datetime import datetime
from pathlib import Path

if __package__:
    from .output_paths import date_output_dir
else:
    from output_paths import date_output_dir


def build_prompt(workflow: dict, config, module_root: Path) -> dict:
    prompt = copy.deepcopy(workflow)
    for node_id, expected in {"1": "CheckpointLoaderSimple", "2": "CLIPTextEncode",
                              "3": "CLIPTextEncode", "4": "EmptyLatentImage",
                              "5": "KSampler", "7": "Image Save"}.items():
        if prompt.get(node_id, {}).get("class_type") != expected:
            raise ValueError(f"工作流节点 {node_id} 应为 {expected}，请更新本模块 builder")
    for name in ("width", "height", "steps"):
        value = getattr(config, name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} 必须是正整数")
    if config.width % 8 or config.height % 8:
        raise ValueError("示例宽高必须是 8 的倍数")
    if type(config.cfg) not in (float, int) or not math.isfinite(config.cfg) or config.cfg < 0:
        raise ValueError("cfg 必须是非负有限数值")
    seed = config.seed if config.seed is not None else secrets.randbelow(2**63)
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("seed 必须是 0 到 2**63-1 的整数")
    label = config.filename_prefix or module_root.name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
        raise ValueError("filename_prefix 只使用技术标识、字母、数字、下划线或连字符")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:12]
    prefix = f"{label}_{run_id}"
    save_dir = date_output_dir(module_root)
    prompt["1"]["inputs"]["ckpt_name"] = config.checkpoint
    prompt["2"]["inputs"]["text"] = config.positive
    prompt["3"]["inputs"]["text"] = config.negative
    prompt["4"]["inputs"].update(width=config.width, height=config.height, batch_size=1)
    prompt["5"]["inputs"].update(seed=seed, steps=config.steps, cfg=config.cfg,
                                     sampler_name=config.sampler, scheduler=config.scheduler)
    prompt["7"]["inputs"].update(output_path=save_dir.as_posix(), filename_prefix=prefix,
                                     overwrite_mode="prefix_as_filename", extension="png")
    return {"prompt": prompt, "seed": seed, "run_id": run_id,
            "filename_prefix": prefix, "expected_output_path": str(save_dir / f"{prefix}.png")}
