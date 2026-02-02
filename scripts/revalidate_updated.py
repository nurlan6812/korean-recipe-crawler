"""
수정된 53,381개 재검증
- 원본 제목 + 현재 food_name + 레시피 내용 함께 입력
- 잘못 수정된 케이스 (모음→단일) 삭제
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import re
import time
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai

# ===== 설정 =====
API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY 환경변수를 설정하세요")

MAX_WORKERS = 10
BATCH_SIZE = 500
MAX_RETRIES = 3
SAVE_INTERVAL = 100

RAW_DIR = PROJECT_ROOT / "data/raw/recipes"
REFINED_DIR = PROJECT_ROOT / "data/processed/recipes_refined"
CHECKPOINT_FILE = PROJECT_ROOT / "data/processed/checkpoint_revalidation.json"
VALIDATION_CHECKPOINT = PROJECT_ROOT / "data/processed/checkpoint_validation.json"

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'processed_ids': [],
        'deleted_ids': [],
        'kept_ids': [],
        'total_processed': 0,
        'last_updated': None
    }


def save_checkpoint(checkpoint):
    checkpoint['last_updated'] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def get_updated_ids():
    """이전 검증에서 수정된 ID 목록 가져오기"""
    with open(VALIDATION_CHECKPOINT, 'r', encoding='utf-8') as f:
        cp = json.load(f)
    return cp.get('updated_ids', [])


def validate_one(rid, retry_count=0):
    """단일 레시피 재검증"""
    try:
        raw_file = RAW_DIR / f'{rid}.json'
        refined_file = REFINED_DIR / f'{rid}.json'

        if not raw_file.exists() or not refined_file.exists():
            return {'recipe_id': rid, 'action': 'skip', 'success': True}

        with open(raw_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        with open(refined_file, 'r', encoding='utf-8') as f:
            refined_data = json.load(f)

        original_title = raw_data.get('title_original', '')
        current_name = refined_data.get('food_name', '')
        steps = refined_data.get('steps', [])
        steps_text = '\n'.join([f"- {s}" for s in steps[:5]])

        prompt = f'''레시피 검증

[원본 제목]
{original_title}

[현재 음식명]
{current_name}

[레시피 내용]
{steps_text}

[판단 기준]
1. 원본이 여러 음식 모음인데 단일 음식으로 잘못 변환됨 → DELETE
   예: "가지요리 6종세트" → "돼지고기 가지볶음" (잘못됨, DELETE)
   예: "반찬 3가지" → "어묵볶음" (잘못됨, DELETE)

2. 원본이 단일 음식인데 수식어만 제거됨 → OK
   예: "백종원 김치찌개" → "김치찌개" (정상, OK)
   예: "초간단 된장찌개" → "된장찌개" (정상, OK)

3. 레시피 내용이 실제로 여러 음식을 다루면 → DELETE

[출력]
OK 또는 DELETE만 출력'''

        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 50}
        )
        result = response.text.strip().upper()

        action = 'delete' if 'DELETE' in result else 'keep'

        return {
            'recipe_id': rid,
            'original_title': original_title,
            'current_name': current_name,
            'action': action,
            'success': True
        }

    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(2)
            return validate_one(rid, retry_count + 1)
        return {'recipe_id': rid, 'success': False, 'error': str(e)}


def process_batch(ids, checkpoint, batch_num, total_batches):
    """배치 처리"""
    results = {'keep': 0, 'delete': 0, 'skip': 0, 'failed': 0}
    batch_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(validate_one, rid): rid for rid in ids}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            rid = result['recipe_id']

            if not result.get('success'):
                results['failed'] += 1
            else:
                action = result['action']
                results[action] = results.get(action, 0) + 1

                if action == 'delete':
                    refined_file = REFINED_DIR / f'{rid}.json'
                    if refined_file.exists():
                        os.remove(refined_file)
                    checkpoint['deleted_ids'].append(rid)
                elif action == 'keep':
                    checkpoint['kept_ids'].append(rid)

            checkpoint['processed_ids'].append(rid)
            checkpoint['total_processed'] += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - batch_start
                speed = (i + 1) / elapsed
                print(f"\r  배치 {batch_num}/{total_batches}: {i+1}/{len(ids)} ({speed:.1f}/초)", end="", flush=True)

            if checkpoint['total_processed'] % SAVE_INTERVAL == 0:
                save_checkpoint(checkpoint)

    print()
    return results


def main():
    print("=" * 60)
    print("수정된 레시피 재검증 (잘못된 모음→단일 변환 찾기)")
    print("=" * 60)

    # 수정된 ID 목록
    updated_ids = get_updated_ids()
    print(f"수정된 레시피: {len(updated_ids)}개")

    # 체크포인트 로드
    checkpoint = load_checkpoint()
    processed_set = set(checkpoint['processed_ids'])

    print(f"이전 처리: {checkpoint['total_processed']}개")
    print(f"  - 유지: {len(checkpoint['kept_ids'])}개")
    print(f"  - 삭제: {len(checkpoint['deleted_ids'])}개")

    # 처리할 ID
    ids_to_process = [rid for rid in updated_ids if rid not in processed_set]
    total = len(ids_to_process)

    print(f"\n처리 대상: {total}개")

    if total == 0:
        print("처리할 레시피가 없습니다.")
        return

    batches = [ids_to_process[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"배치 수: {total_batches}개")
    print(f"예상 시간: {total / 4.5 / 60:.1f}분")
    print()

    start_time = time.time()
    total_results = {'keep': 0, 'delete': 0, 'skip': 0, 'failed': 0}

    for batch_num, batch_ids in enumerate(batches, 1):
        print(f"[배치 {batch_num}/{total_batches}] {len(batch_ids)}개...")

        try:
            results = process_batch(batch_ids, checkpoint, batch_num, total_batches)
            for k, v in results.items():
                total_results[k] = total_results.get(k, 0) + v

            print(f"  유지: {results['keep']} | 삭제: {results['delete']} | 실패: {results['failed']}")
            save_checkpoint(checkpoint)

            elapsed = time.time() - start_time
            remaining = (total - checkpoint['total_processed']) / (checkpoint['total_processed'] / elapsed) if checkpoint['total_processed'] > 0 else 0
            print(f"  진행: {checkpoint['total_processed']}/{total} | 경과: {elapsed/60:.1f}분 | 남은: {remaining/60:.1f}분")
            print()

        except KeyboardInterrupt:
            print("\n\n중단! 체크포인트 저장...")
            save_checkpoint(checkpoint)
            return

    elapsed = time.time() - start_time
    print("=" * 60)
    print("재검증 완료!")
    print(f"  총 처리: {checkpoint['total_processed']}개")
    print(f"  유지: {len(checkpoint['kept_ids'])}개")
    print(f"  삭제: {len(checkpoint['deleted_ids'])}개")
    print(f"  소요: {elapsed/60:.1f}분")
    print("=" * 60)


if __name__ == "__main__":
    main()
