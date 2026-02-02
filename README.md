# Korean Recipe Crawler (만개의 레시피)

한국 레시피 웹사이트 (10000recipe.com) 크롤러 및 데이터 처리 도구

## 개요

- **데이터 수집**: 173,939개 레시피 크롤링
- **이미지 다운로드**: 레시피 이미지 병렬 다운로드
- **데이터 정제**: Gemini API를 활용한 LLM 기반 데이터 정제
- **검증**: 음식명 검증 및 수정

## 프로젝트 구조

```
korean-recipe-crawler/
├── scripts/                    # 실행 스크립트
│   ├── crawl.py               # 메인 크롤러
│   ├── download_images.py     # 이미지 다운로더
│   ├── process_recipes.py     # LLM 데이터 정제
│   ├── process_data.py        # 데이터 전처리
│   ├── validate_recipes.py    # 음식명 검증
│   └── revalidate_updated.py  # 재검증
│
├── src/                       # 소스 코드
│   ├── crawlers/              # 크롤러 모듈
│   │   ├── category_crawler.py
│   │   └── recipe_crawler.py
│   ├── processors/            # 처리기
│   │   └── llm_processor.py
│   ├── storage/               # 저장 핸들러
│   │   ├── json_handler.py
│   │   └── csv_handler.py
│   └── utils/                 # 유틸리티
│       └── helpers.py
│
├── config/
│   └── settings.py            # 설정
│
├── data/                      # 데이터 (gitignore)
│   ├── raw/                   # 크롤링 원본
│   ├── processed/             # 정제된 데이터
│   └── images/                # 레시피 이미지
│
├── requirements.txt
└── README.md
```

## 설치

```bash
# 환경 생성
conda create -n food-crawler python=3.10 -y
conda activate food-crawler

# 의존성 설치
pip install -r requirements.txt

# API 키 설정 (LLM 처리용)
export GOOGLE_API_KEY="your-api-key"
```

## 사용법

### 1. 레시피 크롤링

```bash
# 전체 크롤링
python scripts/crawl.py crawl

# 특정 페이지 범위
python scripts/crawl.py crawl --start 1 --end 100

# 크롤링 상태 확인
python scripts/crawl.py status
```

### 2. 이미지 다운로드

```bash
python scripts/download_images.py
```

### 3. 데이터 정제 (Gemini API)

```bash
# API 키 설정 필수
export GOOGLE_API_KEY="your-api-key"

python scripts/process_recipes.py
```

### 4. 검증

```bash
python scripts/validate_recipes.py
```

## 데이터 형식

### 정제된 레시피 (recipes_refined/)

```json
{
  "recipe_id": "6984007",
  "food_name": "김치찌개",
  "ingredients": [
    {"name": "돼지고기", "amount": "300g"},
    {"name": "김치", "amount": "1/4포기"}
  ],
  "steps": [
    "돼지고기를 한입 크기로 썬다",
    "냄비에 기름을 두르고 볶는다"
  ],
  "image_url": "https://..."
}
```

## 수집 통계

| 항목 | 수량 |
|------|------|
| 전체 레시피 | 173,939개 |
| 이미지 | ~170,000장 |
| 용량 (이미지) | ~53GB |
| 용량 (데이터) | ~1.6GB |

## 관련 프로젝트

- [korean-recipe-retrieval](https://github.com/nurlan6812/korean-recipe-retrieval) - 이 데이터로 학습한 레시피-이미지 검색 모델
