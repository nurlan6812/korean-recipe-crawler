"""
CSV 저장 핸들러
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PROCESSED_DIR
from utils.helpers import logger


def save_recipes_to_csv(recipes: List[Dict[str, Any]], filename: str = "recipes.csv") -> bool:
    """
    레시피 목록을 CSV로 저장

    Args:
        recipes: 레시피 딕셔너리 리스트
        filename: 저장할 파일명

    Returns:
        성공 여부
    """
    if not recipes:
        logger.warning("저장할 레시피가 없습니다")
        return False

    try:
        # 메인 레시피 정보 추출
        main_data = []
        for recipe in recipes:
            row = {
                "recipe_id": recipe.get("recipe_id"),
                "title_original": recipe.get("title_original"),
                "title_processed": recipe.get("title_processed"),
                "recipe_source": recipe.get("recipe_source"),
                "description": recipe.get("description"),
                "author": recipe.get("author"),
                "servings": recipe.get("servings"),
                "cook_time": recipe.get("cook_time"),
                "difficulty": recipe.get("difficulty"),
                "rating": recipe.get("rating"),
                "tips": recipe.get("tips"),
                "main_image_url": recipe.get("main_image_url"),
                "cat_type": recipe.get("cat_type"),
                "cat_situation": recipe.get("cat_situation"),
                "cat_ingredient": recipe.get("cat_ingredient"),
                "cat_method": recipe.get("cat_method"),
                # 재료와 단계는 JSON 문자열로 저장
                "ingredients_json": json.dumps(recipe.get("ingredients", []), ensure_ascii=False),
                "steps_json": json.dumps(recipe.get("steps", []), ensure_ascii=False),
                "steps_processed_json": json.dumps(recipe.get("steps_processed", []), ensure_ascii=False),
            }
            main_data.append(row)

        df = pd.DataFrame(main_data)
        filepath = PROCESSED_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"레시피 CSV 저장 완료: {filepath} ({len(recipes)}개)")

        return True

    except Exception as e:
        logger.error(f"CSV 저장 실패: {e}")
        return False


def save_ingredients_to_csv(recipes: List[Dict[str, Any]], filename: str = "ingredients.csv") -> bool:
    """
    재료 정보를 별도 CSV로 저장 (정규화)

    Args:
        recipes: 레시피 딕셔너리 리스트
        filename: 저장할 파일명
    """
    try:
        data = []
        for recipe in recipes:
            recipe_id = recipe.get("recipe_id")
            ingredients = recipe.get("ingredients", [])

            for ing in ingredients:
                data.append({
                    "recipe_id": recipe_id,
                    "ingredient_name": ing.get("name"),
                    "ingredient_amount": ing.get("amount"),
                })

        if not data:
            logger.warning("저장할 재료 데이터가 없습니다")
            return False

        df = pd.DataFrame(data)
        filepath = PROCESSED_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"재료 CSV 저장 완료: {filepath} ({len(data)}개)")

        return True

    except Exception as e:
        logger.error(f"재료 CSV 저장 실패: {e}")
        return False


def save_steps_to_csv(recipes: List[Dict[str, Any]], filename: str = "steps.csv") -> bool:
    """
    조리 순서를 별도 CSV로 저장 (정규화)

    Args:
        recipes: 레시피 딕셔너리 리스트
        filename: 저장할 파일명
    """
    try:
        data = []
        for recipe in recipes:
            recipe_id = recipe.get("recipe_id")
            steps = recipe.get("steps", [])
            steps_processed = recipe.get("steps_processed", [])

            for step in steps:
                step_num = step.get("step_num")

                # 전처리된 단계 찾기
                processed_desc = ""
                for ps in steps_processed:
                    if ps.get("step_num") == step_num:
                        processed_desc = ps.get("description", "")
                        break

                data.append({
                    "recipe_id": recipe_id,
                    "step_num": step_num,
                    "description": step.get("description"),
                    "description_processed": processed_desc,
                    "image_url": step.get("image_url"),
                })

        if not data:
            logger.warning("저장할 조리 순서 데이터가 없습니다")
            return False

        df = pd.DataFrame(data)
        filepath = PROCESSED_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"조리순서 CSV 저장 완료: {filepath} ({len(data)}개)")

        return True

    except Exception as e:
        logger.error(f"조리순서 CSV 저장 실패: {e}")
        return False


def save_categories_to_csv(categories: Dict[str, List[Dict]], filename: str = "categories.csv") -> bool:
    """
    카테고리 정보를 CSV로 저장

    Args:
        categories: 카테고리 딕셔너리
        filename: 저장할 파일명
    """
    try:
        data = []
        for field, items in categories.items():
            for item in items:
                data.append({
                    "category_type": field,
                    "code": item.get("code"),
                    "name": item.get("name"),
                })

        if not data:
            logger.warning("저장할 카테고리 데이터가 없습니다")
            return False

        df = pd.DataFrame(data)
        filepath = PROCESSED_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info(f"카테고리 CSV 저장 완료: {filepath} ({len(data)}개)")

        return True

    except Exception as e:
        logger.error(f"카테고리 CSV 저장 실패: {e}")
        return False


def load_recipes_from_csv(filename: str = "recipes.csv") -> List[Dict[str, Any]]:
    """CSV에서 레시피 로드"""
    try:
        filepath = PROCESSED_DIR / filename
        if not filepath.exists():
            return []

        df = pd.read_csv(filepath, encoding="utf-8-sig")

        recipes = []
        for _, row in df.iterrows():
            recipe = row.to_dict()

            # JSON 문자열을 파싱
            if "ingredients_json" in recipe and pd.notna(recipe["ingredients_json"]):
                recipe["ingredients"] = json.loads(recipe["ingredients_json"])
            if "steps_json" in recipe and pd.notna(recipe["steps_json"]):
                recipe["steps"] = json.loads(recipe["steps_json"])
            if "steps_processed_json" in recipe and pd.notna(recipe["steps_processed_json"]):
                recipe["steps_processed"] = json.loads(recipe["steps_processed_json"])

            recipes.append(recipe)

        return recipes

    except Exception as e:
        logger.error(f"CSV 로드 실패: {e}")
        return []


def append_recipe_to_csv(recipe: Dict[str, Any], filename: str = "recipes.csv") -> bool:
    """단일 레시피를 CSV에 추가 (append 모드)"""
    try:
        filepath = PROCESSED_DIR / filename

        row = {
            "recipe_id": recipe.get("recipe_id"),
            "title_original": recipe.get("title_original"),
            "title_processed": recipe.get("title_processed"),
            "recipe_source": recipe.get("recipe_source"),
            "description": recipe.get("description"),
            "author": recipe.get("author"),
            "servings": recipe.get("servings"),
            "cook_time": recipe.get("cook_time"),
            "difficulty": recipe.get("difficulty"),
            "rating": recipe.get("rating"),
            "tips": recipe.get("tips"),
            "main_image_url": recipe.get("main_image_url"),
            "cat_type": recipe.get("cat_type"),
            "cat_situation": recipe.get("cat_situation"),
            "cat_ingredient": recipe.get("cat_ingredient"),
            "cat_method": recipe.get("cat_method"),
            "ingredients_json": json.dumps(recipe.get("ingredients", []), ensure_ascii=False),
            "steps_json": json.dumps(recipe.get("steps", []), ensure_ascii=False),
            "steps_processed_json": json.dumps(recipe.get("steps_processed", []), ensure_ascii=False),
        }

        df = pd.DataFrame([row])

        # 파일이 없으면 새로 생성, 있으면 append
        if filepath.exists():
            df.to_csv(filepath, mode='a', header=False, index=False, encoding="utf-8-sig")
        else:
            df.to_csv(filepath, index=False, encoding="utf-8-sig")

        return True

    except Exception as e:
        logger.error(f"레시피 추가 실패: {e}")
        return False
