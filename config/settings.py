"""
만개의 레시피 크롤링 설정
"""
from pathlib import Path

# 기본 경로
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
IMAGES_DIR = DATA_DIR / "images"

# 크롤링 설정
BASE_URL = "https://www.10000recipe.com"
LIST_URL = f"{BASE_URL}/recipe/list.html"
RECIPE_URL = f"{BASE_URL}/recipe"

# 요청 설정
REQUEST_DELAY = 0.5  # 요청 간격 (초)
REQUEST_TIMEOUT = 30  # 요청 타임아웃 (초)
MAX_RETRIES = 3  # 최대 재시도 횟수
RETRY_DELAY = 2  # 재시도 대기 시간 (초)

# User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# 카테고리 파라미터 매핑
CATEGORY_PARAMS = {
    "cat_type": "cat4",       # 종류별
    "cat_situation": "cat2",  # 상황별
    "cat_ingredient": "cat3", # 재료별
    "cat_method": "cat1",     # 방법별
}

# 체크포인트 파일
CHECKPOINT_FILE = DATA_DIR / "checkpoint.json"
FAILED_IDS_FILE = DATA_DIR / "failed_ids.json"

# 로깅 설정
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "crawling.log"

# LLM 전처리 설정
LLM_MODEL = "unsloth/Qwen3-VL-8B-Instruct-unsloth-bnb-4bit"
LLM_BATCH_SIZE = 16
LLM_MAX_NEW_TOKENS = 128

# Gemini API 설정
import os
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# 디렉토리 생성
for dir_path in [DATA_DIR, RAW_DIR, PROCESSED_DIR, IMAGES_DIR, LOG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)
