"""Tests generated for the pixel-limit configuration change; no real service."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from harnessui.client import HarnessError
from harnessui.core import submit
from harnessui.image_limits import check_image_pixels, require_pixel_limit
from templates.workflow_module import api as module_api

ROOT = Path(__file__).resolve().parents[1]


class PixelLimitChecks(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "workflows/basic-t2i", self.root / "workflows/basic-t2i")
        self.module = self.root / "my_module"
        shutil.copytree(ROOT / "templates/workflow_module", self.module,
                        ignore=shutil.ignore_patterns("__pycache__", "output", "runs"))
        self.module_config = json.loads((self.module / "config.example.json").read_text(encoding="utf-8"))
        self.env_path = self.root / "environment.json"
        self.task = {"workflow": "basic-t2i", "parameters": {"checkpoint": "demo", "positive": "teapot", "seed": 42}}
        self.registry = {"resources": [{"id": "demo", "kind": "checkpoint", "family": "sdxl", "filename": "demo.safetensors"}]}
        self.client = SimpleNamespace(base_url="http://127.0.0.1:9", client_id="fake",
                                      queue_prompt=Mock(return_value="mock-prompt"),
                                      json=Mock(return_value={"prompt_id": "mock-prompt"}))

    def tearDown(self):
        self.temp.cleanup()

    def environment(self, limit):
        env = {"base_url": "http://127.0.0.1:9", "limits": {"max_image_pixels": limit}}
        self.env_path.write_text(json.dumps(env), encoding="utf-8")
        return env

    def test_unset_and_invalid_values(self):
        for env in ({}, {"limits": {}}, {"limits": {"max_image_pixels": None}}):
            with self.subTest(env=env), self.assertRaisesRegex(ValueError, "提醒用户"):
                require_pixel_limit(env)
        for value in (0, -1, True, "1000000", 100.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "正整数"):
                require_pixel_limit(self.environment(value))

    def test_exact_boundary_and_over_limit(self):
        env = self.environment(512 * 512)
        self.assertEqual(check_image_pixels(env, 512, 512)["pixels"], 512 * 512)
        with self.assertRaisesRegex(ValueError, "超过已配置上限"):
            check_image_pixels(env, 512, 520)

    def test_module_blocks_unset_or_excess_before_network_or_job_creation(self):
        for value in (None, 100):
            self.environment(value)
            with self.subTest(value=value), patch.object(module_api, "ComfyUIClient") as transport:
                with self.assertRaises(ValueError):
                    module_api.run_module(self.module_config, module_root=self.module, environment_path=self.env_path)
                transport.assert_not_called()
                self.assertFalse((self.module / "output").exists())

    def test_module_records_confirmed_limit(self):
        self.environment(512 * 512)
        with patch.object(module_api, "ComfyUIClient") as factory:
            client = factory.return_value
            client.client_id = "fake"
            client.queue_prompt.return_value = {"prompt_id": "mock-prompt"}
            result = module_api.run_module(self.module_config, module_root=self.module, environment_path=self.env_path)
            self.assertEqual(result["status"], "submitted")
            self.assertEqual(result["pixel_limit_check"]["max_image_pixels"], 512 * 512)
            client.queue_prompt.assert_called_once()

    def test_shared_runner_blocks_unset_or_excess_before_network(self):
        for value in (None, 100):
            with self.subTest(value=value), patch("harnessui.core.inspect_service") as inspection:
                with self.assertRaises(HarnessError):
                    submit(self.root, self.task, self.registry, self.client, environment=self.environment(value))
                inspection.assert_not_called()
                self.client.queue_prompt.assert_not_called()
                self.client.json.assert_not_called()
                self.assertFalse((self.root / "runs").exists())

    def test_shared_runner_uses_explicit_environment_and_records_limit(self):
        config_dir = self.root / "config"
        config_dir.mkdir()
        (config_dir / "environment.local.json").write_text(json.dumps(self.environment(1)), encoding="utf-8")
        with patch("harnessui.core.inspect_service", return_value={"dependency_check": "passed", "dependency_errors": []}):
            result = submit(self.root, self.task, self.registry, self.client, environment=self.environment(512 * 512))
        self.assertEqual(result["execution_status"], "submitted")
        self.assertEqual(result["pixel_limit_checks"][0]["max_image_pixels"], 512 * 512)

    def test_dry_run_remains_offline_and_reports_unchecked_budget(self):
        with patch.object(module_api, "ComfyUIClient") as transport:
            result = module_api.run_module(self.module_config, module_root=self.module, dry_run=True)
            transport.assert_not_called()
        self.assertFalse(result["pixel_limit_checked"])
        self.assertFalse((self.module / "output").exists())


if __name__ == "__main__":
    unittest.main()
