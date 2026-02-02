"""
레시피 크롤러
만개의 레시피 사이트의 레시피 상세 정보 수집
"""
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import LIST_URL, RECIPE_URL, RAW_DIR
from utils.helpers import (
    fetch_page, save_json, logger,
    get_text_safe, get_attr_safe,
    clean_image_url, extract_recipe_id
)


def get_total_pages() -> int:
    """전체 페이지 수 조회"""
    soup = fetch_page(LIST_URL)
    if not soup:
        return 0

    # 총 레시피 수 추출: "총 262,595개의 맛있는 레시피가 있습니다"
    full_text = soup.get_text()

    # 패턴 매칭: "총 N개" 또는 "N개의 ... 레시피"
    matches = re.findall(r'총\s*([\d,]+)\s*개', full_text)
    if not matches:
        matches = re.findall(r'([\d,]+)\s*개의.*레시피', full_text)

    if matches:
        total_recipes = int(matches[0].replace(",", ""))
        # 페이지당 40개 기준
        total_pages = (total_recipes + 39) // 40
        logger.info(f"총 레시피: {total_recipes:,}개, 총 페이지: {total_pages:,}개")
        return total_pages

    return 0


def crawl_recipe_list(page: int) -> List[Dict[str, str]]:
    """
    레시피 목록 페이지에서 레시피 기본 정보 수집

    Args:
        page: 페이지 번호

    Returns:
        레시피 기본 정보 리스트
    """
    url = f"{LIST_URL}?page={page}"
    soup = fetch_page(url)

    if not soup:
        return []

    recipes = []

    # 레시피 카드 찾기
    recipe_cards = soup.find_all("li", class_="common_sp_list_li")

    for card in recipe_cards:
        recipe = _parse_recipe_card(card)
        if recipe:
            recipes.append(recipe)

    return recipes


def _parse_recipe_card(card) -> Optional[Dict[str, str]]:
    """레시피 카드에서 기본 정보 추출"""
    try:
        # 링크에서 ID 추출
        link = card.find("a", class_="common_sp_link")
        if not link:
            return None

        href = get_attr_safe(link, "href")
        recipe_id = extract_recipe_id(href)
        if not recipe_id:
            return None

        # 제목
        title_elem = card.find("div", class_="common_sp_caption_tit")
        title = get_text_safe(title_elem)

        # 썸네일
        thumb_div = card.find("div", class_="common_sp_thumb")
        img_elem = thumb_div.find("img") if thumb_div else None
        thumbnail = get_attr_safe(img_elem, "src") if img_elem else ""

        # 작성자
        author_div = card.find("div", class_="common_sp_caption_rv_name")
        author = get_text_safe(author_div).strip() if author_div else ""

        return {
            "recipe_id": recipe_id,
            "title_original": title,
            "thumbnail_url": thumbnail,
            "author": author,
        }

    except Exception as e:
        logger.warning(f"레시피 카드 파싱 실패: {e}")
        return None


def crawl_recipe_detail(recipe_id: str) -> Optional[Dict[str, Any]]:
    """
    레시피 상세 페이지 크롤링

    Args:
        recipe_id: 레시피 ID

    Returns:
        레시피 상세 정보 딕셔너리
    """
    url = f"{RECIPE_URL}/{recipe_id}"
    soup = fetch_page(url)

    if not soup:
        return None

    try:
        recipe = {
            "recipe_id": recipe_id,
            "url": url,
        }

        # 제목
        title_elem = soup.find("div", class_="view2_summary")
        if title_elem:
            h3 = title_elem.find("h3")
            recipe["title_original"] = get_text_safe(h3)

        # 소개글
        summary_info = soup.find("div", class_="view2_summary_info")
        if summary_info:
            recipe["description"] = get_text_safe(summary_info)

        # 메인 이미지
        main_img = soup.find("img", id="main_thumbs")
        if main_img:
            img_url = get_attr_safe(main_img, "src")
            recipe["main_image_url"] = clean_image_url(img_url)

        # 작성자
        author_elem = soup.find("span", class_="user_info2_name")
        if not author_elem:
            author_elem = soup.find("a", class_="user_link2")
        if author_elem:
            recipe["author"] = get_text_safe(author_elem)

        # 요리 정보 (인분, 시간, 난이도)
        recipe.update(_parse_cooking_info(soup))

        # 평점
        recipe["rating"] = _parse_rating(soup)

        # 재료
        recipe["ingredients"] = _parse_ingredients(soup)

        # 조리 순서
        recipe["steps"] = _parse_steps(soup)

        # 요리 팁
        recipe["tips"] = _parse_tips(soup)

        # 카테고리
        recipe.update(_parse_categories(soup))

        return recipe

    except Exception as e:
        logger.error(f"레시피 상세 파싱 실패 (ID: {recipe_id}): {e}")
        return None


