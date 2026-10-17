"""Per-module async template tests, using the existing isolated HTTP mock."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from templates.workflow_module.api import run_module
from test_harness import MockServer, image_bytes

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/workflow_module"


class ModuleTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="模块 空格 ", dir=ROOT / "tmp")
        self.module = Path(self.temp.name) / "my_module"
        shutil.copytree(TEMPLATE, self.module, ignore=shutil.ignore_patterns("__pycache__", "output", "runs"))
        self.config = json.loads((self.module / "config.example.json").read_text(encoding="utf-8"))
        self.config["checkpoint"] = "models/demo.safetensors"
        self.mock = MockServer()
        fields = ["output_path", "filename_prefix", "filename_delimiter", "filename_number_padding",
                  "filename_number_start", "extension", "dpi", "quality", "optimize_image", "lossless_webp",
                  "overwrite_mode", "show_history", "show_history_by_prefix", "embed_workflow", "show_previews", "images"]
        self.mock.info["Image Save"] = {"input": {"required": {name: ["STRING"] for name in fields}},
                                       "output": [], "output_node": True}
        self.env = Path(self.temp.name) / "environment.local.json"
        self.env.write_text(json.dumps({"base_url": self.mock.client.base_url, "limits": {"max_image_pixels": 1_000_000}}), encoding="utf-8")

    def tearDown(self):
        self.mock.close()
        self.temp.cleanup()

    def submit(self):
        return run_module(self.config, module_root=self.module, environment_path=self.env)

    def test_dry_run_has_no_network_or_output_directory(self):
        result = run_module(self.config, module_root=self.module, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["submitted"])
        self.assertEqual(result["prompt"]["7"]["class_type"], "Image Save")
        self.assertFalse((self.module / "output").exists())
        self.assertFalse(self.mock.posts)

    def test_submit_returns_before_image_exists_and_plans_direct_output(self):
        result = self.submit()
        self.assertEqual(result["status"], "submitted", result)
        self.assertTrue(result["prompt_id"])
        expected = Path(result["expected_output_path"])
        self.assertEqual(expected.parent.parent, self.module / "output")
        self.assertFalse(expected.exists())
        self.assertFalse(self.mock.views)
        self.assertFalse(self.mock.history)
        prompt = self.mock.posts[0]["prompt"]
        self.assertEqual(prompt["7"]["inputs"]["output_path"], expected.parent.as_posix())
        self.assertEqual(prompt["7"]["inputs"]["overwrite_mode"], "prefix_as_filename")
        self.assertEqual(expected.name, prompt["7"]["inputs"]["filename_prefix"] + ".png")
        self.assertEqual(prompt["1"]["inputs"]["ckpt_name"], "models\\demo.safetensors")
        jobs = Path(result["manifest_path"]).parent
        self.assertEqual(jobs.parent, self.module / "output/jobs")
        self.assertEqual(json.loads((jobs / "prompt.json").read_text(encoding="utf-8")), prompt)

    def test_two_submissions_have_distinct_paths_and_keep_records(self):
        one, two = self.submit(), self.submit()
        self.assertNotEqual(one["expected_output_path"], two["expected_output_path"])
        self.assertNotEqual(one["manifest_path"], two["manifest_path"])
        self.assertTrue(Path(one["manifest_path"]).is_file())
        self.assertEqual(one["seed"], two["seed"])

    def test_missing_custom_save_node_blocks_submission(self):
        del self.mock.info["Image Save"]
        result = self.submit()
        self.assertEqual(result["status"], "submit_failed")
        self.assertIn("Image Save", result["error"])
        self.assertFalse(self.mock.posts)

    def test_black_recent_output_blocks_submission(self):
        recent = self.module / "output/20260101/old.png"
        recent.parent.mkdir(parents=True)
        recent.write_bytes(image_bytes("black"))
        result = self.submit()
        self.assertEqual(result["status"], "submit_failed")
        self.assertIn("纯黑", result["error"])
        self.assertFalse(self.mock.posts)
        self.assertTrue(recent.exists())

    def test_server_rejection_and_unknown_do_not_auto_retry(self):
        for mode, expected in (("reject", "submit_failed"), ("unknown", "submission_unknown")):
            self.mock.mode = mode
            before = len(self.mock.posts)
            result = self.submit()
            self.assertEqual(result["status"], expected)
            self.assertEqual(len(self.mock.posts), before + 1)

    def test_module_cli_works_after_copy_without_shared_runner(self):
        result = subprocess.run([sys.executable, "run.py", "--config", "config.example.json", "--dry-run"],
                                cwd=self.module, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertTrue(json.loads(result.stdout.decode("utf-8"))["dry_run"])
        self.assertFalse((self.module / "output").exists())


if __name__ == "__main__":
    unittest.main()
