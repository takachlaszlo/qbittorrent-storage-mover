import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "qbit-move-completed.py"


def load_module():
    os.environ.update(
        {
            "QB_URL": "http://127.0.0.1:8080",
            "QB_USERNAME": "test",
            "QB_PASSWORD": "test",
            "SOURCE_PATH": "/source",
            "TARGET_PATH": "/target",
            "DRY_RUN": "0",
            "INCLUDE_TAGS": "",
        }
    )
    spec = importlib.util.spec_from_file_location("qbit_mover", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BatchMoveTest(unittest.TestCase):
    def test_all_eligible_hashes_are_sent_in_one_request(self):
        module = load_module()
        now = int(time.time())
        torrents = [
            {
                "hash": "a1",
                "name": "one",
                "completion_on": now - 9000,
                "amount_left": 0,
                "save_path": "/source",
                "content_path": "/source/one",
                "state": "uploading",
                "size": 100,
                "tags": "music,archive",
            },
            {
                "hash": "b2",
                "name": "two",
                "completion_on": now - 8000,
                "amount_left": 0,
                "save_path": "/source",
                "content_path": "/source/two",
                "state": "stalledUP",
                "size": 200,
                "tags": "linux",
            },
        ]

        class FakeClient:
            posts = []

            def __init__(self, base_url):
                self.base_url = base_url

            def authenticate(self):
                return None

            def request(self, endpoint, data=None):
                if endpoint == "/api/v2/torrents/info?filter=completed":
                    return json.dumps(torrents).encode()
                if endpoint == "/api/v2/torrents/setLocation":
                    self.posts.append(data)
                    return b""
                raise AssertionError(endpoint)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            module.QBClient = FakeClient
            module.validate_paths = lambda: None
            module.TARGET_PATH = target
            module.MIN_FREE_BYTES = 0
            module.DRY_RUN = False

            with patch.object(
                module.shutil,
                "disk_usage",
                return_value=shutil._ntuple_diskusage(10**12, 0, 10**12),
            ):
                self.assertEqual(module.main(), 0)

        self.assertEqual(
            FakeClient.posts,
            [{"hashes": "a1|b2", "location": str(target)}],
        )

    def test_any_configured_tag_is_enough(self):
        module = load_module()
        module.INCLUDE_TAGS = {"music", "linux"}
        now = int(time.time())
        torrents = [
            {
                "hash": "yes",
                "name": "matching",
                "completion_on": now - 9000,
                "amount_left": 0,
                "save_path": "/source",
                "content_path": "/source/matching",
                "state": "uploading",
                "size": 100,
                "tags": "music,other",
            },
            {
                "hash": "no",
                "name": "not-matching",
                "completion_on": now - 9000,
                "amount_left": 0,
                "save_path": "/source",
                "content_path": "/source/not-matching",
                "state": "uploading",
                "size": 100,
                "tags": "movies",
            },
        ]

        class FakeClient:
            posts = []

            def __init__(self, base_url):
                self.base_url = base_url

            def authenticate(self):
                return None

            def request(self, endpoint, data=None):
                if endpoint == "/api/v2/torrents/info?filter=completed":
                    return json.dumps(torrents).encode()
                if endpoint == "/api/v2/torrents/setLocation":
                    self.posts.append(data)
                    return b""
                raise AssertionError(endpoint)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            module.QBClient = FakeClient
            module.validate_paths = lambda: None
            module.TARGET_PATH = target
            module.MIN_FREE_BYTES = 0
            module.DRY_RUN = False
            with patch.object(
                module.shutil,
                "disk_usage",
                return_value=shutil._ntuple_diskusage(10**12, 0, 10**12),
            ):
                self.assertEqual(module.main(), 0)

        self.assertEqual(
            FakeClient.posts,
            [{"hashes": "yes", "location": str(target)}],
        )

    def test_emergency_moves_incomplete_torrents_and_ignores_filters(self):
        module = load_module()
        module.INCLUDE_TAGS = {"required-tag"}
        torrents = [
            {
                "hash": "downloading",
                "name": "active-download",
                "added_on": 100,
                "completion_on": 0,
                "amount_left": 900,
                "save_path": "/source",
                "content_path": "/source/active-download",
                "state": "downloading",
                "size": 1000,
                "tags": "",
            },
            {
                "hash": "paused",
                "name": "paused-download",
                "added_on": 200,
                "completion_on": 0,
                "amount_left": 500,
                "save_path": "/source/category",
                "content_path": "/source/category/paused-download",
                "state": "pausedDL",
                "size": 800,
                "tags": "different-tag",
            },
            {
                "hash": "already-moving",
                "name": "already-moving",
                "added_on": 300,
                "completion_on": 0,
                "amount_left": 100,
                "save_path": "/source",
                "content_path": "/source/already-moving",
                "state": "moving",
                "size": 100,
                "tags": "",
            },
            {
                "hash": "metadata",
                "name": "fetching-metadata",
                "added_on": 350,
                "completion_on": 0,
                "amount_left": 0,
                "save_path": "/source",
                "content_path": "",
                "state": "metaDL",
                "size": -1,
                "tags": "",
            },
            {
                "hash": "elsewhere",
                "name": "elsewhere",
                "added_on": 400,
                "completion_on": 0,
                "amount_left": 100,
                "save_path": "/other",
                "content_path": "/other/elsewhere",
                "state": "downloading",
                "size": 100,
                "tags": "",
            },
        ]

        class FakeClient:
            posts = []

            def __init__(self, base_url):
                self.base_url = base_url

            def authenticate(self):
                return None

            def request(self, endpoint, data=None):
                if endpoint == "/api/v2/torrents/info":
                    return json.dumps(torrents).encode()
                if endpoint == "/api/v2/torrents/setLocation":
                    self.posts.append(data)
                    return b""
                raise AssertionError(endpoint)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory).resolve()
            module.QBClient = FakeClient
            module.validate_paths = lambda: None
            module.TARGET_PATH = target
            module.MIN_FREE_BYTES = 0
            module.DRY_RUN = True

            with patch.object(
                module.shutil,
                "disk_usage",
                return_value=shutil._ntuple_diskusage(10**12, 0, 10**12),
            ):
                self.assertEqual(module.main(emergency=True), 0)

        self.assertEqual(
            FakeClient.posts,
            [
                {
                    "hashes": "downloading|paused|metadata",
                    "location": str(target),
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
