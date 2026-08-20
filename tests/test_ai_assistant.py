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

def test_initialization():
    assistant = AIAssistant("fake-key", "gemini-3.5-flash")
    assert assistant.api_key == "fake-key"
    assert assistant.model_name == "gemini-3.5-flash"

def test_rank_available_models(mock_genai, mock_qsettings):
    # Mock settings to pretend no cache
    mock_settings = MagicMock()
    mock_settings.value.side_effect = lambda *args, **kwargs: None
    mock_qsettings.return_value = mock_settings
    
    # Mock client and models
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    assistant = AIAssistant("fake-key", "gemini-3.5-flash")
    
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
            
    mock_client.models.generate_content.return_value = DummyResponse()
    
    assistant.rank_available_models()
    
    assert hasattr(assistant, "ranked_models")
    assert len(assistant.ranked_models) == 3
    assert assistant.ranked_models[0]["name"] in ["gemini-2.5-flash", "gemini-3.5-flash"]
    assert assistant.ranked_models[-1]["name"] == "gemini-3.5-flash-lite"

def test_ask_direct_error_raising(mock_genai):
    assistant = AIAssistant("fake-key", "gemini-3.5-flash")
    
    # Mock client
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    
    # Force an exception when calling generate_content
    mock_client.models.generate_content.side_effect = Exception("429 Quota Exceeded")
    
    assistant._initialize_models()
    
    with pytest.raises(Exception, match="429 Quota Exceeded"):
        assistant.ask_direct("Hello")
