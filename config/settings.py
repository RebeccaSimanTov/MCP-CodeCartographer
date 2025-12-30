import os
from dotenv import load_dotenv

load_dotenv()


class GeminiConfig:
    """הגדרות עבור Gemini API."""
    API_KEY = os.getenv("GEMINI_API_KEY")
    API_BASE = "https://generativelanguage.googleapis.com/v1beta"
    MODEL = "gemini-2.5-flash"
    TEMPERATURE = 0.7
    TIMEOUT = 30
    MAX_RETRIES = 3
    VERIFY_SSL = False  # False for NetFree compatibility


class ServerConfig:
    """הגדרות עבור השרת."""
    NAME = "Code Cartographer"
    LOG_FILE = "server.log"
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


class VisualizationConfig:
    """הגדרות עבור ויזואליזציה."""
    DEFAULT_FILENAME = "architecture_map.png"
    FIGURE_SIZE = (10, 8)
    SPRING_LAYOUT_K = 0.8
    BASE_NODE_SIZE = 1000
    NODE_SIZE_MULTIPLIER = 500
    FONT_SIZE = 10
    FONT_WEIGHT = "bold"
    EDGE_COLOR = "gray"
    COLOR_MAP = "coolwarm"


class ScannerConfig:
    """הגדרות עבור סורק ה-repository."""
    EXCLUDE_FILES = ["server.py"]
    FILE_EXTENSION = ".py"
    DEFAULT_PATH = "."