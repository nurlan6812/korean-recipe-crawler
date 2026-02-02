"""
카테고리 크롤러
만개의 레시피 사이트의 카테고리 정보 수집
"""
import re
from typing import Dict, List, Optional
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import LIST_URL, RAW_DIR
from utils.helpers import fetch_page, save_json, logger, get_text_safe


# 카테고리 매핑 정보
CATEGORY_INFO = {
    "cat4": {
        "name": "종류별",
        "field": "cat_type"
    },
    "cat2": {
        "name": "상황별",
        "field": "cat_situation"
    },
    "cat3": {
        "name": "재료별",
        "field": "cat_ingredient"
    },
    "cat1": {
        "name": "방법별",
        "field": "cat_method"
    }
}


def crawl_categories() -> Dict[str, List[Dict[str, str]]]:
    """
    모든 카테고리 정보 크롤링

    Returns:
        카테고리 정보 딕셔너리
        {
            "cat_type": [{"code": "63", "name": "밑반찬"}, ...],
            "cat_situation": [...],
            ...
        }
    """
    logger.info("카테고리 크롤링 시작")

    soup = fetch_page(LIST_URL)
    if not soup:
        logger.error("카테고리 페이지 로드 실패")
        return {}

    categories = {}

    for cat_param, info in CATEGORY_INFO.items():
        field_name = info["field"]
        cat_name = info["name"]

        logger.info(f"  {cat_name} 카테고리 수집 중...")

        items = _extract_category_items(soup, cat_param)
        categories[field_name] = items

        logger.info(f"  {cat_name}: {len(items)}개 항목 수집")

    # 저장
    save_path = RAW_DIR / "categories.json"
    if save_json(categories, save_path):
        logger.info(f"카테고리 정보 저장 완료: {save_path}")

    return categories


def _extract_category_items(soup, cat_param: str) -> List[Dict[str, str]]:
    """
    특정 카테고리 파라미터의 항목들 추출

    Args:
        soup: BeautifulSoup 객체
        cat_param: 카테고리 파라미터 (cat1, cat2, cat3, cat4)

    Returns:
        카테고리 항목 리스트 [{"code": "63", "name": "밑반찬"}, ...]
    """
    items = []

    # 카테고리 링크 찾기
    # 패턴: href에 cat1=, cat2=, cat3=, cat4= 포함
    pattern = re.compile(rf'{cat_param}=(\d+)')

    # 모든 링크에서 해당 카테고리 추출
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        match = pattern.search(href)

        if match:
            code = match.group(1)
            name = get_text_safe(link)

            # "전체" 제외, 중복 제거
            if name and name != "전체":
                item = {"code": code, "name": name}
                if item not in items:
                    items.append(item)

    return items


def get_category_name(categories: Dict, field: str, code: str) -> Optional[str]:
    """
    카테고리 코드로 이름 조회

    Args:
        categories: 카테고리 딕셔너리
        field: 필드명 (cat_type, cat_situation 등)
        code: 카테고리 코드

    Returns:
        카테고리 이름 또는 None
    """
    if field not in categories:
        return None

    for item in categories[field]:
        if item["code"] == code:
            return item["name"]

    return None


if __name__ == "__main__":
    # 테스트 실행
    categories = crawl_categories()
    for field, items in categories.items():
        print(f"\n{field}:")
        for item in items[:5]:
            print(f"  - {item['name']} (code: {item['code']})")
        if len(items) > 5:
            print(f"  ... 외 {len(items) - 5}개")
