"""
JSON 저장 핸들러
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PROCESSED_DIR, RAW_DIR
from utils.helpers import logger, save_json, load_json


def save_recipe_json(recipe: Dict[str, Any]) -> bool:
    """
    개별 레시피를 JSON 파일로 저장

    Args:
        recipe: 레시피 딕셔너리

    Returns:
        성공 여부
    """
    recipe_id = recipe.get("recipe_id")
    if not recipe_id:
        logger.warning("레시피 ID가 없습니다")
        return False

    # processed 디렉토리에 저장
    recipes_dir = PROCESSED_DIR / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    filepath = recipes_dir / f"{recipe_id}.json"
    return save_json(recipe, filepath)


def load_recipe_json(recipe_id: str) -> Optional[Dict[str, Any]]:
    """
    개별 레시피 JSON 파일 로드

    Args:
        recipe_id: 레시피 ID

    Returns:
        레시피 딕셔너리 또는 None
    """
    filepath = PROCESSED_DIR / "recipes" / f"{recipe_id}.json"
    return load_json(filepath)


def save_all_recipes_json(recipes: List[Dict[str, Any]], filename: str = "all_recipes.json") -> bool:
    """
    모든 레시피를 단일 JSON 파일로 저장

    Args:
        recipes: 레시피 리스트
        filename: 저장할 파일명

    Returns:
        성공 여부
    """
    filepath = PROCESSED_DIR / filename
    return save_json(recipes, filepath)


def load_all_recipes_json(filename: str = "all_recipes.json") -> List[Dict[str, Any]]:
    """
    모든 레시피를 단일 JSON 파일에서 로드

    Returns:
        레시피 리스트
    """
    filepath = PROCESSED_DIR / filename
    data = load_json(filepath)
    return data if data else []


def save_categories_json(categories: Dict[str, List[Dict]], filename: str = "categories.json") -> bool:
    """
    카테고리 정보를 JSON으로 저장

    Args:
        categories: 카테고리 딕셔너리
        filename: 저장할 파일명

    Returns:
        성공 여부
    """
    filepath = PROCESSED_DIR / filename
    return save_json(categories, filepath)


def load_categories_json(filename: str = "categories.json") -> Dict[str, List[Dict]]:
    """
    카테고리 정보 JSON 로드

    Returns:
        카테고리 딕셔너리
    """
    filepath = PROCESSED_DIR / filename
    data = load_json(filepath)
    return data if data else {}


def get_raw_recipe_ids() -> List[str]:
    """
    raw 디렉토리에 저장된 레시피 ID 목록 조회

    Returns:
        레시피 ID 리스트
    """
    recipes_dir = RAW_DIR / "recipes"
    if not recipes_dir.exists():
        return []

    recipe_ids = []
    for filepath in recipes_dir.glob("*.json"):
        recipe_id = filepath.stem
        recipe_ids.append(recipe_id)

    return recipe_ids


def load_raw_recipe(recipe_id: str) -> Optional[Dict[str, Any]]:
    """
    raw 디렉토리에서 레시피 로드

    Args:
        recipe_id: 레시피 ID

    Returns:
        레시피 딕셔너리 또는 None
    """
    filepath = RAW_DIR / "recipes" / f"{recipe_id}.json"
    return load_json(filepath)


def merge_recipe_data(raw_recipe: Dict[str, Any], processed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    원본 레시피와 전처리 데이터 병합

    Args:
        raw_recipe: 원본 레시피 데이터
        processed_data: 전처리된 데이터 (title_processed, recipe_source, steps_processed)

    Returns:
        병합된 레시피 딕셔너리
    """
    merged = raw_recipe.copy()
    merged.update(processed_data)
    return merged


def export_summary_json(recipes: List[Dict[str, Any]], filename: str = "recipes_summary.json") -> bool:
    """
    레시피 요약 정보만 JSON으로 내보내기 (용량 절약)

    Args:
        recipes: 레시피 리스트
        filename: 저장할 파일명

    Returns:
        성공 여부
    """
    summary_data = []

    for recipe in recipes:
        summary = {
            "recipe_id": recipe.get("recipe_id"),
            "title_original": recipe.get("title_original"),
            "title_processed": recipe.get("title_processed"),
            "recipe_source": recipe.get("recipe_source"),
            "author": recipe.get("author"),
            "servings": recipe.get("servings"),
            "cook_time": recipe.get("cook_time"),
            "difficulty": recipe.get("difficulty"),
            "rating": recipe.get("rating"),
            "cat_type": recipe.get("cat_type"),
            "cat_situation": recipe.get("cat_situation"),
            "cat_ingredient": recipe.get("cat_ingredient"),
            "cat_method": recipe.get("cat_method"),
            "ingredients_count": len(recipe.get("ingredients", [])),
            "steps_count": len(recipe.get("steps", [])),
        }
        summary_data.append(summary)

    filepath = PROCESSED_DIR / filename
    return save_json(summary_data, filepath)
