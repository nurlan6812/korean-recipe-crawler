"""
만개의 레시피 크롤러 - 메인 실행 파일
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import asyncio
import aiohttp
import aiofiles
from typing import Set, List
from tqdm import tqdm

from config.settings import (
    CHECKPOINT_FILE, FAILED_IDS_FILE,
    RAW_DIR, IMAGES_DIR, REQUEST_DELAY
)
from src.crawlers.category_crawler import crawl_categories
from src.crawlers.recipe_crawler import (
    get_total_pages, crawl_recipe_list,
    crawl_recipe_detail, save_recipe
)
from src.storage.csv_handler import (
    save_recipes_to_csv, save_ingredients_to_csv,
    save_steps_to_csv, save_categories_to_csv, append_recipe_to_csv
)
from src.storage.json_handler import (
    save_recipe_json, save_categories_json, get_raw_recipe_ids
)
from src.utils.helpers import (
    logger, Checkpoint, save_json, load_json, clean_image_url
)


def crawl_all_recipes(start_page: int = 1, end_page: int = None, save_interval: int = 100):
    """
    전체 레시피 크롤링

    Args:
        start_page: 시작 페이지
        end_page: 종료 페이지 (None이면 끝까지)
        save_interval: 저장 간격 (N개마다 CSV 저장)
    """
    logger.info("=== 만개의 레시피 크롤링 시작 ===")

    # 체크포인트 로드
    checkpoint = Checkpoint(CHECKPOINT_FILE)
    if checkpoint.last_page > 0 and start_page == 1:
        start_page = checkpoint.last_page + 1
        logger.info(f"체크포인트에서 재개: {start_page} 페이지부터")

    # 전체 페이지 수 확인
    total_pages = get_total_pages()
    if end_page is None or end_page > total_pages:
        end_page = total_pages

    logger.info(f"크롤링 범위: {start_page} ~ {end_page} 페이지")

    # 이미 크롤링된 ID 로드
    crawled_ids: Set[str] = set(checkpoint.data.get("crawled_ids", []))
    logger.info(f"이미 크롤링된 레시피: {len(crawled_ids)}개")

    # 실패한 ID 로드
    failed_ids: Set[str] = set(load_json(FAILED_IDS_FILE) or [])

    # raw 레시피 디렉토리 생성
    (RAW_DIR / "recipes").mkdir(parents=True, exist_ok=True)

    # 크롤링 진행
    new_recipes_count = 0
    batch_recipes = []

    try:
        for page in tqdm(range(start_page, end_page + 1), desc="페이지 크롤링"):
            # 목록 페이지에서 레시피 ID 수집
            recipe_list = crawl_recipe_list(page)

            for recipe_info in recipe_list:
                recipe_id = recipe_info.get("recipe_id")

                if not recipe_id:
                    continue

                # 이미 크롤링된 경우 스킵
                if recipe_id in crawled_ids:
                    continue

                # 상세 정보 크롤링
                detail = crawl_recipe_detail(recipe_id)

                if detail:
                    # raw 데이터 저장
                    save_recipe(detail)

                    crawled_ids.add(recipe_id)
                    checkpoint.add_recipe_id(recipe_id)
                    new_recipes_count += 1
                    batch_recipes.append(detail)

                    # 실패 목록에서 제거
                    if recipe_id in failed_ids:
                        failed_ids.discard(recipe_id)

                else:
                    failed_ids.add(recipe_id)
                    logger.warning(f"레시피 크롤링 실패: {recipe_id}")

            # 페이지 완료 시 체크포인트 저장
            checkpoint.update_page(page)

            # 주기적으로 CSV 저장
            if new_recipes_count > 0 and new_recipes_count % save_interval == 0:
                logger.info(f"중간 저장: {new_recipes_count}개 완료")
                _save_batch_to_csv(batch_recipes)
                batch_recipes = []

    except KeyboardInterrupt:
        logger.info("\n크롤링 중단됨 (Ctrl+C)")

    finally:
        # 최종 저장
        checkpoint.save()
        save_json(list(failed_ids), FAILED_IDS_FILE)

        if batch_recipes:
            _save_batch_to_csv(batch_recipes)

        logger.info(f"=== 크롤링 완료 ===")
        logger.info(f"새로 크롤링된 레시피: {new_recipes_count}개")
        logger.info(f"총 크롤링된 레시피: {len(crawled_ids)}개")
        logger.info(f"실패한 레시피: {len(failed_ids)}개")


def _save_batch_to_csv(recipes: List[dict]):
    """배치 레시피를 CSV에 추가"""
    for recipe in recipes:
        append_recipe_to_csv(recipe)


def retry_failed():
    """실패한 레시피 재시도"""
    logger.info("=== 실패한 레시피 재시도 ===")

    failed_ids = load_json(FAILED_IDS_FILE) or []
    if not failed_ids:
        logger.info("재시도할 레시피가 없습니다")
        return

    logger.info(f"재시도 대상: {len(failed_ids)}개")

    success_ids = []
    still_failed = []

    for recipe_id in tqdm(failed_ids, desc="재시도"):
        detail = crawl_recipe_detail(recipe_id)

        if detail:
            save_recipe(detail)
            append_recipe_to_csv(detail)
            success_ids.append(recipe_id)
        else:
            still_failed.append(recipe_id)

    # 실패 목록 업데이트
    save_json(still_failed, FAILED_IDS_FILE)

    logger.info(f"성공: {len(success_ids)}개, 여전히 실패: {len(still_failed)}개")


async def download_image(session: aiohttp.ClientSession, url: str, filepath: Path) -> bool:
    """비동기 이미지 다운로드"""
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                content = await response.read()
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(content)
                return True
    except Exception as e:
        logger.debug(f"이미지 다운로드 실패: {url} - {e}")
    return False


async def download_images_batch(image_tasks: List[tuple], max_concurrent: int = 10):
    """배치 이미지 다운로드"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_semaphore(session, url, filepath):
        async with semaphore:
            await asyncio.sleep(0.1)  # 요청 간격
            return await download_image(session, url, filepath)

    async with aiohttp.ClientSession() as session:
        tasks = [
            download_with_semaphore(session, url, filepath)
            for url, filepath in image_tasks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results


def download_all_images():
    """모든 레시피 이미지 다운로드"""
    logger.info("=== 이미지 다운로드 시작 ===")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 크롤링된 레시피 ID 목록
    recipe_ids = get_raw_recipe_ids()
    logger.info(f"총 {len(recipe_ids)}개 레시피 이미지 다운로드")

    # 이미지 다운로드 태스크 생성
    image_tasks = []

    for recipe_id in recipe_ids:
        filepath = IMAGES_DIR / f"{recipe_id}.jpg"

        # 이미 다운로드된 경우 스킵
        if filepath.exists():
            continue

        # raw 데이터에서 이미지 URL 가져오기
        recipe_data = load_json(RAW_DIR / "recipes" / f"{recipe_id}.json")
        if recipe_data:
            img_url = recipe_data.get("main_image_url")
            if img_url:
                # 원본 URL로 변환
                img_url = clean_image_url(img_url)
                image_tasks.append((img_url, filepath))

    if not image_tasks:
        logger.info("다운로드할 이미지가 없습니다")
        return

    logger.info(f"다운로드 대상: {len(image_tasks)}개")

    # 비동기 다운로드
    asyncio.run(download_images_batch(image_tasks))

    logger.info("=== 이미지 다운로드 완료 ===")


def export_data():
    """크롤링 데이터 내보내기 (CSV + JSON)"""
    logger.info("=== 데이터 내보내기 ===")

    # 카테고리 크롤링 및 저장
    categories = crawl_categories()
    save_categories_csv_result = save_categories_to_csv(categories)
    save_categories_json(categories)

    # 크롤링된 모든 레시피 로드
    recipe_ids = get_raw_recipe_ids()
    logger.info(f"총 {len(recipe_ids)}개 레시피 내보내기")

    all_recipes = []
    for recipe_id in tqdm(recipe_ids, desc="레시피 로드"):
        recipe_data = load_json(RAW_DIR / "recipes" / f"{recipe_id}.json")
        if recipe_data:
            all_recipes.append(recipe_data)

    # CSV 저장
    save_recipes_to_csv(all_recipes)
    save_ingredients_to_csv(all_recipes)
    save_steps_to_csv(all_recipes)

    logger.info("=== 내보내기 완료 ===")


def main():
    parser = argparse.ArgumentParser(description="만개의 레시피 크롤러")

    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # crawl 명령어
    crawl_parser = subparsers.add_parser("crawl", help="레시피 크롤링")
    crawl_parser.add_argument("--start", type=int, default=1, help="시작 페이지")
    crawl_parser.add_argument("--end", type=int, default=None, help="종료 페이지")
    crawl_parser.add_argument("--interval", type=int, default=100, help="저장 간격")

    # retry 명령어
    subparsers.add_parser("retry", help="실패한 레시피 재시도")

    # images 명령어
    subparsers.add_parser("images", help="이미지 다운로드")

    # export 명령어
    subparsers.add_parser("export", help="데이터 내보내기")

    # categories 명령어
    subparsers.add_parser("categories", help="카테고리만 크롤링")

    # status 명령어
    subparsers.add_parser("status", help="크롤링 상태 확인")

    args = parser.parse_args()

    if args.command == "crawl":
        crawl_all_recipes(
            start_page=args.start,
            end_page=args.end,
            save_interval=args.interval
        )

    elif args.command == "retry":
        retry_failed()

    elif args.command == "images":
        download_all_images()

    elif args.command == "export":
        export_data()

    elif args.command == "categories":
        categories = crawl_categories()
        save_categories_json(categories)
        save_categories_to_csv(categories)

    elif args.command == "status":
        checkpoint = Checkpoint(CHECKPOINT_FILE)
        failed_ids = load_json(FAILED_IDS_FILE) or []
        recipe_ids = get_raw_recipe_ids()

        print("\n=== 크롤링 상태 ===")
        print(f"마지막 크롤링 페이지: {checkpoint.last_page}")
        print(f"크롤링된 레시피 수: {len(recipe_ids)}")
        print(f"실패한 레시피 수: {len(failed_ids)}")

        # 이미지 다운로드 상태
        downloaded_images = len(list(IMAGES_DIR.glob("*.jpg")))
        print(f"다운로드된 이미지: {downloaded_images}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
