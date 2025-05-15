import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import tempfile

from telegram import Voice, File as TGFile
from telegram.ext import ContextTypes

from src.voice_utils import download_voice_message, transcribe_persian_voice, process_voice_message
from config.config import Settings # Import the class for type hinting or direct use if needed for test setup

@pytest.fixture
def mock_context():
    """Mocks ContextTypes.DEFAULT_TYPE for voice utility functions."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = AsyncMock()
    return context

@pytest.fixture
def mock_telegram_voice_file():
    """Mocks a Telegram Voice object and its associated File object."""
    mock_file = AsyncMock(spec=TGFile)
    mock_file.file_id = "test_voice_file_id"
    # mock_file.download = AsyncMock() # Replaced by download_to_drive
    mock_file.download_to_drive = AsyncMock(return_value="/fake/path/downloaded.ogg")

    mock_voice = MagicMock(spec=Voice)
    mock_voice.file_id = "test_voice_file_id"
    mock_voice.duration = 60 # seconds
    mock_voice.mime_type = "audio/ogg"
    return mock_voice, mock_file


@pytest.mark.asyncio
async def test_download_voice_message_success(mock_context, mock_telegram_voice_file):
    mock_voice, mock_tg_file_obj = mock_telegram_voice_file
    mock_context.bot.get_file.return_value = mock_tg_file_obj

    # Use a real temporary file to test the download_to_drive logic
    with tempfile.NamedTemporaryFile(delete=True, suffix=".ogg") as temp_audio_file_obj:
        # Mock download_to_drive to use this temp file's name
        mock_tg_file_obj.download_to_drive = AsyncMock(
            side_effect=lambda custom_path: open(custom_path, 'wb').write(b'fake ogg data')
        )

        # Patch tempfile.NamedTemporaryFile to control its name and prevent deletion within the test scope if needed
        # For this test, we want it to create a file, so we will mock what `download_to_drive` needs.
        # The important part is that download_to_drive is called with the temp file's name.
        with patch('tempfile.NamedTemporaryFile', return_value=temp_audio_file_obj) as mock_tempfile_constructor:
            downloaded_path = await download_voice_message(mock_voice.file_id, mock_context)
            
            mock_context.bot.get_file.assert_awaited_once_with(mock_voice.file_id)
            # Assert that download_to_drive was called with the path of the temp file
            mock_tg_file_obj.download_to_drive.assert_awaited_once_with(custom_path=temp_audio_file_obj.name)
            assert downloaded_path == temp_audio_file_obj.name
            assert os.path.exists(downloaded_path) # Check if file was actually created by the mock

@pytest.mark.asyncio
async def test_download_voice_message_failure(mock_context):
    mock_context.bot.get_file.side_effect = Exception("Telegram API error")
    downloaded_path = await download_voice_message("bad_file_id", mock_context)
    assert downloaded_path is None


@patch('src.voice_utils.speech.SpeechClient')
@patch('src.voice_utils.settings') # To control GOOGLE_APPLICATION_CREDENTIALS
def test_transcribe_persian_voice_success(mock_settings, MockSpeechClient):
    mock_settings.GOOGLE_APPLICATION_CREDENTIALS = "fake_creds.json"
    mock_settings.GEMINI_LOCATION = "us-central1" # or any other for non-EU endpoint
    
    # Mock the SpeechClient and its recognize method
    mock_client_instance = MockSpeechClient.return_value
    mock_response = MagicMock()
    mock_alternative = MagicMock()
    mock_alternative.transcript = "سلام دنیا"
    mock_result = MagicMock()
    mock_result.alternatives = [mock_alternative]
    mock_response.results = [mock_result]
    mock_client_instance.recognize.return_value = mock_response

    # Create a dummy audio file for the test
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmpfile:
        tmpfile.write(b"fake audio data")
        audio_file_path = tmpfile.name

    # Patch os.path.exists for GOOGLE_APPLICATION_CREDENTIALS check
    with patch('os.path.exists', side_effect=lambda path: path == "fake_creds.json" or path == audio_file_path) as mock_os_exists, \
         patch('builtins.open', mock_open(read_data=b"fake audio data")) as mock_file_open, \
         patch('os.remove') as mock_os_remove:
        
        transcription = transcribe_persian_voice(audio_file_path)

        MockSpeechClient.assert_called_once() # Check if client was initialized
        mock_client_instance.recognize.assert_called_once()
        args, kwargs = mock_client_instance.recognize.call_args
        config = kwargs['config']
        assert config.language_code == "fa-IR"
        assert config.encoding == speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        assert transcription == "سلام دنیا"
        mock_os_remove.assert_called_once_with(audio_file_path) # Check cleanup

@patch('src.voice_utils.speech.SpeechClient')
@patch('src.voice_utils.settings')
def test_transcribe_persian_voice_no_creds(mock_settings, MockSpeechClient):
    mock_settings.GOOGLE_APPLICATION_CREDENTIALS = None
    transcription = transcribe_persian_voice("any_path.ogg")
    assert transcription is None
    MockSpeechClient.assert_not_called()

@patch('src.voice_utils.speech.SpeechClient')
@patch('src.voice_utils.settings')
@patch('os.path.exists', return_value=False) # Mock credentials file not existing
def test_transcribe_persian_voice_creds_file_not_found(mock_os_exists, mock_settings, MockSpeechClient):
    mock_settings.GOOGLE_APPLICATION_CREDENTIALS = "non_existent_creds.json"
    transcription = transcribe_persian_voice("any_path.ogg")
    assert transcription is None
    MockSpeechClient.assert_not_called()
    mock_os_exists.assert_any_call("non_existent_creds.json")

@patch('src.voice_utils.speech.SpeechClient')
@patch('src.voice_utils.settings')
def test_transcribe_persian_voice_api_error(mock_settings, MockSpeechClient):
    mock_settings.GOOGLE_APPLICATION_CREDENTIALS = "fake_creds.json"
    MockSpeechClient.return_value.recognize.side_effect = Exception("Google API Error")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmpfile:
        tmpfile.write(b"fake audio data")
        audio_file_path = tmpfile.name

    with patch('os.path.exists', return_value=True), \
         patch('builtins.open', mock_open(read_data=b"fake audio data")), \
         patch('os.remove') as mock_os_remove:
        transcription = transcribe_persian_voice(audio_file_path)
        assert transcription is None
        mock_os_remove.assert_called_once_with(audio_file_path)


@pytest.mark.asyncio
@patch('src.voice_utils.download_voice_message', new_callable=AsyncMock)
@patch('src.voice_utils.transcribe_persian_voice')
async def test_process_voice_message_success(mock_transcribe, mock_download, mock_context, mock_telegram_voice_file):
    update = AsyncMock(spec=Update) # Using AsyncMock for update for awaitable reply_text
    update.message = AsyncMock()
    update.message.voice, _ = mock_telegram_voice_file
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    mock_download.return_value = "/fake/path/downloaded.ogg"
    mock_transcribe.return_value = "سلام این تست است"

    result = await process_voice_message(update, mock_context)

    mock_download.assert_awaited_once_with(update.message.voice.file_id, mock_context)
    mock_transcribe.assert_called_once_with("/fake/path/downloaded.ogg")
    assert result == "سلام این تست است"
    update.message.reply_text.assert_not_called() # Errors are handled by reply_text in this func

@pytest.mark.asyncio
async def test_process_voice_message_too_long(mock_context, mock_telegram_voice_file):
    update = AsyncMock(spec=Update)
    update.message = AsyncMock()
    update.message.voice, _ = mock_telegram_voice_file
    update.message.voice.duration = 301 # Too long
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    result = await process_voice_message(update, mock_context)
    assert result is None
    update.message.reply_text.assert_awaited_once_with("فایل صوتی شما بیش از حد طولانی است. لطفاً فایل‌های کوتاه‌تر ارسال کنید.")

@pytest.mark.asyncio
@patch('src.voice_utils.download_voice_message', new_callable=AsyncMock)
async def test_process_voice_message_download_fails(mock_download, mock_context, mock_telegram_voice_file):
    update = AsyncMock(spec=Update)
    update.message = AsyncMock()
    update.message.voice, _ = mock_telegram_voice_file
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    mock_download.return_value = None # Simulate download failure

    result = await process_voice_message(update, mock_context)
    assert result is None
    update.message.reply_text.assert_awaited_once_with("متاسفانه در دانلود فایل صوتی مشکلی پیش آمد.")

@pytest.mark.asyncio
@patch('src.voice_utils.download_voice_message', new_callable=AsyncMock)
@patch('src.voice_utils.transcribe_persian_voice')
async def test_process_voice_message_transcription_fails(mock_transcribe, mock_download, mock_context, mock_telegram_voice_file):
    update = AsyncMock(spec=Update)
    update.message = AsyncMock()
    update.message.voice, _ = mock_telegram_voice_file
    update.effective_user = MagicMock()
    update.effective_user.id = 123
    update.message.reply_text = AsyncMock()

    mock_download.return_value = "/fake/path/downloaded.ogg"
    mock_transcribe.return_value = None # Simulate transcription failure

    result = await process_voice_message(update, mock_context)
    assert result is None
    update.message.reply_text.assert_awaited_once_with("متاسفانه در تبدیل گفتار به نوشتار مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا پیام خود را بنویسید.") 