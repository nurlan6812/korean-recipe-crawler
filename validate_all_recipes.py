"""
전체 레시피 음식명 재검증 스크립트
- 이미 정제된 18만개 대상
- 음식명 + 레시피(steps) 함께 검증
- 수식어 제거, 복수 음식 판별
"""

import json
import re
import time
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai

# ===== 설정 =====
API_KEY = "AIzaSyDCuaCq5bo4-8PrGTuYEOLoUz3fLwxXzQ8"
MAX_WORKERS = 10
BATCH_SIZE = 500
MAX_RETRIES = 3
SAVE_INTERVAL = 100

INPUT_DIR = Path("data/processed/recipes_refined")
CHECKPOINT_FILE = Path("data/processed/checkpoint_validation.json")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'processed_ids': [],
        'deleted_ids': [],
        'updated_ids': [],
        'total_processed': 0,
        'last_updated': None
    }


def save_checkpoint(checkpoint):
    checkpoint['last_updated'] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def validate_one(file_path, retry_count=0):
    """단일 레시피 검증"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        name = data.get('food_name', '') or ''
        rid = data.get('recipe_id', file_path.stem)
        steps = data.get('steps', [])

        # steps를 텍스트로 변환
        steps_text = '\n'.join([f"- {s}" for s in steps[:5]])  # 앞 5개만

        prompt = f'''음식명 검증

[현재 음식명]
{name}

[레시피 내용]
{steps_text}

[규칙]
1. 수식어 제거
   - 만능, 초간단, 초스피드, 간단, 쉬운, 꿀맛, 대박, 존맛, N분, N색, HACCP 등
   - 예: "만능 야채참치" → "야채참치"

2. 슬래시(/) 처리
   - 같은 종류면 대표명: "돼지국밥/순대국밥" → "돼지국밥"
   - 레시피 내용 보고 판단

3. 쉼표(,) 처리
   - 레시피가 하나의 요리면 대표명 선택
   - 완전히 다른 여러 요리면 DELETE

4. 레시피 내용과 음식명이 안 맞으면 레시피 기준으로 수정

5. 유효하지 않으면 DELETE (빈 값, 모음집, N가지 등)

[출력]
정제된 음식명만 출력. 삭제 대상이면 DELETE만 출력.'''

        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 100}
        )
        result = response.text.strip()

        # DELETE 또는 정제된 이름
        clean_name = result.replace('"', '').replace("'", "").strip()

        # 여러 줄이면 첫 줄만
        if '\n' in clean_name:
            clean_name = clean_name.split('\n')[0].strip()

        return {
            'recipe_id': rid,
            'file': str(file_path),
            'original_name': name,
            'clean_name': clean_name,
            'action': 'delete' if clean_name.upper() == 'DELETE' else ('update' if clean_name != name else 'keep'),
            'success': True
        }

    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(2)
            return validate_one(file_path, retry_count + 1)
        return {
            'recipe_id': file_path.stem,
            'file': str(file_path),
            'success': False,
            'error': str(e)
        }


def process_batch(files, checkpoint, batch_num, total_batches):
    """배치 처리"""
    results = {'keep': 0, 'update': 0, 'delete': 0, 'failed': 0}
    batch_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(validate_one, f): f for f in files}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            rid = result['recipe_id']

            if not result.get('success'):
                results['failed'] += 1
            else:
                action = result['action']
                results[action] += 1

                if action == 'delete':
                    os.remove(result['file'])
                    checkpoint['deleted_ids'].append(rid)
                elif action == 'update':
                    with open(result['file'], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data['food_name'] = result['clean_name']
                    with open(result['file'], 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    checkpoint['updated_ids'].append(rid)

            checkpoint['processed_ids'].append(rid)
            checkpoint['total_processed'] += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - batch_start
                speed = (i + 1) / elapsed
                print(f"\r  배치 {batch_num}/{total_batches}: {i+1}/{len(files)} ({speed:.1f}/초)", end="", flush=True)

            if checkpoint['total_processed'] % SAVE_INTERVAL == 0:
                save_checkpoint(checkpoint)

    print()
    return results


def main():
    print("=" * 60)
    print("전체 레시피 음식명 재검증 (음식명 + 레시피 내용)")
    print("=" * 60)

    checkpoint = load_checkpoint()
    processed_set = set(checkpoint['processed_ids'])

    print(f"이전 처리: {checkpoint['total_processed']}개")
    print(f"  - 삭제: {len(checkpoint['deleted_ids'])}개")
    print(f"  - 수정: {len(checkpoint['updated_ids'])}개")

    # 처리할 파일 목록
    all_files = list(INPUT_DIR.glob('*.json'))
    files_to_process = [f for f in all_files if f.stem not in processed_set]

    total = len(files_to_process)
    print(f"\n처리 대상: {total}개 (전체 {len(all_files)}개)")

    if total == 0:
        print("처리할 파일이 없습니다.")
        return

    batches = [files_to_process[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"배치 수: {total_batches}개")
    print(f"예상 시간: {total / 4.5 / 60:.1f}분 (약 {total / 4.5 / 3600:.1f}시간)")
    print()

    start_time = time.time()
    total_results = {'keep': 0, 'update': 0, 'delete': 0, 'failed': 0}

    for batch_num, batch_files in enumerate(batches, 1):
        print(f"[배치 {batch_num}/{total_batches}] {len(batch_files)}개...")

        try:
            results = process_batch(batch_files, checkpoint, batch_num, total_batches)
            for k, v in results.items():
                total_results[k] += v

            print(f"  유지: {results['keep']} | 수정: {results['update']} | 삭제: {results['delete']} | 실패: {results['failed']}")
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
    print("검증 완료!")
    print(f"  총 처리: {checkpoint['total_processed']}개")
    print(f"  유지: {total_results['keep']}개")
    print(f"  수정: {total_results['update']}개")
    print(f"  삭제: {len(checkpoint['deleted_ids'])}개")
    print(f"  소요: {elapsed/60:.1f}분 ({elapsed/3600:.2f}시간)")
    print("=" * 60)


if __name__ == "__main__":
    main()
