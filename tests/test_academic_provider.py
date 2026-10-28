import io
import json
import urllib.request
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from backend.config_manager import ConfigManager
from backend.ai_assistant import (
    fetch_academic_models,
    format_academic_messages,
    estimate_response_time_seconds,
    _extract_academic_error_message,
    AIAssistant
)


def test_format_academic_messages_system_merge():
    # Academic API strictly rejects 'system' role. It must be merged into user role.
    messages = [
        {"role": "system", "content": "You are a research assistant."},
        {"role": "user", "content": "What is the main finding?"},
        {"role": "assistant", "content": "The main finding is X."},
        {"role": "user", "content": "Explain further."}
    ]
    formatted = format_academic_messages(messages)
    assert len(formatted) == 3
    assert formatted[0]["role"] == "user"
    assert "You are a research assistant." in formatted[0]["content"]
    assert "What is the main finding?" in formatted[0]["content"]
    assert formatted[1]["role"] == "assistant"
    assert formatted[1]["content"] == "The main finding is X."
    assert formatted[2]["role"] == "user"
    assert formatted[2]["content"] == "Explain further."


def test_format_academic_messages_system_only():
    messages = [{"role": "system", "content": "System only context."}]
    formatted = format_academic_messages(messages)
    assert len(formatted) == 1
    assert formatted[0]["role"] == "user"
    assert formatted[0]["content"] == "System only context."


def test_fetch_academic_models_success(monkeypatch):
    mock_response = io.BytesIO(json.dumps({
        "success": True,
        "data": [
            {"modelName": "gpt-4o", "contextWindow": 128000},
            {"modelName": "gpt-5-mini", "contextWindow": 400000},
            {"modelName": "o3", "contextWindow": 200000}
        ]
    }).encode("utf-8"))

    class MockHTTPResponse:
        def __enter__(self):
            return mock_response
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, *args, **kwargs: MockHTTPResponse())

    models = fetch_academic_models("https://meduniwien-api.academic-ai.at", "client_123", "secret_abc")
    assert models == ["gpt-4o", "gpt-5-mini", "o3"]


def test_fetch_academic_models_missing_credentials():
    with pytest.raises(ValueError, match="Client ID and Client Secret are required"):
        fetch_academic_models("https://meduniwien-api.academic-ai.at", "", "secret_abc")

    with pytest.raises(ValueError, match="Client ID and Client Secret are required"):
        fetch_academic_models("https://meduniwien-api.academic-ai.at", "client_123", "")


def test_fetch_academic_models_http_error(monkeypatch):
    err_body = json.dumps({"message": "Invalid client secret"}).encode("utf-8")
    http_err = urllib.error.HTTPError("http://test", 401, "Unauthorized", {}, io.BytesIO(err_body))

    monkeypatch.setattr(urllib.request, "urlopen", MagicMock(side_effect=http_err))

    with pytest.raises(ValueError, match="Invalid client secret"):
        fetch_academic_models("https://meduniwien-api.academic-ai.at", "bad_client", "bad_secret")


def test_estimate_response_time_academic():
    est = estimate_response_time_seconds("academic", "gpt-4o", doc_tokens=1000, prompt_tokens=50)
    assert est == 2.5


def test_academic_ai_assistant_credentials(monkeypatch):
    import keyring
    creds = {"academic_client_id": "test_id_keyring", "academic_client_secret": "test_sec_keyring"}
    monkeypatch.setattr(keyring, "get_password", lambda svc, key: creds.get(key))

    assistant = AIAssistant()
    cid, sec = assistant._get_academic_credentials()
    assert cid == "test_id_keyring"
    assert sec == "test_sec_keyring"


def test_academic_ai_assistant_active_model(monkeypatch):
    monkeypatch.setattr(ConfigManager, "ai_provider", "academic")
    monkeypatch.setattr(ConfigManager, "academic_model_name", "gpt-5.5")

    assistant = AIAssistant()
    assert assistant.provider == "academic"
    assert assistant.get_active_model_name() == "gpt-5.5"
    assert assistant.rank_available_models() == [{"name": "gpt-5.5", "RPM": 9999, "RPD": 999999}]


def test_academic_call_api_and_ask(monkeypatch, tmp_path):
    monkeypatch.setattr(ConfigManager, "ai_provider", "academic")
    monkeypatch.setattr(ConfigManager, "academic_base_url", "https://meduniwien-api.academic-ai.at")
    monkeypatch.setattr(ConfigManager, "academic_model_name", "gpt-4o")

    import keyring
    creds = {"academic_client_id": "mock_cid", "academic_client_secret": "mock_sec"}
    monkeypatch.setattr(keyring, "get_password", lambda svc, key: creds.get(key))

    captured_requests = []

    def mock_urlopen(req, *args, **kwargs):
        captured_requests.append(req)
        resp_data = json.dumps({
            "success": True,
            "data": {
                "content": "This is an academic AI answer.",
                "model": "gpt-4o"
            }
        }).encode("utf-8")
        mock_resp = io.BytesIO(resp_data)
        class MockResp:
            def __enter__(self):
                return mock_resp
            def __exit__(self, *args):
                pass
        return MockResp()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    assistant = AIAssistant()
    assistant.local_document_text = "The quick brown fox jumps over the lazy dog."

    stream_chunks = []
    response = assistant.ask("What does the fox do?", stream_callback=lambda c: stream_chunks.append(c))

    assert response == "This is an academic AI answer."
    assert stream_chunks == ["This is an academic AI answer."]
    assert len(captured_requests) == 1

    sent_req = captured_requests[0]
    assert sent_req.full_url == "https://meduniwien-api.academic-ai.at/api/v1/llm/chat"
    assert sent_req.headers.get("X-client-id") == "mock_cid"
    assert sent_req.headers.get("X-client-secret") == "mock_sec"

    sent_payload = json.loads(sent_req.data.decode("utf-8"))
    assert sent_payload["model"] == "gpt-4o"
    assert sent_payload["maxTokens"] == 4096
    # Verify no system roles in payload
    for m in sent_payload["messages"]:
        assert m["role"] in ("user", "assistant")


