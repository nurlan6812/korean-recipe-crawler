"""
전처리 실행 스크립트
크롤링 완료 후 LLM을 사용하여 데이터 전처리
"""
import argparse
from pathlib import Path
from typing import List, Dict, Any
from tqdm import tqdm

from config.settings import RAW_DIR, PROCESSED_DIR
from processors.llm_processor import LLMProcessor, GeminiProcessor, RuleBasedProcessor
from storage.json_handler import (
    load_raw_recipe, get_raw_recipe_ids,
    save_recipe_json, load_recipe_json
)
from storage.csv_handler import save_recipes_to_csv, save_ingredients_to_csv, save_steps_to_csv
from utils.helpers import logger, load_json, save_json


def process_with_llm(recipe_ids: List[str] = None, batch_size: int = 100):
    """
    LLM을 사용하여 레시피 전처리

    Args:
        recipe_ids: 처리할 레시피 ID 리스트 (None이면 전체)
        batch_size: 배치 크기
    """
    logger.info("=== LLM 전처리 시작 ===")

    # 처리할 레시피 ID 목록
    if recipe_ids is None:
        recipe_ids = get_raw_recipe_ids()

    logger.info(f"처리 대상: {len(recipe_ids)}개 레시피")

    # 이미 전처리된 레시피 확인
    processed_dir = PROCESSED_DIR / "recipes"
    processed_dir.mkdir(parents=True, exist_ok=True)

    already_processed = set()
    for f in processed_dir.glob("*.json"):
        already_processed.add(f.stem)

    to_process = [rid for rid in recipe_ids if rid not in already_processed]
    logger.info(f"새로 처리할 레시피: {len(to_process)}개 (이미 처리됨: {len(already_processed)}개)")

    if not to_process:
        logger.info("처리할 레시피가 없습니다")
        return

    # LLM 프로세서 초기화
    processor = LLMProcessor()
    processor.load_model()

    try:
        # 개별 레시피 단위로 처리
        for recipe_id in tqdm(to_process, desc="LLM 전처리"):
            try:
                # 원본 데이터 로드
                recipe = load_raw_recipe(recipe_id)
                if not recipe:
                    continue

                # 전처리
                processed = processor.process_recipe(recipe)

                # 저장
                save_recipe_json(processed)

            except Exception as e:
                logger.error(f"레시피 처리 실패 (ID: {recipe_id}): {e}")

    finally:
        # 모델 언로드
        processor.unload_model()

    logger.info("=== LLM 전처리 완료 ===")


