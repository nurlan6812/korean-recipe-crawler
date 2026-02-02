"""
레시피 이미지 다운로드 스크립트
- 179,502개 레시피 이미지 다운로드
- 병렬 처리 + 체크포인트
"""

import json
import time
import os
import requests
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 설정 =====
MAX_WORKERS = 20
BATCH_SIZE = 1000
MAX_RETRIES = 3
SAVE_INTERVAL = 100
TIMEOUT = 10

REFINED_DIR = Path("data/processed/recipes_refined")
IMAGE_DIR = Path("data/images/recipes")
CHECKPOINT_FILE = Path("data/images/checkpoint_images.json")

IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'downloaded_ids': [],
        'failed_ids': [],
        'total_downloaded': 0,
        'total_failed': 0,
        'last_updated': None
    }


def save_checkpoint(checkpoint):
    checkpoint['last_updated'] = datetime.now().isoformat()
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def download_one(recipe_file, retry_count=0):
    """단일 이미지 다운로드"""
    try:
        with open(recipe_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        rid = data.get('recipe_id', recipe_file.stem)
        image_url = data.get('main_image_url', '')

        if not image_url:
            return {'recipe_id': rid, 'success': False, 'error': 'no_url'}

        # 확장자 추출
        ext = image_url.split('.')[-1].split('?')[0].lower()
        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            ext = 'jpg'

        image_path = IMAGE_DIR / f"{rid}.{ext}"

        # 이미 다운로드된 경우 스킵
        if image_path.exists():
            return {'recipe_id': rid, 'success': True, 'skipped': True}

        # 다운로드
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(image_url, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()

        with open(image_path, 'wb') as f:
            f.write(response.content)

        return {'recipe_id': rid, 'success': True, 'skipped': False}

    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(1)
            return download_one(recipe_file, retry_count + 1)
        return {
            'recipe_id': recipe_file.stem,
            'success': False,
            'error': str(e)
        }


def process_batch(files, checkpoint, batch_num, total_batches):
    """배치 처리"""
    results = {'success': 0, 'skipped': 0, 'failed': 0}
    batch_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, f): f for f in files}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            rid = result['recipe_id']

            if result.get('success'):
                if result.get('skipped'):
                    results['skipped'] += 1
                else:
                    results['success'] += 1
                checkpoint['downloaded_ids'].append(rid)
                checkpoint['total_downloaded'] += 1
            else:
                results['failed'] += 1
                checkpoint['failed_ids'].append(rid)
                checkpoint['total_failed'] += 1

            if (i + 1) % 100 == 0:
                elapsed = time.time() - batch_start
                speed = (i + 1) / elapsed
                print(f"\r  배치 {batch_num}/{total_batches}: {i+1}/{len(files)} ({speed:.1f}/초)", end="", flush=True)

            if (i + 1) % SAVE_INTERVAL == 0:
                save_checkpoint(checkpoint)

    print()
    return results


def main():
    print("=" * 60)
    print("레시피 이미지 다운로드")
    print("=" * 60)

    checkpoint = load_checkpoint()
    downloaded_set = set(checkpoint['downloaded_ids'])

    print(f"이전 다운로드: {checkpoint['total_downloaded']}개")
    print(f"  - 실패: {checkpoint['total_failed']}개")

    # 처리할 파일 목록
    all_files = list(REFINED_DIR.glob('*.json'))
    files_to_process = [f for f in all_files if f.stem not in downloaded_set]

    total = len(files_to_process)
    print(f"\n처리 대상: {total}개 (전체 {len(all_files)}개)")

    if total == 0:
        print("처리할 파일이 없습니다.")
        return

    batches = [files_to_process[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"배치 수: {total_batches}개")
    print(f"동시 다운로드: {MAX_WORKERS}개")
    print()

    start_time = time.time()
    total_results = {'success': 0, 'skipped': 0, 'failed': 0}

    for batch_num, batch_files in enumerate(batches, 1):
        print(f"[배치 {batch_num}/{total_batches}] {len(batch_files)}개...")

        try:
            results = process_batch(batch_files, checkpoint, batch_num, total_batches)
            for k, v in results.items():
                total_results[k] += v

            print(f"  성공: {results['success']} | 스킵: {results['skipped']} | 실패: {results['failed']}")
            save_checkpoint(checkpoint)

            elapsed = time.time() - start_time
            done = checkpoint['total_downloaded']
            remaining = (total - done) / (done / elapsed) if done > 0 else 0
            print(f"  진행: {done}/{total} | 경과: {elapsed/60:.1f}분 | 남은: {remaining/60:.1f}분")
            print()

        except KeyboardInterrupt:
            print("\n\n중단! 체크포인트 저장...")
            save_checkpoint(checkpoint)
            return

    elapsed = time.time() - start_time
    print("=" * 60)
    print("다운로드 완료!")
    print(f"  총 다운로드: {checkpoint['total_downloaded']}개")
    print(f"  성공: {total_results['success']}개")
    print(f"  스킵: {total_results['skipped']}개")
    print(f"  실패: {checkpoint['total_failed']}개")
    print(f"  소요: {elapsed/60:.1f}분")
    print(f"\n이미지 저장: {IMAGE_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
