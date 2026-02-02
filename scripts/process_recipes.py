"""
레시피 전체 처리 스크립트
- 배치 처리 (1000개씩)
- 체크포인트 저장 (중간 저장)
- Rate limit 대응 (재시도 로직)
- 진행률 표시
- 이미 처리된 파일 스킵
"""
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import time
import re
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import google.generativeai as genai

# ===== 설정 =====
API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY 환경변수를 설정하세요")

MAX_WORKERS = 10          # 동시 처리 스레드 수
BATCH_SIZE = 1000         # 배치당 처리 개수
MAX_RETRIES = 3           # 실패시 재시도 횟수
RETRY_DELAY = 5           # 재시도 대기 시간(초)
SAVE_INTERVAL = 100       # N개마다 중간 저장

RAW_DIR = PROJECT_ROOT / "data/raw/recipes"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/recipes_refined"
CHECKPOINT_FILE = PROJECT_ROOT / "data/processed/checkpoint_refined.json"

# ===== 초기화 =====
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_checkpoint():
    """체크포인트 로드"""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'processed_ids': [],
        'failed_ids': [],
        'total_processed': 0,
        'total_success': 0,
        'total_failed': 0,
        'last_updated': None
    }


def save_checkpoint(checkpoint):
    """체크포인트 저장"""
    checkpoint['last_updated'] = datetime.now().isoformat()
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def check_yo_style(s):
    """해요체 체크"""
    clean = s.rstrip('.')
    return clean.endswith(('요', '세요', '어요', '아요'))


def parse_meta_from_description(desc):
    """description에서 인분/시간/난이도 파싱"""
    desc = desc or ''
    servings = re.search(r'(\d+인분(?:\s*이상)?)', desc)
    cook_time = re.search(r'(\d+분\s*이내|\d+시간\s*이내|\d+시간\s*이상)', desc)
    difficulty = re.search(r'(아무나|초급|중급|고급|신의경지)', desc)

    return {
        'servings': servings.group(1) if servings else None,
        'cook_time': cook_time.group(1) if cook_time else None,
        'difficulty': difficulty.group(1) if difficulty else None
    }


