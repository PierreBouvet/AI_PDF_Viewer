import pytest
import json
from unittest.mock import MagicMock, patch
from backend.ai_assistant import AIAssistant, FREE_TIER_QUOTAS

@pytest.fixture
def mock_genai():
    with patch("backend.ai_assistant.genai") as mock:
        yield mock

@pytest.fixture
def mock_qsettings():
    with patch("backend.ai_assistant.QSettings") as mock:
        yield mock

@pytest.fixture
def mock_keyring():
    with patch("backend.ai_assistant.keyring") as mock:
        mock.get_password.return_value = "fake-key"
        yield mock

def test_initialization():
    assistant = AIAssistant("gemini-3.5-flash")
    assert assistant.model_name == "gemini-3.5-flash"

def test_rank_available_models(mock_genai, mock_qsettings):
    # Mock settings to pretend no cache
    mock_settings = MagicMock()
    mock_settings.value.side_effect = lambda *args, **kwargs: None
    mock_qsettings.return_value = mock_settings
    
    # Mock client and models
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    assistant = AIAssistant("gemini-3.5-flash")
    
    mock_model1 = MagicMock()
    mock_model1.name = "models/gemini-2.5-flash"
    mock_model2 = MagicMock()
    mock_model2.name = "models/gemini-3.5-flash"
    mock_model3 = MagicMock()
    mock_model3.name = "models/gemini-3.5-flash-lite"
    
    mock_client.models.list.return_value = [mock_model1, mock_model2, mock_model3]
    
    class DummyResponse:
        @property
        def text(self):
            return json.dumps(["models/gemini-2.5-flash", "models/gemini-3.5-flash", "models/gemini-3.5-flash-lite"])
            
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat
    mock_chat.send_message.return_value = DummyResponse()
    
    assistant.rank_available_models()
    
    assert hasattr(assistant, "ranked_models")
    assert len(assistant.ranked_models) == 3
    assert assistant.ranked_models[0]["name"] in ["gemini-2.5-flash", "gemini-3.5-flash"]
    assert assistant.ranked_models[-1]["name"] == "gemini-3.5-flash-lite"

def test_ask_direct_error_raising(mock_genai, mock_keyring):
    assistant = AIAssistant("gemini-3.5-flash")
    
    # Mock client
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    # Force an exception when calling send_message
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat
    mock_chat.send_message.side_effect = Exception("429 Quota Exceeded")
    
    assistant._initialize_models()
    
    with pytest.raises(Exception, match="429 Quota Exceeded"):
        assistant.ask_direct("Hello")

def test_ask_direct_model_override(mock_genai, mock_keyring):
    assistant = AIAssistant("gemini-3.5-flash")
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    mock_chat = MagicMock()
    mock_client.chats.create.return_value = mock_chat
    
    class DummyResp:
        @property
        def text(self):
            return "Custom model output"
            
    mock_chat.send_message.return_value = DummyResp()
    
    assistant._initialize_models()
    result = assistant.ask_direct("Test prompt", model_override="gemini-2.5-pro")
    
    assert result == "Custom model output"
    mock_client.chats.create.assert_called_with(model="gemini-2.5-pro")
    # Persistent model name must not have been mutated
    assert assistant.model_name == "gemini-3.5-flash"
