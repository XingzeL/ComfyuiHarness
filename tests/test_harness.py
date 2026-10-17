"""Offline contracts against a local mock server; never connects to ComfyUI."""
from __future__ import annotations

import copy
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from harnessui.client import Client, HarnessError
from harnessui.core import (build, check_dependencies, collect, inspect_service, read_json,
                            status, submit, validate_graph, write_json)

PACKAGE = Path(__file__).resolve().parents[1]


def node(required, output, output_node=False):
    return {"input": {"required": required}, "output": output, "output_node": output_node}


def schemas():
    return {
        "CheckpointLoaderSimple": node({"ckpt_name": [["models\\demo.safetensors"]]}, ["MODEL", "CLIP", "VAE"]),
        "CLIPTextEncode": node({"text": ["STRING"], "clip": ["CLIP"]}, ["CONDITIONING"]),
        "EmptyLatentImage": node({"width": ["INT", {"min": 16}], "height": ["INT", {"min": 16}], "batch_size": ["INT"]}, ["LATENT"]),
        "KSampler": node({"model": ["MODEL"], "positive": ["CONDITIONING"], "negative": ["CONDITIONING"],
                          "latent_image": ["LATENT"], "seed": ["INT"], "steps": ["INT"], "cfg": ["FLOAT"],
                          "sampler_name": [["euler"]], "scheduler": [["normal"]], "denoise": ["FLOAT"]}, ["LATENT"]),
        "VAEDecode": node({"samples": ["LATENT"], "vae": ["VAE"]}, ["IMAGE"]),
        "SaveImage": node({"images": ["IMAGE"], "filename_prefix": ["STRING"]}, [], True),
        "LoraLoader": node({"model": ["MODEL"], "clip": ["CLIP"], "lora_name": [["styles/demo.safetensors"]],
                            "strength_model": ["FLOAT"], "strength_clip": ["FLOAT"]}, ["MODEL", "CLIP"]),
        "LoadImage": node({"image": [[]]}, ["IMAGE", "MASK"]),
    }


def image_bytes(color="white"):
    buffer = io.BytesIO()
    Image.new("RGB", (16, 24), color).save(buffer, "PNG")
    return buffer.getvalue()