def process_one(file_path, retry_count=0):
    """단일 레시피 처리"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            recipe = json.load(f)

        recipe_id = recipe.get('recipe_id', '')
        title = recipe.get('title_original', '')
        steps = recipe.get('steps', [])

        # 원본 재료
        ingredients_raw = []
        for ing in recipe.get('ingredients', []):
            if isinstance(ing, dict):
                ingredients_raw.append({
                    'name': ing.get('name', ''),
                    'amount': ing.get('amount', '')
                })
            elif isinstance(ing, str):
                ingredients_raw.append({'name': ing, 'amount': ''})

        # 메타정보 파싱
        meta = parse_meta_from_description(recipe.get('description', ''))

        # 이미지/URL
        main_image_url = recipe.get('main_image_url', '')
        recipe_url = recipe.get('url', '')

        # steps 텍스트
        steps_text = ""
        for s in steps:
            desc = s.get("description", "") if isinstance(s, dict) else str(s)
            if desc:
                steps_text += f"- {desc}\n"

        prompt = f'''레시피 정제

[원본]
제목: {title}
재료: {', '.join([ing['name'] for ing in ingredients_raw[:10]])}
조리순서:
{steps_text}

[필수 규칙]
1. food_name: 핵심 음식명만 (하나만)
2. recipe_source: 유명인만 (없으면 null)
3. steps:
   - 문체: 모든 문장 "~요"로 끝내기
   - 금지: "~ㅂ니다", "~한다", "~줘"
   - 괄호() 절대 사용 금지! 괄호 내용은 삭제하거나 문장에 녹여야 함
   - 잡담/광고 제거
   - 연속된 짧은 단계 합치기

{{"food_name":"","recipe_source":null,"steps":[]}}'''

        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.1, "max_output_tokens": 2000}
        )
        result_text = response.text.strip()

        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return {
                'recipe_id': recipe_id,
                'success': True,
                'data': {
                    'recipe_id': recipe_id,
                    'food_name': parsed.get('food_name'),
                    'recipe_source': parsed.get('recipe_source'),
                    'servings': meta['servings'],
                    'cook_time': meta['cook_time'],
                    'difficulty': meta['difficulty'],
                    'main_image_url': main_image_url,
                    'recipe_url': recipe_url,
                    'ingredients': ingredients_raw,
                    'steps': parsed.get('steps', [])
                }
            }
        else:
            raise ValueError("JSON 파싱 실패")

    except Exception as e:
        if retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
            return process_one(file_path, retry_count + 1)
        return {
            'recipe_id': recipe.get('recipe_id', file_path.stem) if 'recipe' in dir() else file_path.stem,
            'success': False,
            'error': str(e)
        }


def save_result(result):
    """개별 결과 저장"""
    if result['success']:
        output_path = OUTPUT_DIR / f"{result['recipe_id']}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result['data'], f, ensure_ascii=False, indent=2)


def process_batch(files, checkpoint, batch_num, total_batches):
    """배치 처리"""
    results = {'success': 0, 'failed': 0}
    batch_start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, f): f for f in files}

        for i, future in enumerate(as_completed(futures)):
            result = future.result()

            if result['success']:
                results['success'] += 1
                checkpoint['total_success'] += 1
                save_result(result)
            else:
                results['failed'] += 1
                checkpoint['total_failed'] += 1
                checkpoint['failed_ids'].append(result['recipe_id'])

            checkpoint['processed_ids'].append(result['recipe_id'])
            checkpoint['total_processed'] += 1

            # 진행률 표시
            if (i + 1) % 10 == 0:
                elapsed = time.time() - batch_start
                speed = (i + 1) / elapsed
                print(f"\r  배치 {batch_num}/{total_batches}: {i+1}/{len(files)} ({speed:.1f}/초)", end="", flush=True)

            # 중간 저장
            if checkpoint['total_processed'] % SAVE_INTERVAL == 0:
                save_checkpoint(checkpoint)

    print()
    return results


def main():
    print("=" * 60)
    print("레시피 전체 처리 시작")
    print("=" * 60)

    # 체크포인트 로드
    checkpoint = load_checkpoint()
    processed_set = set(checkpoint['processed_ids'])

    print(f"이전 처리 현황: {checkpoint['total_processed']}개 완료")
    print(f"  - 성공: {checkpoint['total_success']}개")
    print(f"  - 실패: {checkpoint['total_failed']}개")

    # 처리할 파일 목록 (이미 처리된 것 제외)
    all_files = list(RAW_DIR.glob("*.json"))
    files_to_process = [f for f in all_files if f.stem not in processed_set]

    total_files = len(files_to_process)
    print(f"\n처리 대상: {total_files}개 (전체 {len(all_files)}개 중)")

    if total_files == 0:
        print("처리할 파일이 없습니다.")
        return

    # 배치 분할
    batches = [files_to_process[i:i+BATCH_SIZE] for i in range(0, total_files, BATCH_SIZE)]
    total_batches = len(batches)

    print(f"배치 수: {total_batches}개 (배치당 {BATCH_SIZE}개)")
    print(f"동시 처리: {MAX_WORKERS}개 스레드")
    print(f"예상 시간: {total_files / 4.5 / 60:.1f}분 (약 {total_files / 4.5 / 3600:.1f}시간)")
    print()

    start_time = time.time()

    for batch_num, batch_files in enumerate(batches, 1):
        print(f"[배치 {batch_num}/{total_batches}] {len(batch_files)}개 처리 중...")

        try:
            results = process_batch(batch_files, checkpoint, batch_num, total_batches)
            print(f"  완료: 성공 {results['success']}개, 실패 {results['failed']}개")

            # 배치 완료 후 체크포인트 저장
            save_checkpoint(checkpoint)

            # 진행 상황 출력
            elapsed = time.time() - start_time
            remaining = (total_files - checkpoint['total_processed']) / (checkpoint['total_processed'] / elapsed) if checkpoint['total_processed'] > 0 else 0
            print(f"  전체 진행: {checkpoint['total_processed']}/{len(all_files)} | 경과: {elapsed/60:.1f}분 | 남은 시간: {remaining/60:.1f}분")
            print()

        except KeyboardInterrupt:
            print("\n\n중단됨! 체크포인트 저장 중...")
            save_checkpoint(checkpoint)
            print(f"저장 완료: {checkpoint['total_processed']}개 처리됨")
            return

        except Exception as e:
            print(f"\n배치 처리 오류: {e}")
            save_checkpoint(checkpoint)
            time.sleep(10)  # 잠시 대기 후 계속

    # 최종 결과
    total_time = time.time() - start_time
    print("=" * 60)
    print("처리 완료!")
    print(f"  총 처리: {checkpoint['total_processed']}개")
    print(f"  성공: {checkpoint['total_success']}개")
    print(f"  실패: {checkpoint['total_failed']}개")
    print(f"  소요 시간: {total_time/60:.1f}분 ({total_time/3600:.2f}시간)")
    print(f"  처리 속도: {checkpoint['total_processed']/total_time:.2f}개/초")
    print(f"\n결과 저장: {OUTPUT_DIR}")
    print(f"체크포인트: {CHECKPOINT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