def test_academic_config_dialog(qtbot, monkeypatch):
    import keyring
    stored_passwords = {}
    def mock_get(svc, key):
        return stored_passwords.get(key, "")
    def mock_set(svc, key, val):
        stored_passwords[key] = val
    monkeypatch.setattr(keyring, "get_password", mock_get)
    monkeypatch.setattr(keyring, "set_password", mock_set)

    from ui.config_dialog import ConfigDialog
    dialog = ConfigDialog()
    qtbot.addWidget(dialog)

    # Switch to academic provider
    dialog.show()
    dialog.radio_academic.setChecked(True)
    assert not dialog.academic_container.isHidden()
    assert dialog.cloud_container.isHidden()
    assert dialog.local_container.isHidden()

    # Enter academic credentials
    dialog.academic_url_input.setText("https://meduniwien-api.academic-ai.at")
    dialog.academic_id_input.setText("my_client_id_123")
    dialog.academic_secret_input.setText("my_client_secret_xyz")

    # Accept dialog to save settings
    dialog.accept()

    assert stored_passwords["academic_client_id"] == "my_client_id_123"
    assert stored_passwords["academic_client_secret"] == "my_client_secret_xyz"
    assert dialog.config.ai_provider == "academic"
    assert dialog.config.academic_base_url == "https://meduniwien-api.academic-ai.at"


def test_extract_academic_error_message():
    # 1. Nested validation error in meta.error.message
    nested_err = {
        "message": "API request failed",
        "meta": {
            "error": {
                "internalErrorCode": 400,
                "message": "API Client Error: Validation failed: Field 'temperature' for model 'gpt-5.2' is only supported when reasoningEffort is 'none'"
            }
        }
    }
    extracted = _extract_academic_error_message(nested_err, "Fallback")
    assert extracted == "Validation failed: Field 'temperature' for model 'gpt-5.2' is only supported when reasoningEffort is 'none'"

    # 2. Standard top-level message
    simple_err = {"message": "Invalid API token"}
    assert _extract_academic_error_message(simple_err, "Fallback") == "Invalid API token"

    # 3. Generic "API request failed" with no detail falls back
    generic_err = {"message": "API request failed"}
    assert _extract_academic_error_message(generic_err, "Fallback Reason") == "API request failed"


def test_academic_call_api_reasoning_model_omits_temperature(monkeypatch):
    monkeypatch.setattr(ConfigManager, "ai_provider", "academic")
    monkeypatch.setattr(ConfigManager, "academic_model_name", "gpt-5.2")

    import keyring
    creds = {"academic_client_id": "mock_cid", "academic_client_secret": "mock_sec"}
    monkeypatch.setattr(keyring, "get_password", lambda svc, key: creds.get(key))

    captured_requests = []

    def mock_urlopen(req, *args, **kwargs):
        captured_requests.append(req)
        resp_data = json.dumps({
            "success": True,
            "data": {
                "content": "Answer from gpt-5.2",
                "model": "gpt-5.2"
            }
        }).encode("utf-8")
        mock_resp = io.BytesIO(resp_data)
        class MockResp:
            def __enter__(self):
                return mock_resp
            def __exit__(self, *args):
                pass
        return MockResp()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    assistant = AIAssistant()
    res = assistant._call_academic_api([{"role": "user", "content": "Hello"}])
    assert res == "Answer from gpt-5.2"
    assert len(captured_requests) == 1

    payload = json.loads(captured_requests[0].data.decode("utf-8"))
    assert payload["model"] == "gpt-5.2"
    assert "temperature" not in payload  # Must not include temperature for gpt-5.2!


def test_academic_call_api_retry_on_temperature_rejection(monkeypatch):
    monkeypatch.setattr(ConfigManager, "ai_provider", "academic")
    monkeypatch.setattr(ConfigManager, "academic_model_name", "custom-reasoning-model")

    import keyring
    creds = {"academic_client_id": "mock_cid", "academic_client_secret": "mock_sec"}
    monkeypatch.setattr(keyring, "get_password", lambda svc, key: creds.get(key))

    call_count = 0

    def mock_urlopen(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        payload = json.loads(req.data.decode("utf-8"))
        if "temperature" in payload:
            err_json = {
                "message": "API request failed",
                "meta": {
                    "error": {
                        "message": "API Client Error: Field 'temperature' is not supported for this model"
                    }
                }
            }
            err_bytes = json.dumps(err_json).encode("utf-8")
            raise urllib.error.HTTPError("http://test", 400, "Bad Request", {}, io.BytesIO(err_bytes))

        # Second call succeeds
        resp_data = json.dumps({
            "success": True,
            "data": {"content": "Answer after retry"}
        }).encode("utf-8")
        mock_resp = io.BytesIO(resp_data)
        class MockResp:
            def __enter__(self):
                return mock_resp
            def __exit__(self, *args):
                pass
        return MockResp()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    assistant = AIAssistant()
    # If custom model had temperature, it catches 400 and retries without temperature
    res = assistant._call_academic_api([{"role": "user", "content": "Hello"}], model_override="standard-model")
    assert res == "Answer after retry"
    assert call_count == 2

