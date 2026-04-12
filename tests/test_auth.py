"""Tests for Viewfinder API auth, usage metering, and custom prompts."""

import pytest

from viewfinder.storage import Storage


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_auth.db"
    s = Storage(db_path=db_path)
    yield s
    s.close()


class TestApiKeys:
    def test_create_key(self, store):
        key = store.create_api_key("test-app")
        assert key.startswith("vf-")
        assert len(key) == 51  # "vf-" + 48 hex chars

    def test_get_key(self, store):
        key = store.create_api_key("test-app", is_admin=True, rate_limit_rpm=60)
        record = store.get_api_key(key)
        assert record is not None
        assert record["name"] == "test-app"
        assert record["is_admin"] == 1
        assert record["rate_limit_rpm"] == 60

    def test_get_missing_key(self, store):
        assert store.get_api_key("vf-nonexistent") is None

    def test_list_keys(self, store):
        store.create_api_key("app-1")
        store.create_api_key("app-2")
        keys = store.list_api_keys()
        assert len(keys) == 2

    def test_delete_key(self, store):
        key = store.create_api_key("temp")
        assert store.delete_api_key(key)
        assert store.get_api_key(key) is None

    def test_delete_missing_key(self, store):
        assert not store.delete_api_key("vf-nonexistent")


class TestUsageLog:
    def test_log_and_get(self, store):
        key = store.create_api_key("test-app")
        store.log_usage(key, "/api/ingest", video_id="vid123", input_tokens=100, output_tokens=50)
        usage = store.get_usage(key)
        assert usage["total_requests"] == 1
        assert usage["total_input_tokens"] == 100
        assert usage["total_output_tokens"] == 50
        assert usage["unique_videos"] == 1

    def test_multiple_requests(self, store):
        key = store.create_api_key("test-app")
        store.log_usage(key, "/api/ingest", video_id="vid1", input_tokens=100, output_tokens=50)
        store.log_usage(key, "/api/ingest", video_id="vid2", input_tokens=200, output_tokens=100)
        usage = store.get_usage(key)
        assert usage["total_requests"] == 2
        assert usage["total_input_tokens"] == 300
        assert usage["unique_videos"] == 2

    def test_rate_limit_count(self, store):
        key = store.create_api_key("test-app")
        store.log_usage(key, "/api/ingest")
        store.log_usage(key, "/api/ingest")
        count = store.get_request_count_last_minute(key)
        assert count == 2


class TestCustomPrompts:
    def test_save_and_get(self, store):
        key = store.create_api_key("test-app")
        store.save_custom_prompt(key, "my-prompt", "Summarize: {transcript}")
        template = store.get_custom_prompt(key, "my-prompt")
        assert template == "Summarize: {transcript}"

    def test_get_missing(self, store):
        key = store.create_api_key("test-app")
        assert store.get_custom_prompt(key, "nonexistent") is None

    def test_list_prompts(self, store):
        key = store.create_api_key("test-app")
        store.save_custom_prompt(key, "prompt-1", "Template 1: {transcript}")
        store.save_custom_prompt(key, "prompt-2", "Template 2: {transcript}")
        prompts = store.list_custom_prompts(key)
        assert len(prompts) == 2
        names = [p["name"] for p in prompts]
        assert "prompt-1" in names
        assert "prompt-2" in names

    def test_upsert(self, store):
        key = store.create_api_key("test-app")
        store.save_custom_prompt(key, "my-prompt", "Version 1")
        store.save_custom_prompt(key, "my-prompt", "Version 2")
        assert store.get_custom_prompt(key, "my-prompt") == "Version 2"

    def test_delete(self, store):
        key = store.create_api_key("test-app")
        store.save_custom_prompt(key, "my-prompt", "Template")
        assert store.delete_custom_prompt(key, "my-prompt")
        assert store.get_custom_prompt(key, "my-prompt") is None

    def test_delete_missing(self, store):
        key = store.create_api_key("test-app")
        assert not store.delete_custom_prompt(key, "nonexistent")

    def test_per_key_isolation(self, store):
        key1 = store.create_api_key("app-1")
        key2 = store.create_api_key("app-2")
        store.save_custom_prompt(key1, "shared-name", "Template for app-1")
        store.save_custom_prompt(key2, "shared-name", "Template for app-2")
        assert store.get_custom_prompt(key1, "shared-name") == "Template for app-1"
        assert store.get_custom_prompt(key2, "shared-name") == "Template for app-2"
