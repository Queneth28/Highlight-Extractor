import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4-turbo"
WHISPER_MODEL = "whisper-1"

# File paths
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
LOGS_DIR = "logs"

# Video processing
TARGET_ASPECT_RATIO = 9/16
TARGET_RESOLUTION = (1080, 1920)
MIN_HIGHLIGHT_DURATION = 2
MAX_VIDEO_SIZE_MB = 500

# Subtitle styling
SUBTITLE_FONT_SIZE = 50
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_BG_COLOR = "black"
SUBTITLE_BG_OPACITY = 0.7

# Create directories
for directory in [UPLOAD_DIR, OUTPUT_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)
