# 만개의레시피 크롤링 & 데이터 정제 프로젝트

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [데이터 처리 파이프라인](#3-데이터-처리-파이프라인)
4. [각 단계별 상세 설명](#4-각-단계별-상세-설명)
5. [데이터 형식 및 예시](#5-데이터-형식-및-예시)
6. [최종 데이터 필터링](#6-최종-데이터-필터링)
7. [스크립트 사용법](#7-스크립트-사용법)
8. [데이터 통계](#8-데이터-통계)

---

## 1. 프로젝트 개요

### 1.1 목적
- **만개의레시피** (10000recipe.com) 사이트에서 한국 음식 레시피 데이터 수집
- Gemini API를 활용한 레시피 데이터 정제 (제목 정제, 해요체 변환)
- VLM (Vision Language Model) 학습을 위한 고품질 Food 데이터셋 구축

### 1.2 최종 목표
- Food 도메인 특화 VLM 모델 학습
- GPT-4V, Gemini보다 한국 음식 인식에 특화된 모델 개발
- Qwen3-VL-8B-Instruct 모델 파인튜닝

### 1.3 데이터 출처
- **사이트**: https://www.10000recipe.com
- **수집 방식**: Python 크롤링 (BeautifulSoup, requests)
- **수집 기간**: 2024년 12월

---

## 2. 디렉토리 구조

```
food_crawling/
│
├── main.py                      # 크롤링 메인 CLI
├── process_all_recipes.py       # 1차 정제: Gemini API 처리
├── validate_all_recipes.py      # 2차 검증: 음식명 재검증
├── revalidate_updated.py        # 3차 재검증: 수정된 레시피 확인
├── download_images.py           # 이미지 다운로드
│
├── config/
│   └── settings.py              # 설정 파일 (URL, API, 경로)
│
├── crawlers/
│   ├── __init__.py
│   ├── category_crawler.py      # 카테고리 크롤러
│   └── recipe_crawler.py        # 레시피 상세 크롤러
│
├── storage/
│   ├── __init__.py
│   ├── json_handler.py          # JSON 저장/로드 유틸리티
│   └── csv_handler.py           # CSV 저장 유틸리티
│
├── utils/
│   ├── __init__.py
│   └── helpers.py               # 공통 유틸리티 함수
│
├── processors/
│   ├── __init__.py
│   └── llm_processor.py         # LLM 처리 모듈
│
├── data/
│   ├── checkpoint.json          # 크롤링 체크포인트
│   ├── failed_ids.json          # 실패한 레시피 ID 목록
│   │
│   ├── raw/
│   │   └── recipes/             # 원본 크롤링 데이터 (184,307개 JSON)
│   │
│   ├── processed/
│   │   ├── recipes_refined/     # 최종 정제 데이터 (179,486개 JSON)
│   │   ├── checkpoint_refined.json
│   │   ├── checkpoint_validation.json
│   │   └── checkpoint_revalidation.json
│   │
│   └── images/
│       ├── recipes/             # 레시피 이미지 (179,486개, 53GB)
│       └── checkpoint_images.json
│
├── logs/
│   └── crawling.log             # 크롤링 로그
│
└── unsloth_compiled_cache/      # Unsloth 모델 캐시
```

---

## 3. 데이터 처리 파이프라인

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           데이터 처리 파이프라인                              │
└─────────────────────────────────────────────────────────────────────────────┘

[Stage 1] 크롤링 (main.py)
    │
    │   만개의레시피 웹사이트 크롤링
    │   - 레시피 목록 페이지 순회
    │   - 각 레시피 상세 페이지 파싱
    │   - JSON 파일로 저장
    │
    ▼
┌─────────────────────────────────────────┐
│  Raw Data: 184,307개                    │
│  위치: data/raw/recipes/*.json          │
└─────────────────────────────────────────┘
    │
    │
[Stage 2] 1차 정제 (process_all_recipes.py)
    │
    │   Gemini API (gemini-2.0-flash)
    │   - 제목에서 핵심 음식명 추출
    │   - 유명인 레시피 출처 추출
    │   - 조리법 해요체 변환
    │   - 괄호 내용 제거/통합
    │   - 메타정보 파싱 (인분, 시간, 난이도)
    │
    ▼
┌─────────────────────────────────────────┐
│  1차 정제: 184,086개 (성공)              │
│  실패: 221개                            │
│  처리 시간: 약 11시간                    │
└─────────────────────────────────────────┘
    │
    │
[Stage 3] 2차 검증 (validate_all_recipes.py)
    │
    │   Gemini API로 음식명 재검증
    │   - 수식어 제거 (만능, 초간단, N분 등)
    │   - 슬래시(/) 처리 → 대표명 선택
    │   - 쉼표(,) 처리 → 단일 요리면 대표명, 복수면 DELETE
    │   - 레시피 내용과 음식명 일치 여부 확인
    │   - 모음집, N가지 요리 DELETE
    │
    ▼
┌─────────────────────────────────────────┐
│  2차 검증 결과:                          │
│  - 유지: 128,310개                       │
│  - 수정: 53,381개                        │
│  - 삭제: 2,395개                         │
│  남은 레시피: 181,691개                  │
└─────────────────────────────────────────┘
    │
    │
[Stage 4] 3차 재검증 (revalidate_updated.py)
    │
    │   수정된 53,381개만 대상
    │   - 원본 제목과 현재 음식명 비교
    │   - 잘못된 변환 감지 (모음집 → 단일 요리)
    │   - 예: "가지요리 6종세트" → "돼지고기 가지볶음" (삭제)
    │
    ▼
┌─────────────────────────────────────────┐
│  3차 재검증 결과:                        │
│  - 추가 삭제: 2,205개                    │
│  남은 레시피: 179,486개                  │
└─────────────────────────────────────────┘
    │
    │
[Stage 5] 이미지 다운로드 (download_images.py)
    │
    │   병렬 다운로드 (20 workers)
    │   - main_image_url에서 이미지 다운로드
    │   - {recipe_id}.jpg 형식으로 저장
    │   - 404 에러 발생 시 해당 레시피 삭제
    │
    ▼
┌─────────────────────────────────────────┐
│  이미지 다운로드 결과:                    │
│  - 성공: 179,470개                       │
│  - 실패 (404): 16개 → 레시피 삭제        │
│  최종: 179,486개 (레시피 + 이미지 1:1)   │
│  용량: 53GB                              │
└─────────────────────────────────────────┘
    │
    │
[Stage 6] VLM 학습용 필터링 (filter_valid_recipes)
    │
    │   유효성 검사
    │   - 이미지 파일 존재 여부
    │   - 재료 목록 존재 여부
    │   - 조리법 존재 여부
    │   - 제목 존재 여부
    │
    ▼
┌─────────────────────────────────────────┐
│  최종 유효 데이터: 173,939개             │
│  제외: 5,547개                           │
│  위치: data/processed/recipes_refined/   │
│  이미지: data/images/recipes/            │
└─────────────────────────────────────────┘
```

---

## 4. 각 단계별 상세 설명

### 4.1 Stage 1: 크롤링 (main.py)

#### 실행 방법
```bash
# 전체 크롤링
python main.py crawl

# 특정 페이지 범위
python main.py crawl --start 1 --end 100

# 실패한 레시피 재시도
python main.py retry

# 상태 확인
python main.py status
```

#### 크롤링 대상 정보
| 항목 | 설명 |
|------|------|
| recipe_id | 레시피 고유 ID |
| title_original | 원본 제목 |
| description | 설명 (인분/시간/난이도 포함) |
| main_image_url | 메인 이미지 URL |
| author | 작성자 |
| ingredients | 재료 목록 (이름, 양) |
| steps | 조리 순서 (설명, 이미지) |
| tips | 요리 팁 |
| categories | 카테고리 (종류/상황/재료/방법별) |

#### 체크포인트 시스템
- `data/checkpoint.json`: 마지막 크롤링 페이지, 완료된 ID 목록
- `data/failed_ids.json`: 실패한 레시피 ID 목록
- 중단 후 재시작 시 자동으로 이어서 진행

---

### 4.2 Stage 2: 1차 정제 (process_all_recipes.py)

#### 처리 내용
1. **제목 정제**: "생크림 없을 때 로제 만들기" → "로제 우동"
2. **유명인 출처 추출**: "백종원의 김치찌개" → recipe_source: "백종원"
3. **해요체 변환**: "~한다", "~ㅂ니다" → "~해요"
4. **괄호 제거**: "(선택 사항)" 내용을 문장에 통합하거나 삭제
5. **메타정보 파싱**: description에서 인분/시간/난이도 추출

#### Gemini API 프롬프트
```
레시피 정제

[원본]
제목: {title}
재료: {ingredients}
조리순서:
{steps}

[필수 규칙]
1. food_name: 핵심 음식명만 (하나만)
2. recipe_source: 유명인만 (없으면 null)
3. steps:
   - 문체: 모든 문장 "~요"로 끝내기
   - 금지: "~ㅂ니다", "~한다", "~줘"
   - 괄호() 절대 사용 금지! 괄호 내용은 삭제하거나 문장에 녹여야 함
   - 잡담/광고 제거
   - 연속된 짧은 단계 합치기

{"food_name":"","recipe_source":null,"steps":[]}
```

#### 처리 설정
| 설정 | 값 |
|------|-----|
| MAX_WORKERS | 10 (동시 처리 스레드) |
| BATCH_SIZE | 1000 |
| MAX_RETRIES | 3 |
| 모델 | gemini-2.0-flash |
| temperature | 0.1 |

---

### 4.3 Stage 3: 2차 검증 (validate_all_recipes.py)

#### 검증 규칙
1. **수식어 제거**
   - 만능, 초간단, 초스피드, 간단, 쉬운, 꿀맛, 대박, 존맛
   - N분, N색, HACCP 등
   - 예: "만능 야채참치" → "야채참치"

2. **슬래시(/) 처리**
   - 같은 종류면 대표명 선택
   - 레시피 내용 기준으로 판단
   - 예: "돼지국밥/순대국밥" → "돼지국밥"

3. **쉼표(,) 처리**
   - 하나의 요리면 대표명 선택
   - 완전히 다른 여러 요리면 DELETE

4. **레시피 내용과 불일치 시 수정**

5. **DELETE 대상**
   - 빈 값
   - 모음집 ("N가지 요리")
   - 복합 레시피

---

### 4.4 Stage 4: 3차 재검증 (revalidate_updated.py)

#### 재검증 대상
- 2차 검증에서 수정된 53,381개 레시피

#### 검증 방법
- 원본 제목 (`title_original`)과 현재 음식명 (`food_name`) 비교
- 모음집이 단일 요리로 잘못 변환된 경우 삭제

#### 문제 사례
```
원본: "가지요리 6종세트"
잘못된 변환: "돼지고기 가지볶음"
→ 모음집 레시피가 실제로는 6가지 요리를 포함하므로 삭제
```

---

### 4.5 Stage 5: 이미지 다운로드 (download_images.py)

#### 설정
| 설정 | 값 |
|------|-----|
| MAX_WORKERS | 20 |
| BATCH_SIZE | 1000 |
| TIMEOUT | 10초 |

#### 저장 형식
- 파일명: `{recipe_id}.jpg`
- 위치: `data/images/recipes/`

#### 실패 처리
- 404 에러 발생 시 해당 레시피 JSON도 삭제
- 최종 16개 레시피 삭제됨

---

## 5. 데이터 형식 및 예시

### 5.1 Raw 데이터 (크롤링 원본)

**위치**: `data/raw/recipes/{recipe_id}.json`

```json
{
  "recipe_id": "6995497",
  "url": "https://www.10000recipe.com/recipe/6995497",
  "title_original": "생크림 없을 때 로제 만들기",
  "description": "1인분10분 이내아무나",
  "main_image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/f95f10aa07b1d8b180aa47e9cb0bbbfe1.jpg",
  "author": "쿠킹천국",
  "servings": "1인분",
  "cook_time": null,
  "difficulty": null,
  "rating": null,
  "ingredients": [
    {
      "name": "우동면",
      "amount": "1개"
    },
    {
      "name": "우유",
      "amount": "200ml"
    },
    {
      "name": "버터",
      "amount": "1큰술"
    },
    {
      "name": "설탕",
      "amount": "1작은술"
    },
    {
      "name": "고운 고춧가루",
      "amount": "1큰술"
    },
    {
      "name": "청양고추",
      "amount": "1개"
    },
    {
      "name": "슬라이스치즈",
      "amount": "1장"
    },
    {
      "name": "소금",
      "amount": "약간"
    },
    {
      "name": "후추",
      "amount": "약간"
    },
    {
      "name": "물",
      "amount": "500ml"
    },
    {
      "name": "파슬리가루",
      "amount": "약간"
    }
  ],
  "steps": [
    {
      "step_num": 1,
      "description": "물 500ml에 물이 끓으면 우동면 1개를 넣는다. 2~3분 끓여 면을 익혀준다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/d10cfe37e230227dce2755e21d06da971.jpg"
    },
    {
      "step_num": 2,
      "description": "우동면을 찬물에 헹군 후 찬물에 담가놓는다. 로제 양념을 만들 동안 불지 않게 하기 위함이다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/a084491347ddf4a05a2b8318c325b79f1.jpg"
    },
    {
      "step_num": 3,
      "description": "버터 1 큰 술을 넣고 고운 고춧가루 1 작은 술 넣는다.중불",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/31619c7cac8c77b291200da8f4a71bc01.jpg"
    },
    {
      "step_num": 4,
      "description": "우유 200ml를 넣고 잘 섞어준다.빠르게 섞어 버터가 우유와 잘 섞이게 만든다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/8b2b85f1853f7968cc90d1ea02c20dd41.jpg"
    },
    {
      "step_num": 5,
      "description": "청양고추 1개를 반을 잘라 넣는다. 설탕 1 작은 술, 소금 약간 넣는다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/7a09f7ab18a4703e6ee76df38f7775a91.jpg"
    },
    {
      "step_num": 6,
      "description": "우동면을 넣어 양념과 섞어준다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/ba5b37ef4a31e238e1b86eec6f8971781.jpg"
    },
    {
      "step_num": 7,
      "description": "슬라이스 치즈 1장(선택 사항)을 넣어준다.치즈를 넣으면 더욱 풍미가 좋다. 그리고 살짝 꾸덕꾸덕한 식감을 주기도 한다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/c114318d5abcf02864827811f2d336261.jpg"
    },
    {
      "step_num": 8,
      "description": "면은 이미 익은 상태이기 때문에 2~3분 끓이면 된다. 파슬리가루 약간 뿌려 마무리한다.",
      "image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/43ed6eda8ab933609d664e81c888fd1b1.jpg"
    }
  ],
  "tips": null,
  "cat_type": null,
  "cat_situation": null,
  "cat_ingredient": null,
  "cat_method": null
}
```

#### Raw 데이터 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| recipe_id | string | 레시피 고유 ID |
| url | string | 원본 레시피 URL |
| title_original | string | 원본 제목 |
| description | string | 설명 (인분/시간/난이도 혼합) |
| main_image_url | string | 메인 이미지 URL |
| author | string | 작성자 |
| servings | string \| null | 인분 |
| cook_time | string \| null | 조리 시간 |
| difficulty | string \| null | 난이도 |
| rating | float \| null | 평점 |
| ingredients | array | 재료 목록 |
| steps | array | 조리 순서 (step_num, description, image_url) |
| tips | string \| null | 요리 팁 |
| cat_type | string \| null | 종류별 카테고리 |
| cat_situation | string \| null | 상황별 카테고리 |
| cat_ingredient | string \| null | 재료별 카테고리 |
| cat_method | string \| null | 방법별 카테고리 |

---

### 5.2 Refined 데이터 (최종 정제)

**위치**: `data/processed/recipes_refined/{recipe_id}.json`

```json
{
  "recipe_id": "6995497",
  "food_name": "로제 우동",
  "recipe_source": null,
  "servings": "1인분",
  "cook_time": "10분 이내",
  "difficulty": "아무나",
  "main_image_url": "https://recipe1.ezmember.co.kr/cache/recipe/2023/01/15/f95f10aa07b1d8b180aa47e9cb0bbbfe1.jpg",
  "recipe_url": "https://www.10000recipe.com/recipe/6995497",
  "ingredients": [
    {
      "name": "우동면",
      "amount": "1개"
    },
    {
      "name": "우유",
      "amount": "200ml"
    },
    {
      "name": "버터",
      "amount": "1큰술"
    },
    {
      "name": "설탕",
      "amount": "1작은술"
    },
    {
      "name": "고운 고춧가루",
      "amount": "1큰술"
    },
    {
      "name": "청양고추",
      "amount": "1개"
    },
    {
      "name": "슬라이스치즈",
      "amount": "1장"
    },
    {
      "name": "소금",
      "amount": "약간"
    },
    {
      "name": "후추",
      "amount": "약간"
    },
    {
      "name": "물",
      "amount": "500ml"
    },
    {
      "name": "파슬리가루",
      "amount": "약간"
    }
  ],
  "steps": [
    "물 500ml에 물이 끓으면 우동면 1개를 넣고 2~3분 끓여 면을 익혀줘요.",
    "우동면을 찬물에 헹군 후 찬물에 담가 로제 양념을 만들 동안 불지 않게 해요.",
    "중불에 버터 1 큰 술과 고운 고춧가루 1 작은 술을 넣어요.",
    "우유 200ml를 넣고 빠르게 섞어 버터가 우유와 잘 섞이게 해요.",
    "청양고추 1개를 반으로 잘라 넣고 설탕 1 작은 술, 소금 약간 넣어요.",
    "우동면을 넣어 양념과 섞어줘요.",
    "선택 사항으로 슬라이스 치즈 1장을 넣어 풍미와 꾸덕꾸덕한 식감을 더해요.",
    "면은 이미 익은 상태이므로 2~3분 끓이면 완성돼요.",
    "파슬리 가루 약간 뿌려 마무리해요."
  ]
}
```

#### Refined 데이터 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| recipe_id | string | 레시피 고유 ID |
| food_name | string | **정제된 음식명** (핵심 명칭만) |
| recipe_source | string \| null | 유명인 출처 (백종원, 이연복 등) |
| servings | string \| null | 인분 (description에서 파싱) |
| cook_time | string \| null | 조리 시간 (description에서 파싱) |
| difficulty | string \| null | 난이도 (description에서 파싱) |
| main_image_url | string | 메인 이미지 URL |
| recipe_url | string | 원본 레시피 URL |
| ingredients | array | 재료 목록 (이름, 양) |
| steps | array[string] | **해요체로 변환된 조리 순서** |

#### Raw vs Refined 비교

| 항목 | Raw | Refined |
|------|-----|---------|
| 제목 | "생크림 없을 때 로제 만들기" | "로제 우동" |
| 조리법 형식 | 객체 배열 (step_num, description, image_url) | 문자열 배열 |
| 문체 | "~한다", "~준다" 혼합 | **"~해요" 통일** |
| 괄호 | "(선택 사항)" 포함 | 문장에 통합 |
| 메타정보 | description에 혼합 | servings, cook_time, difficulty 분리 |

---

### 5.3 이미지 데이터

**위치**: `data/images/recipes/{recipe_id}.jpg`

| 항목 | 값 |
|------|-----|
| 형식 | JPEG (대부분), PNG, GIF, WebP |
| 파일명 | {recipe_id}.{확장자} |
| 총 용량 | 53GB |
| 총 개수 | 179,486개 |

---

## 6. 최종 데이터 필터링

### 6.1 필터링 함수

VLM 학습용 데이터셋 생성 시 `filter_valid_recipes()` 함수로 유효성 검사:

```python
def filter_valid_recipes(recipes: list, image_dir: str) -> list:
    valid_recipes = []

    for recipe in recipes:
        recipe_id = recipe.get('recipe_id')
        image_path = Path(image_dir) / f"{recipe_id}.jpg"

        # 4가지 조건 모두 만족해야 유효
        if image_path.exists():                    # 1. 이미지 존재
            if recipe.get('ingredients'):          # 2. 재료 있음
                if recipe.get('steps'):            # 3. 조리법 있음
                    if recipe.get('food_name'):    # 4. 제목 있음
                        valid_recipes.append(recipe)

    return valid_recipes
```

### 6.2 필터링 조건

| 조건 | 설명 |
|------|------|
| 이미지 존재 | `{recipe_id}.jpg` 파일이 images/recipes/에 있어야 함 |
| 재료 존재 | `ingredients` 배열이 비어있지 않아야 함 |
| 조리법 존재 | `steps` 배열이 비어있지 않아야 함 |
| 제목 존재 | `food_name`이 비어있지 않아야 함 |

### 6.3 제외 원인 분석

| 원인 | 개수 |
|------|------|
| 이미지 없음 | 4,842개 |
| 재료 없음 | 607개 |
| 조리법 없음 | 15개 |
| **합계 (중복 제외)** | **5,547개** |

> **참고**: 일부 레시피는 여러 조건에 해당 (예: 이미지도 없고 재료도 없음)

### 6.4 필터링 결과

```
전체 정제 데이터:  179,486개
제외된 데이터:      5,547개
─────────────────────────────
최종 유효 데이터:  173,939개
```

---

## 7. 스크립트 사용법

### 7.1 크롤링 (main.py)

```bash
# 전체 크롤링 시작
python main.py crawl

# 특정 페이지 범위만 크롤링
python main.py crawl --start 100 --end 200

# 저장 간격 설정 (기본값: 100)
python main.py crawl --interval 50

# 실패한 레시피 재시도
python main.py retry

# 이미지 다운로드
python main.py images

# 데이터 내보내기 (CSV + JSON)
python main.py export

# 크롤링 상태 확인
python main.py status
```

### 7.2 1차 정제 (process_all_recipes.py)

```bash
# 전체 레시피 정제 (체크포인트 자동 관리)
python process_all_recipes.py
```

- 중단 후 재실행 시 자동으로 이어서 처리
- 체크포인트: `data/processed/checkpoint_refined.json`

### 7.3 2차 검증 (validate_all_recipes.py)

```bash
# 전체 레시피 음식명 재검증
python validate_all_recipes.py
```

- 체크포인트: `data/processed/checkpoint_validation.json`

### 7.4 3차 재검증 (revalidate_updated.py)

```bash
# 수정된 레시피만 재검증
python revalidate_updated.py
```

- 체크포인트: `data/processed/checkpoint_revalidation.json`

### 7.5 이미지 다운로드 (download_images.py)

```bash
# 이미지 다운로드
python download_images.py
```

- 체크포인트: `data/images/checkpoint_images.json`

---

## 8. 데이터 통계

### 8.1 처리 단계별 수량

| 단계 | 수량 | 비고 |
|------|------|------|
| 크롤링 완료 | 184,307개 | Raw 데이터 |
| 1차 정제 성공 | 184,086개 | 221개 실패 |
| 2차 검증 후 | 181,691개 | 2,395개 삭제 |
| 3차 재검증 후 | 179,486개 | 2,205개 추가 삭제 |
| 이미지 매칭 후 | 179,486개 | 16개 404 에러 삭제 |
| **최종 유효** | **173,939개** | 5,547개 필터링 |

### 8.2 삭제 사유 요약

| 사유 | 수량 |
|------|------|
| 1차 정제 실패 (API 오류) | 221개 |
| 2차 검증 삭제 (모음집, 복수 요리 등) | 2,395개 |
| 3차 재검증 삭제 (잘못된 변환) | 2,205개 |
| 이미지 404 에러 | 16개 |
| 유효성 필터링 (이미지/재료/조리법 없음) | 5,547개 |
| **총 삭제/제외** | **10,368개** |

### 8.3 최종 데이터 용량

| 항목 | 용량/수량 |
|------|----------|
| 정제 JSON 파일 | 179,486개 |
| 이미지 파일 | 179,486개 (53GB) |
| 유효 데이터 | 173,939개 |

---

## 부록: 설정 파일 (config/settings.py)

```python
# 기본 경로
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
IMAGES_DIR = DATA_DIR / "images"

# 크롤링 설정
BASE_URL = "https://www.10000recipe.com"
LIST_URL = f"{BASE_URL}/recipe/list.html"
RECIPE_URL = f"{BASE_URL}/recipe"

# 요청 설정
REQUEST_DELAY = 0.5      # 요청 간격 (초)
REQUEST_TIMEOUT = 30     # 요청 타임아웃 (초)
MAX_RETRIES = 3          # 최대 재시도 횟수

# LLM 설정
LLM_MODEL = "unsloth/Qwen3-VL-8B-Instruct-unsloth-bnb-4bit"
GEMINI_MODEL = "gemini-2.0-flash-exp"
```

---

## 다음 단계: VLM 학습 데이터셋 생성

현재 데이터를 기반으로 **Food QA 데이터셋** 생성 예정:

- **형식**: Qwen3-VL JSONL
- **구조**: 이미지 + 질문 → 답변
- **질문 유형**: 음식 이름, 재료, 레시피, 난이도/시간 등
- **타겟 모델**: `unsloth/Qwen3-VL-8B-Instruct-unsloth-bnb-4bit`