def process_with_gemini(recipe_ids: List[str] = None, num_workers: int = 10):
    """
    Gemini API로 레시피 전처리 (병렬 처리)

    Args:
        recipe_ids: 처리할 레시피 ID 리스트 (None이면 전체)
        num_workers: 병렬 워커 수 (기본 10)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.info("=== Gemini 전처리 시작 ===")

    if recipe_ids is None:
        recipe_ids = get_raw_recipe_ids()

    logger.info(f"처리 대상: {len(recipe_ids)}개 레시피")

    # 이미 전처리된 레시피 확인
    processed_dir = PROCESSED_DIR / "recipes"
    processed_dir.mkdir(parents=True, exist_ok=True)

    already_processed = set()
    for f in processed_dir.glob("*.json"):
        already_processed.add(f.stem)

    to_process = [rid for rid in recipe_ids if rid not in already_processed]
    logger.info(f"새로 처리할 레시피: {len(to_process)}개 (이미 처리됨: {len(already_processed)}개)")

    if not to_process:
        logger.info("처리할 레시피가 없습니다")
        return

    # Gemini 프로세서 초기화
    processor = GeminiProcessor()
    processor.load_model()

    success_count = 0
    fail_count = 0

    def process_one(recipe_id: str) -> bool:
        """단일 레시피 처리"""
        try:
            recipe = load_raw_recipe(recipe_id)
            if not recipe:
                return False

            processed = processor.process_recipe(recipe)
            save_recipe_json(processed)
            return True
        except Exception as e:
            logger.error(f"레시피 처리 실패 (ID: {recipe_id}): {e}")
            return False

    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(process_one, rid): rid for rid in to_process}

            for future in tqdm(as_completed(futures), total=len(to_process), desc="Gemini 전처리"):
                if future.result():
                    success_count += 1
                else:
                    fail_count += 1

    finally:
        processor.unload_model()

    logger.info(f"=== Gemini 전처리 완료 ===")
    logger.info(f"성공: {success_count}개, 실패: {fail_count}개")


def process_with_rules(recipe_ids: List[str] = None):
    """
    규칙 기반으로 레시피 전처리 (LLM 없이)

    Args:
        recipe_ids: 처리할 레시피 ID 리스트 (None이면 전체)
    """
    logger.info("=== 규칙 기반 전처리 시작 ===")

    if recipe_ids is None:
        recipe_ids = get_raw_recipe_ids()

    logger.info(f"처리 대상: {len(recipe_ids)}개 레시피")

    processed_dir = PROCESSED_DIR / "recipes"
    processed_dir.mkdir(parents=True, exist_ok=True)

    for recipe_id in tqdm(recipe_ids, desc="전처리"):
        try:
            # 원본 데이터 로드
            recipe = load_raw_recipe(recipe_id)
            if not recipe:
                continue

            # 제목 전처리
            title = recipe.get("title_original", "")
            if title:
                title_result = RuleBasedProcessor.process_title(title)
                recipe["title_processed"] = title_result.get("food_name")
                recipe["recipe_source"] = title_result.get("recipe_source")

            # 조리 순서는 원본 그대로 (규칙 기반에서는 처리 안 함)
            recipe["steps_processed"] = recipe.get("steps", [])

            # 저장
            save_recipe_json(recipe)

        except Exception as e:
            logger.error(f"레시피 처리 실패 (ID: {recipe_id}): {e}")

    logger.info("=== 규칙 기반 전처리 완료 ===")


def export_processed_data():
    """전처리된 데이터를 CSV로 내보내기"""
    logger.info("=== 전처리 데이터 내보내기 ===")

    processed_dir = PROCESSED_DIR / "recipes"

    # 전처리된 레시피 로드
    recipes = []
    for filepath in tqdm(list(processed_dir.glob("*.json")), desc="레시피 로드"):
        data = load_json(filepath)
        if data:
            recipes.append(data)

    logger.info(f"로드된 레시피: {len(recipes)}개")

    if not recipes:
        logger.warning("내보낼 레시피가 없습니다")
        return

    # CSV 저장
    save_recipes_to_csv(recipes, "recipes_processed.csv")
    save_ingredients_to_csv(recipes, "ingredients_processed.csv")
    save_steps_to_csv(recipes, "steps_processed.csv")

    logger.info("=== 내보내기 완료 ===")


def get_processing_status():
    """전처리 상태 확인"""
    raw_ids = set(get_raw_recipe_ids())

    processed_dir = PROCESSED_DIR / "recipes"
    processed_ids = set()
    if processed_dir.exists():
        for f in processed_dir.glob("*.json"):
            processed_ids.add(f.stem)

    print("\n=== 전처리 상태 ===")
    print(f"크롤링된 레시피: {len(raw_ids)}개")
    print(f"전처리된 레시피: {len(processed_ids)}개")
    print(f"미처리 레시피: {len(raw_ids - processed_ids)}개")


def main():
    parser = argparse.ArgumentParser(description="레시피 데이터 전처리")

    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # llm 명령어
    llm_parser = subparsers.add_parser("llm", help="LLM 기반 전처리 (Qwen)")
    llm_parser.add_argument("--batch-size", type=int, default=100, help="배치 크기")

    # gemini 명령어
    gemini_parser = subparsers.add_parser("gemini", help="Gemini API 기반 전처리")
    gemini_parser.add_argument("-w", "--workers", type=int, default=10, help="병렬 워커 수 (기본 10)")

    # rules 명령어
    subparsers.add_parser("rules", help="규칙 기반 전처리")

    # export 명령어
    subparsers.add_parser("export", help="CSV 내보내기")

    # status 명령어
    subparsers.add_parser("status", help="처리 상태 확인")

    # test 명령어 (규칙 기반 테스트)
    subparsers.add_parser("test", help="규칙 기반 전처리 테스트")

    args = parser.parse_args()

    if args.command == "llm":
        process_with_llm(batch_size=args.batch_size)

    elif args.command == "gemini":
        process_with_gemini(num_workers=args.workers)

    elif args.command == "rules":
        process_with_rules()

    elif args.command == "export":
        export_processed_data()

    elif args.command == "status":
        get_processing_status()

    elif args.command == "test":
        print("=== 규칙 기반 전처리 테스트 ===\n")
        test_titles = [
            "백종원의 돼지불백 만들기",
            "엄마표 김치찌개 황금레시피",
            "아삭하고 맛있는 오이고추된장무침 만들기",
            "초간단 10분 계란볶음밥 레시피",
            "맛있는 된장찌개",
            "할머니의 잡채 만드는 법",
        ]

        for title in test_titles:
            result = RuleBasedProcessor.process_title(title)
            print(f"원본: {title}")
            print(f"  -> 음식: {result['food_name']}")
            print(f"  -> 출처: {result['recipe_source']}")
            print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
