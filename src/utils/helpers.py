"""
공통 유틸리티 함수
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT,
    MAX_RETRIES, RETRY_DELAY, LOG_FILE, LOG_DIR
)


def setup_logger(name: str = "crawler") -> logging.Logger:
    """로거 설정"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 파일 핸들러
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 포맷터
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


logger = setup_logger()


def fetch_page(url: str, delay: float = REQUEST_DELAY) -> Optional[BeautifulSoup]:
    """
    페이지 요청 및 파싱

    Args:
        url: 요청 URL
        delay: 요청 전 대기 시간

    Returns:
        BeautifulSoup 객체 또는 None
    """
    time.sleep(delay)

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            response.encoding = "utf-8"

            return BeautifulSoup(response.text, "lxml")

        except requests.RequestException as e:
            logger.warning(f"요청 실패 (시도 {attempt + 1}/{MAX_RETRIES}): {url} - {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"최종 실패: {url}")
                return None

    return None


def save_json(data: Any, filepath: Path) -> bool:
    """JSON 파일 저장"""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"JSON 저장 실패: {filepath} - {e}")
        return False


def load_json(filepath: Path) -> Optional[Any]:
    """JSON 파일 로드"""
    try:
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    except Exception as e:
        logger.error(f"JSON 로드 실패: {filepath} - {e}")
        return None


def get_text_safe(element, default: str = "") -> str:
    """BeautifulSoup 요소에서 안전하게 텍스트 추출"""
    if element:
        return element.get_text(strip=True)
    return default


def get_attr_safe(element, attr: str, default: str = "") -> str:
    """BeautifulSoup 요소에서 안전하게 속성 추출"""
    if element and element.has_attr(attr):
        return element[attr]
    return default


def clean_image_url(url: str) -> str:
    """
    이미지 URL에서 썸네일 접미사 제거하여 원본 URL 반환

    예: ...image_m.jpg -> ...image.jpg
    """
    if not url:
        return ""

    # _m 접미사 제거 (썸네일 -> 원본)
    if "_m." in url:
        url = url.replace("_m.", ".")

    return url


def extract_recipe_id(url: str) -> Optional[str]:
    """URL에서 레시피 ID 추출"""
    try:
        # /recipe/1234567 형식에서 ID 추출
        parts = url.rstrip("/").split("/")
        recipe_id = parts[-1]
        if recipe_id.isdigit():
            return recipe_id
        return None
    except Exception:
        return None


class Checkpoint:
    """크롤링 체크포인트 관리"""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        """체크포인트 로드"""
        data = load_json(self.filepath)
        if data is None:
            data = {
                "last_page": 0,
                "crawled_ids": [],
                "total_recipes": 0,
            }
        return data

    def save(self) -> bool:
        """체크포인트 저장"""
        return save_json(self.data, self.filepath)

    def update_page(self, page: int):
        """마지막 크롤링 페이지 업데이트"""
        self.data["last_page"] = page
        self.save()

    def add_recipe_id(self, recipe_id: str):
        """크롤링된 레시피 ID 추가"""
        if recipe_id not in self.data["crawled_ids"]:
            self.data["crawled_ids"].append(recipe_id)

    def is_crawled(self, recipe_id: str) -> bool:
        """해당 레시피가 이미 크롤링되었는지 확인"""
        return recipe_id in self.data["crawled_ids"]

    @property
    def last_page(self) -> int:
        return self.data.get("last_page", 0)

    @property
    def crawled_count(self) -> int:
        return len(self.data.get("crawled_ids", []))