def _parse_cooking_info(soup) -> Dict[str, str]:
    """인분, 조리시간, 난이도 파싱"""
    info = {
        "servings": None,
        "cook_time": None,
        "difficulty": None,
    }

    # span.view2_summary_info1 모두 찾기
    info_spans = soup.find_all("span", class_="view2_summary_info1")
    for span in info_spans:
        text = get_text_safe(span)
        if "인분" in text:
            info["servings"] = text
        elif "분" in text or "시간" in text:
            info["cook_time"] = text
        elif any(word in text for word in ["아무나", "초급", "중급", "고급", "신의경지"]):
            info["difficulty"] = text

    return info


def _parse_rating(soup) -> Optional[float]:
    """평점 파싱"""
    rating_elem = soup.find("span", class_="view2_rating")
    if rating_elem:
        try:
            return float(get_text_safe(rating_elem))
        except ValueError:
            pass
    return None


def _parse_ingredients(soup) -> List[Dict[str, str]]:
    """재료 파싱"""
    ingredients = []

    # 재료 섹션 찾기
    ing_div = soup.find("div", class_="ready_ingre3")
    if not ing_div:
        return ingredients

    # 각 재료 항목
    for li in ing_div.find_all("li"):
        name_elem = li.find("div", class_="ingre_list_name")
        amount_elem = li.find("span", class_="ingre_list_ea")

        if name_elem:
            ingredient = {
                "name": get_text_safe(name_elem),
                "amount": get_text_safe(amount_elem) if amount_elem else ""
            }
            ingredients.append(ingredient)

    return ingredients


def _parse_steps(soup) -> List[Dict[str, Any]]:
    """조리 순서 파싱"""
    steps = []

    # 조리 순서 섹션
    step_divs = soup.find_all("div", class_="view_step_cont")

    for i, step_div in enumerate(step_divs, 1):
        # 설명
        desc_elem = step_div.find("div", class_="media-body")
        description = get_text_safe(desc_elem) if desc_elem else ""

        # 이미지 (있을 경우)
        img_elem = step_div.find("img")
        image_url = clean_image_url(get_attr_safe(img_elem, "src")) if img_elem else ""

        steps.append({
            "step_num": i,
            "description": description,
            "image_url": image_url,
        })

    return steps


def _parse_tips(soup) -> Optional[str]:
    """요리 팁 파싱"""
    tip_div = soup.find("div", class_="view_step_tip")
    if tip_div:
        tip_text = tip_div.find("dd")
        if tip_text:
            return get_text_safe(tip_text)
    return None


def _parse_categories(soup) -> Dict[str, Optional[str]]:
    """카테고리 파싱 (각 차원에서 1개씩)"""
    categories = {
        "cat_type": None,       # 종류별
        "cat_situation": None,  # 상황별
        "cat_ingredient": None, # 재료별
        "cat_method": None,     # 방법별
    }

    # 카테고리 파라미터 매핑
    param_to_field = {
        "cat4": "cat_type",
        "cat2": "cat_situation",
        "cat3": "cat_ingredient",
        "cat1": "cat_method",
    }

    # 레시피 정보 영역에서 카테고리 링크 찾기
    category_area = soup.find("div", class_="view_cate")
    if not category_area:
        # 대안: 전체 페이지에서 찾기
        category_area = soup

    for link in category_area.find_all("a", href=True):
        href = link.get("href", "")

        for param, field in param_to_field.items():
            if f"{param}=" in href and categories[field] is None:
                # 이미 값이 없을 때만 설정 (첫 번째 값 사용)
                cat_name = get_text_safe(link)
                if cat_name and cat_name != "전체":
                    categories[field] = cat_name
                    break

    return categories


def save_recipe(recipe: Dict[str, Any]) -> bool:
    """개별 레시피를 JSON 파일로 저장"""
    recipe_id = recipe.get("recipe_id")
    if not recipe_id:
        return False

    filepath = RAW_DIR / "recipes" / f"{recipe_id}.json"
    return save_json(recipe, filepath)


if __name__ == "__main__":
    # 테스트 실행
    print("전체 페이지 수 확인...")
    total = get_total_pages()
    print(f"총 {total:,} 페이지")

    print("\n첫 페이지 레시피 목록...")
    recipes = crawl_recipe_list(1)
    for r in recipes[:3]:
        print(f"  - {r['title_original']} (ID: {r['recipe_id']})")

    if recipes:
        print(f"\n첫 번째 레시피 상세 정보...")
        detail = crawl_recipe_detail(recipes[0]["recipe_id"])
        if detail:
            print(f"  제목: {detail.get('title_original')}")
            print(f"  인분: {detail.get('servings')}")
            print(f"  시간: {detail.get('cook_time')}")
            print(f"  재료: {len(detail.get('ingredients', []))}개")
            print(f"  단계: {len(detail.get('steps', []))}개")
            print(f"  카테고리:")
            print(f"    - 종류별: {detail.get('cat_type')}")
            print(f"    - 상황별: {detail.get('cat_situation')}")
            print(f"    - 재료별: {detail.get('cat_ingredient')}")
            print(f"    - 방법별: {detail.get('cat_method')}")