class MockServer:
    def __init__(self):
        self.info = schemas()
        self.history = {}
        self.queue = {"queue_pending": [], "queue_running": []}
        self.posts = []
        self.uploads = []
        self.views = 0
        self.png = image_bytes()
        self.mode = "normal"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, code, data, binary=False):
                self.send_response(code)
                self.send_header("Content-Type", "image/png" if binary else "application/json")
                self.end_headers()
                self.wfile.write(data if binary else json.dumps(data).encode())

            def do_GET(self):
                if self.path == "/system_stats":
                    self.send(200, {"system": {"comfyui_version": "mock"}})
                elif self.path == "/object_info":
                    self.send(200, owner.info)
                elif self.path.startswith("/history/"):
                    key = self.path.rsplit("/", 1)[1]
                    self.send(200, {key: owner.history[key]} if key in owner.history else {})
                elif self.path == "/queue":
                    self.send(200, owner.queue)
                elif self.path.startswith("/view?"):
                    owner.views += 1
                    self.send(200, owner.png, True)
                else:
                    self.send(404, {})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if self.path == "/upload/image":
                    owner.uploads.append(raw)
                    self.send(200, {"name": "server_name.png", "subfolder": "uploaded", "type": "input"})
                    return
                if self.path != "/prompt":
                    self.send(404, {})
                    return
                body = json.loads(raw)
                owner.posts.append(body)
                if owner.mode == "reject":
                    self.send(400, {"error": "invalid prompt"})
                elif owner.mode == "unknown":
                    self.send(503, {"error": "response lost after acceptance"})
                elif owner.mode == "no-id":
                    self.send(200, {"number": 1})
                else:
                    prompt_id = f"mock-{len(owner.posts)}"
                    owner.queue["queue_pending"].append([0, prompt_id, body["prompt"], {"client_id": body["client_id"]}, []])
                    self.send(200, {"prompt_id": prompt_id, "node_errors": {}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(f"http://127.0.0.1:{self.server.server_port}", timeout=2)

    def complete(self, prompt_id, refs=None):
        self.queue = {"queue_pending": [], "queue_running": []}
        self.history[prompt_id] = {
            "status": {"completed": True, "status_str": "success", "messages": []},
            "outputs": {"7": {"images": refs if refs is not None else [
                {"filename": "actual_00042_.png", "subfolder": "elsewhere", "type": "output"}]}},
        }

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.client.session.close()


class HarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (PACKAGE / "tmp").mkdir(exist_ok=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="测试 空格 ", dir=PACKAGE / "tmp")
        self.root = Path(self.temp.name).resolve()
        shutil.copytree(PACKAGE / "workflows", self.root / "workflows")
        write_json(self.root / "config/environment.local.json", {"limits": {"max_image_pixels": 1_000_000}})
        self.registry = {"resources": [
            {"id": "model", "kind": "checkpoint", "family": "sdxl", "filename": "models/demo.safetensors"},
            {"id": "style", "kind": "lora", "family": "sdxl", "filename": "styles/demo.safetensors"},
        ]}
        self.task = {"workflow": "basic-t2i", "parameters": {"checkpoint": "model", "positive": "a teapot", "seed": 42}}
        self.mock = MockServer()

    def tearDown(self):
        self.mock.close()
        self.temp.cleanup()

    def submit(self):
        result = submit(self.root, self.task, self.registry, self.mock.client)
        self.assertEqual(result["execution_status"], "submitted", result)
        return result

    def spec(self):
        return self.root / "workflows/basic-t2i/workflow.spec.json"

    def graph(self):
        return self.root / "workflows/basic-t2i/workflow.json"

    def test_build_has_no_writes_and_does_not_mutate_template(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = build(self.root, self.task, self.registry)
        self.assertEqual(result["prompt"]["5"]["inputs"]["seed"], 42)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.mock.posts, [])

    def test_seed_is_recorded_and_retry_is_new_run(self):
        self.task["parameters"].pop("seed")
        one = self.submit()
        saved = read_json(self.root / f"runs/{one['run_id']}/task.json")
        self.assertEqual(one["parameters"]["seed"], saved["parameters"]["seed"])
        two = submit(self.root, saved, self.registry, self.mock.client, retry_of=one["run_id"])
        self.assertNotEqual(one["run_id"], two["run_id"])
        self.assertEqual(one["parameters"]["seed"], two["parameters"]["seed"])
        self.assertEqual(two["retry_of"], one["run_id"])
        self.assertNotEqual(self.mock.posts[0]["prompt"]["7"], self.mock.posts[1]["prompt"]["7"])

    def test_resource_family_mismatch_is_rejected(self):
        self.registry["resources"][0]["family"] = "anima"
        with self.assertRaisesRegex(HarnessError, "不兼容"):
            build(self.root, self.task, self.registry)

    def test_unknown_param_and_duplicate_resource_are_rejected(self):
        self.task["parameters"]["typo"] = 1
        with self.assertRaisesRegex(HarnessError, "未知参数"):
            build(self.root, self.task, self.registry)
        self.task["parameters"].pop("typo")
        self.registry["resources"].append(self.registry["resources"][0])
        with self.assertRaisesRegex(HarnessError, "重复"):
            build(self.root, self.task, self.registry)

    def test_lora_strengths_and_chain(self):
        self.task["workflow"] = "basic-t2i-lora"
        self.task["parameters"].update(lora="style", lora_model_strength=0.8, lora_clip_strength=0)
        result = build(self.root, self.task, self.registry)
        self.assertEqual(check_dependencies(result, schemas()), [])
        self.assertEqual(result["prompt"]["8"]["inputs"]["strength_clip"], 0)
        self.assertEqual(result["prompt"]["5"]["inputs"]["model"], ["8", 0])
        self.registry["resources"][1]["family"] = "sd15"
        with self.assertRaisesRegex(HarnessError, "不兼容"):
            build(self.root, self.task, self.registry)

    def test_node_renumbering_works_with_mapping_update(self):
        graph = read_json(self.graph())
        graph["model-new"] = graph.pop("1")
        for item in graph.values():
            for name, value in item["inputs"].items():
                if isinstance(value, list) and value[0] == "1":
                    item["inputs"][name] = ["model-new", value[1]]
        write_json(self.graph(), graph)
        with self.assertRaisesRegex(HarnessError, "类型不匹配"):
            build(self.root, self.task, self.registry)
        spec = read_json(self.spec())
        spec["parameters"]["checkpoint"]["targets"][0]["node"] = "model-new"
        write_json(self.spec(), spec)
        self.assertEqual(check_dependencies(build(self.root, self.task, self.registry), schemas()), [])

    def test_missing_node_model_or_invalid_link_blocks_post(self):
        del self.mock.info["KSampler"]
        result = submit(self.root, self.task, self.registry, self.mock.client)
        self.assertEqual(result["execution_status"], "submit_failed")
        self.assertEqual(self.mock.posts, [])
        self.mock.info = schemas()
        self.mock.info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[]]
        result = submit(self.root, self.task, self.registry, self.mock.client)
        self.assertIn("不可用", result["error"])
        self.assertEqual(self.mock.posts, [])
        built = build(self.root, self.task, self.registry)
        built["prompt"]["5"]["inputs"]["model"] = ["1", 1]
        self.assertTrue(any("连接类型" in e for e in check_dependencies(built, schemas())))

    def test_graph_rejects_ui_cycles_and_broken_links(self):
        with self.assertRaises(HarnessError):
            validate_graph({"nodes": []})
        for value in (["missing", 0], ["1", -1], ["1", 0]):
            with self.assertRaises(HarnessError):
                validate_graph({"1": {"class_type": "A", "inputs": {"a": value}}})

    def test_enum_path_uses_server_spelling(self):
        result = self.submit()
        self.assertEqual(self.mock.posts[0]["prompt"]["1"]["inputs"]["ckpt_name"], "models\\demo.safetensors")
        saved = read_json(self.root / f"runs/{result['run_id']}/prompt.json")
        self.assertEqual(saved, self.mock.posts[0]["prompt"])

    def test_inspect_lists_models_without_submitting(self):
        result = inspect_service(self.mock.client)
        self.assertIn("CheckpointLoaderSimple.ckpt_name", result["discoverable_models"])
        self.assertEqual(result["dependency_check"], "not_requested")
        self.assertFalse(self.mock.posts)

    def test_http_rejection_and_uncertain_submission_not_retried(self):
        for mode, expected in (("reject", "submit_failed"), ("unknown", "submission_unknown"), ("no-id", "submission_unknown")):
            self.mock.mode = mode
            count = len(self.mock.posts)
            result = submit(self.root, self.task, self.registry, self.mock.client)
            self.assertEqual(result["execution_status"], expected)
            self.assertEqual(len(self.mock.posts), count + 1)
            self.assertTrue((self.root / f"runs/{result['run_id']}/prompt.json").is_file())

    def test_parameter_ranges_types_and_random_seed_range(self):
        for name, value in (("steps", 0), ("width", True), ("cfg", float("nan"))):
            task = copy.deepcopy(self.task)
            task["parameters"][name] = value
            with self.assertRaises(HarnessError):
                build(self.root, task, self.registry)
        spec = read_json(self.spec())
        spec["parameters"]["seed"].update(min=3, max=3)
        write_json(self.spec(), spec)
        self.task["parameters"].pop("seed")
        self.assertEqual(build(self.root, self.task, self.registry)["parameters"]["seed"], 3)

    def test_missing_field_wrong_class_and_duplicate_mapping(self):
        original = read_json(self.spec())
        for field, value in (("input", "missing"), ("class_type", "UnknownLoader")):
            spec = copy.deepcopy(original)
            spec["parameters"]["checkpoint"]["targets"][0][field] = value
            write_json(self.spec(), spec)
            with self.assertRaises(HarnessError):
                build(self.root, self.task, self.registry)
        spec = copy.deepcopy(original)
        spec["parameters"]["negative"]["targets"] = spec["parameters"]["positive"]["targets"]
        write_json(self.spec(), spec)
        with self.assertRaisesRegex(HarnessError, "重复映射"):
            build(self.root, self.task, self.registry)

    def test_partial_multiple_outputs_are_not_verified(self):
        graph = read_json(self.graph())
        graph["9"] = copy.deepcopy(graph["7"])
        write_json(self.graph(), graph)
        spec = read_json(self.spec())
        spec["outputs"].append("9")
        write_json(self.spec(), spec)
        run = self.submit()
        self.mock.complete(run["prompt_id"])
        partial = collect(self.root, run["run_id"])
        self.assertEqual(partial["collection_status"], "validation_failed")
        self.assertEqual(len(partial["files"]), 1)
        self.mock.history[run["prompt_id"]]["outputs"]["9"] = copy.deepcopy(self.mock.history[run["prompt_id"]]["outputs"]["7"])
        complete = collect(self.root, run["run_id"])
        self.assertEqual(complete["collection_status"], "verified")
        self.assertEqual(len(complete["files"]), 2)

    def test_undeclared_output_and_special_save_need_adaptation(self):
        graph = read_json(self.graph())
        graph["9"] = copy.deepcopy(graph["7"])
        write_json(self.graph(), graph)
        with self.assertRaisesRegex(HarnessError, "全部"):
            build(self.root, self.task, self.registry)
        graph.pop("9")
        graph["6"]["class_type"] = "CustomDecoderWithSave"
        write_json(self.graph(), graph)
        info = schemas()
        info["CustomDecoderWithSave"] = node({"samples": ["LATENT"], "vae": ["VAE"]}, ["IMAGE"], True)
        errors = check_dependencies(build(self.root, self.task, self.registry), info)
        self.assertTrue(any("专用收集适配" in error for error in errors))

    def test_service_unreachable_is_recorded(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        port = server.server_port
        server.server_close()
        result = submit(self.root, self.task, self.registry, Client(f"http://127.0.0.1:{port}", 0.2))
        self.assertEqual(result["execution_status"], "submit_failed")
        self.assertFalse(self.mock.posts)

    def test_queued_running_unknown_and_failed_statuses(self):
        run = self.submit()
        self.assertEqual(status(self.root, run["run_id"])["execution_status"], "queued")
        self.mock.queue["queue_running"] = self.mock.queue.pop("queue_pending")
        self.assertEqual(status(self.root, run["run_id"])["execution_status"], "running")
        self.mock.queue = {}
        self.assertEqual(status(self.root, run["run_id"])["execution_status"], "unknown")
        self.mock.history[run["prompt_id"]] = {"status": {"completed": False, "status_str": "error", "messages": []}}
        self.assertEqual(status(self.root, run["run_id"])["execution_status"], "failed")
        with self.assertRaisesRegex(HarnessError, "尚未成功"):
            collect(self.root, run["run_id"])

    def test_collect_waits_for_success(self):
        run = self.submit()
        with self.assertRaisesRegex(HarnessError, "尚未成功"):
            collect(self.root, run["run_id"])
        self.assertFalse((self.root / "outputs").exists())

    def test_history_outputs_and_idempotent_collection(self):
        run = self.submit()
        self.mock.complete(run["prompt_id"])
        one = collect(self.root, run["run_id"])
        self.assertEqual(one["collection_status"], "verified")
        self.assertEqual(one["files"][0]["source"]["filename"], "actual_00042_.png")
        file = self.root / one["files"][0]["path"]
        before = file.stat().st_mtime_ns
        two = collect(self.root, run["run_id"])
        self.assertEqual(two["files"], one["files"])
        self.assertEqual(file.stat().st_mtime_ns, before)
        self.assertEqual(self.mock.views, 1)
        for name in ("task.json", "prompt.json", "manifest.json", "workflow.spec.json", "history.json"):
            self.assertTrue((self.root / f"runs/{run['run_id']}" / name).exists())

    def test_history_cleared_after_collection_uses_snapshot(self):
        run = self.submit()
        self.mock.complete(run["prompt_id"])
        collect(self.root, run["run_id"])
        self.mock.history.clear()
        result = collect(self.root, run["run_id"])
        self.assertEqual(result["collection_status"], "verified")
        self.assertEqual(self.mock.views, 1)

    def test_missing_output_is_not_verified(self):
        run = self.submit()
        self.mock.complete(run["prompt_id"], refs=[])
        result = collect(self.root, run["run_id"])
        self.assertEqual(result["execution_status"], "succeeded")
        self.assertEqual(result["collection_status"], "validation_failed")

    def test_corrupt_black_and_altered_files_are_not_verified(self):
        for data in (b"not an image", image_bytes("black")):
            run = self.submit()
            self.mock.complete(run["prompt_id"])
            self.mock.png = data
            result = collect(self.root, run["run_id"])
            self.assertEqual(result["collection_status"], "validation_failed")
            self.assertTrue(result["files"])
        self.mock.png = image_bytes()
        run = self.submit()
        self.mock.complete(run["prompt_id"])
        result = collect(self.root, run["run_id"])
        target = self.root / result["files"][0]["path"]
        target.write_bytes(b"user edit")
        result = collect(self.root, run["run_id"])
        self.assertEqual(result["collection_status"], "validation_failed")
        self.assertEqual(target.read_bytes(), b"user edit")

    def test_paths_and_server_output_traversal_are_rejected(self):
        self.task["workflow"] = "../outside"
        with self.assertRaises(HarnessError):
            build(self.root, self.task, self.registry)
        self.task["workflow"] = "basic-t2i"
        run = self.submit()
        self.mock.complete(run["prompt_id"], [{"filename": "../escape.png", "subfolder": "", "type": "output"}])
        result = collect(self.root, run["run_id"])
        self.assertEqual(result["collection_status"], "validation_failed")
        self.assertEqual(self.mock.views, 0)

    def test_image_is_snapshotted_uploaded_and_references_server_name(self):
        source = self.root / "inputs/测试 image.png"
        source.parent.mkdir()
        source.write_bytes(image_bytes())
        graph = {"6": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}},
                 "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "demo"}}}
        spec = {"id": "basic-t2i", "family": "sdxl", "template": "workflow.json", "outputs": ["7"],
                "parameters": {"image": {"type": "string", "image": True, "targets": [
                    {"node": "6", "class_type": "LoadImage", "input": "image"}]}}}
        write_json(self.graph(), graph)
        write_json(self.spec(), spec)
        self.task = {"workflow": "basic-t2i", "parameters": {"image": "inputs/测试 image.png"}}
        run = self.submit()
        self.assertEqual(self.mock.posts[0]["prompt"]["6"]["inputs"]["image"], "uploaded/server_name.png")
        self.assertTrue((self.root / f"runs/{run['run_id']}/inputs/00.png").is_file())
        self.assertEqual(len(self.mock.uploads), 1)

    def test_package_can_move_and_cli_build_needs_no_service(self):
        moved = self.root / "独立 副本"
        shutil.copytree(PACKAGE, moved, ignore=shutil.ignore_patterns("tmp", "runs", "outputs", "__pycache__", "*.pyc"))
        result = subprocess.run([sys.executable, "-m", "harnessui", "--registry", "resources/registry.example.json",
                                 "build", "--task", "examples/task.basic.json"], cwd=moved, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["workflow_id"], "basic-t2i")
        self.assertFalse((moved / "runs").exists())
        self.assertFalse((moved / "config/environment.local.json").exists())

    def test_cli_outputs_utf8_and_nonzero_for_invalid_task(self):
        task = self.root / "bad.json"
        write_json(task, {"workflow": "basic-t2i", "parameters": {"checkpoint": "missing", "positive": "测试"}})
        result = subprocess.run([sys.executable, "-m", "harnessui", "--registry", "resources/registry.example.json",
                                 "build", "--task", str(task)], cwd=PACKAGE, capture_output=True)
        self.assertEqual(result.returncode, 1)
        error = json.loads(result.stdout.decode("utf-8"))["error"]
        self.assertIn("资源未登记", error)


if __name__ == "__main__":
    unittest.main()
