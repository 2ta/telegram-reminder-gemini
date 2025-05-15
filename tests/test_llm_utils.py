import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from src.llm_utils import get_llm_response, get_llm_json_response
from config import config # To potentially modify settings for tests

# Fixture to temporarily set API key for tests if needed, or ensure it's None
@pytest.fixture(autouse=True)
def mock_settings_api_key(monkeypatch):
    # For most tests, we want to ensure API key is set so ValueError isn't raised prematurely
    monkeypatch.setattr(config.settings, 'GEMINI_API_KEY', 'test_api_key')

@pytest.mark.asyncio
async def test_get_llm_response_success():
    mock_candidate = MagicMock()
    mock_candidate.content.parts = [MagicMock(text="Hello "), MagicMock(text="World")]
    mock_candidate.finish_reason = None # Or some success enum if applicable

    mock_genai_response = MagicMock()
    mock_genai_response.candidates = [mock_candidate]
    mock_genai_response.prompt_feedback = None

    with patch('src.llm_utils.genai.GenerativeModel', new_callable=MagicMock) as mock_generative_model_class:
        mock_model_instance = mock_generative_model_class.return_value
        # The SDK's generate_content is synchronous, so we mock its behavior within the executor call
        mock_model_instance.generate_content = MagicMock(return_value=mock_genai_response)
        
        # We also need to mock genai.configure if it's called inside _blocking_call
        with patch('src.llm_utils.genai.configure', MagicMock()) as mock_configure:
            response = await get_llm_response("test prompt")
            assert response == "Hello World"
            mock_configure.assert_called_once_with(api_key='test_api_key')
            mock_generative_model_class.assert_called_once_with(config.settings.GEMINI_MODEL_NAME)
            mock_model_instance.generate_content.assert_called_once_with("test prompt")

@pytest.mark.asyncio
async def test_get_llm_response_api_key_missing(monkeypatch):
    monkeypatch.setattr(config.settings, 'GEMINI_API_KEY', None)
    with pytest.raises(ValueError, match="Gemini API key is not configured"):
        await get_llm_response("test prompt")

@pytest.mark.asyncio
async def test_get_llm_response_blocked_prompt():
    mock_genai_response = MagicMock()
    mock_genai_response.candidates = [] # No candidates
    mock_genai_response.prompt_feedback = MagicMock()
    mock_genai_response.prompt_feedback.block_reason = MagicMock(name="SAFETY") # Example block reason

    with patch('src.llm_utils.genai.GenerativeModel') as mock_generative_model_class:
        mock_model_instance = mock_generative_model_class.return_value
        mock_model_instance.generate_content = MagicMock(return_value=mock_genai_response)
        with patch('src.llm_utils.genai.configure', MagicMock()):
            with pytest.raises(Exception, match="Prompt blocked by API. Reason: SAFETY"):
                await get_llm_response("blocked prompt")

@pytest.mark.asyncio
async def test_get_llm_response_no_content_parts():
    mock_candidate = MagicMock()
    mock_candidate.content.parts = [] # No parts
    mock_candidate.finish_reason = None
    mock_genai_response = MagicMock()
    mock_genai_response.candidates = [mock_candidate]
    mock_genai_response.prompt_feedback = None

    with patch('src.llm_utils.genai.GenerativeModel') as mock_generative_model_class:
        mock_model_instance = mock_generative_model_class.return_value
        mock_model_instance.generate_content = MagicMock(return_value=mock_genai_response)
        with patch('src.llm_utils.genai.configure', MagicMock()):
            response = await get_llm_response("prompt leading to no content")
            assert response == "" # Expect empty string as per current implementation

@pytest.mark.asyncio
async def test_get_llm_json_response_success():
    # Mock get_llm_response directly for this test
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.return_value = '```json\n{"key": "value", "number": 123}```'
        
        json_response = await get_llm_json_response(
            prompt_template="Test template: {data}", 
            input_variables={"data": "test_data"}
        )
        assert json_response == {"key": "value", "number": 123}
        mock_get_raw_response.assert_called_once_with(
            prompt="Test template: test_data", 
            model_name=config.settings.GEMINI_MODEL_NAME
        )

@pytest.mark.asyncio
async def test_get_llm_json_response_plain_json():
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.return_value = '{"key": "plain_value"}'
        json_response = await get_llm_json_response("template", {})
        assert json_response == {"key": "plain_value"}

@pytest.mark.asyncio
async def test_get_llm_json_response_invalid_json():
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.return_value = 'This is not json'
        with pytest.raises(ValueError, match="LLM response was not valid JSON: This is not json"):
            await get_llm_json_response("template", {})

@pytest.mark.asyncio
async def test_get_llm_json_response_empty_cleaned_response():
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.return_value = '```json\n\n```' # json block is empty
        with pytest.raises(ValueError, match="LLM response was empty after cleaning"):
            await get_llm_json_response("template", {})

@pytest.mark.asyncio
async def test_get_llm_json_response_empty_string_response():
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.return_value = '' # LLM returns completely empty string
        with pytest.raises(ValueError, match="LLM response was empty after cleaning"):
            await get_llm_json_response("template", {})

# Example of how to test if an underlying exception from get_llm_response bubbles up
@pytest.mark.asyncio
async def test_get_llm_json_response_propagates_llm_error():
    with patch('src.llm_utils.get_llm_response', new_callable=AsyncMock) as mock_get_raw_response:
        mock_get_raw_response.side_effect = Exception("LLM Down!")
        with pytest.raises(Exception, match="LLM Down!"):
            await get_llm_json_response("template", {}) 