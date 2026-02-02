"""
LLM 전처리기
제목에서 음식 이름과 레시피 출처 추출
"""
import json
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import LLM_MODEL, LLM_BATCH_SIZE, LLM_MAX_NEW_TOKENS, GEMINI_API_KEY, GEMINI_MODEL
from utils.helpers import logger


class LLMProcessor:
    """Qwen3-VL 기반 텍스트 전처리기"""

    def __init__(self, model_name: str = LLM_MODEL):
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load_model(self):
        """모델 로드"""
        if self._loaded:
            return

        logger.info(f"모델 로드 중: {self.model_name}")

        try:
            from unsloth import FastVisionModel

            # 모델 로드 (4-bit 양자화)
            self.model, self.tokenizer = FastVisionModel.from_pretrained(
                self.model_name,
                load_in_4bit=True,
            )

            # 추론 모드 활성화
            FastVisionModel.for_inference(self.model)

            self._loaded = True
            logger.info("모델 로드 완료")

        except Exception as e:
            logger.error(f"모델 로드 실패: {e}")
            raise

    def unload_model(self):
        """모델 언로드 (메모리 해제)"""
        if self.model is not None:
            del self.model
            del self.tokenizer
            self.model = None
            self.tokenizer = None
            self._loaded = False

            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info("모델 언로드 완료")

    def _generate(self, prompt: str, max_new_tokens: int = LLM_MAX_NEW_TOKENS) -> str:
        """텍스트 생성"""
        if not self._loaded:
            self.load_model()

        try:
            # 텍스트만 사용하는 메시지 형식
            messages = [
                {"role": "user", "content": [
                    {"type": "text", "text": prompt}
                ]}
            ]

            # 텍스트 전용 처리 (images=None으로 text-only 모드)
            text_input = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            inputs = self.tokenizer(
                text=text_input,
                images=None,  # text-only 모드
                return_tensors="pt",
                padding=True,
            ).to(self.model.device)

            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.7,
                do_sample=True,
            )

            # 입력 부분 제외하고 출력만 디코딩
            generated_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            output = self.tokenizer.decode(generated_ids, skip_special_tokens=True)

            return output.strip()

        except Exception as e:
            logger.error(f"생성 실패: {e}")
            return ""

    def process_title(self, title: str, ingredients: List[str] = None) -> Dict[str, Optional[str]]:
        """
        레시피 제목 전처리

        Args:
            title: 원본 레시피 제목
            ingredients: 재료 리스트 (컨텍스트용)

        Returns:
            {"food_name": "음식이름", "recipe_source": "출처 또는 None"}
        """
        # 재료 컨텍스트 구성
        ingredients_str = ', '.join(ingredients[:10]) if ingredients else ''

        prompt = f'''음식 이름 추출

제목: {title}
재료: {ingredients_str}

규칙:
1. 핵심 음식 이름만 (수식어 제거)
2. 출처는 실제 유명인/셰프만 (백종원, 정지선, 김하진 등)
   - "엄마표", "할머니", "엄마손" 등은 출처 아님 → null

{{"food_name":"이름","recipe_source":"유명인 or null"}}'''

        result = self._generate(prompt, max_new_tokens=100)

        # JSON 파싱 시도
        try:
            # JSON 부분 추출
            json_match = re.search(r'\{[^}]+\}', result)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "food_name": parsed.get("food_name"),
                    "recipe_source": parsed.get("recipe_source") if parsed.get("recipe_source") != "null" else None
                }
        except json.JSONDecodeError:
            pass

        # 파싱 실패 시 기본값 반환
        logger.warning(f"제목 파싱 실패: {title} -> {result}")
        return {"food_name": title, "recipe_source": None}

    def process_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        조리 순서 전처리

        Args:
            steps: 원본 조리 순서 리스트

        Returns:
            전처리된 조리 순서 리스트
        """
        if not steps:
            return []

        processed_steps = []

        for step in steps:
            step_num = step.get("step_num")
            description = step.get("description", "")

            if not description:
                processed_steps.append({
                    "step_num": step_num,
                    "description": "",
                    "image_url": step.get("image_url", "")
                })
                continue

            processed_desc = self._process_single_step(description)

            processed_steps.append({
                "step_num": step_num,
                "description": processed_desc,
                "image_url": step.get("image_url", "")
            })

        return processed_steps

    def _process_single_step(self, description: str) -> str:
        """단일 조리 단계 전처리"""
        # "완성" 포함 시 강제 반환
        if "완성" in description:
            return "완성이에요."

        prompt = f"""조리 순서를 해요체로 정리하세요.

규칙:
1. 문장 끝을 "~해요", "~세요"로 통일
2. 잡담/광고/감탄사 제거
3. 올바른 문법: "썬다"→"썰어요", "끓인다"→"끓여요"
4. 원본에 없는 조리 과정을 새로 만들지 마세요

원본: {description}

정리:"""

        result = self._generate(prompt, max_new_tokens=256)

        # 결과가 비어있거나 너무 짧으면 원본 반환
        if not result or len(result) < 5:
            return description

        return result.strip()

    def process_recipe(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """
        전체 레시피 전처리

        Args:
            recipe: 원본 레시피 딕셔너리

        Returns:
            전처리된 필드가 추가된 레시피 딕셔너리
        """
        processed = recipe.copy()

        # 재료 리스트 추출 (컨텍스트용)
        ingredients = []
        for ing in recipe.get("ingredients", []):
            if isinstance(ing, dict):
                ingredients.append(ing.get("name", ""))
            elif isinstance(ing, str):
                ingredients.append(ing)

        # 제목 전처리 (재료 컨텍스트 포함)
        title = recipe.get("title_original", "")
        if title:
            title_result = self.process_title(title, ingredients)
            processed["title_processed"] = title_result.get("food_name")
            processed["recipe_source"] = title_result.get("recipe_source")

        # 조리 순서는 원본 그대로 유지 (시간 효율성)
        processed["steps_processed"] = recipe.get("steps", [])

        return processed

    def process_batch(self, recipes: List[Dict[str, Any]],
                      batch_size: int = LLM_BATCH_SIZE) -> List[Dict[str, Any]]:
        """
        배치 레시피 전처리

        Args:
            recipes: 레시피 리스트
            batch_size: 배치 크기 (현재는 순차 처리)

        Returns:
            전처리된 레시피 리스트
        """
        from tqdm import tqdm

        processed_recipes = []

        for recipe in tqdm(recipes, desc="레시피 전처리"):
            try:
                processed = self.process_recipe(recipe)
                processed_recipes.append(processed)
            except Exception as e:
                logger.error(f"레시피 전처리 실패 (ID: {recipe.get('recipe_id')}): {e}")
                # 실패 시 원본 그대로 추가
                processed_recipes.append(recipe)

        return processed_recipes


# Gemini API 기반 전처리
class GeminiProcessor:
    """Gemini API 기반 텍스트 전처리기"""

    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = GEMINI_MODEL):
        self.api_key = api_key
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        """Gemini 클라이언트 초기화"""
        if self._client is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model_name)
        return self._client

    def _generate(self, prompt: str, max_tokens: int = 100, max_retries: int = 3) -> str:
        """Gemini API 호출"""
        client = self._get_client()

        for attempt in range(max_retries):
            try:
                response = client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,  # 일관된 출력을 위해 낮은 temperature
                        "max_output_tokens": max_tokens,
                    }
                )
                return response.text.strip()
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    # Rate limit - 잠시 대기
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Gemini API 오류: {e}")
                if attempt == max_retries - 1:
                    return ""
        return ""

    def process_recipe(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """
        레시피 전처리 (제목 + 조리순서 한번에)
        - 내용 변경 없이 형식만 정제
        - 문체 통일 (해요체)
        - 잡담/광고 제거
        - 괄호 제거
        """
        processed = recipe.copy()

        title = recipe.get("title_original", "")
        steps = recipe.get("steps", [])

        # 재료 추출
        ingredients = []
        for ing in recipe.get("ingredients", []):
            if isinstance(ing, dict):
                ingredients.append(ing.get("name", ""))
            elif isinstance(ing, str):
                ingredients.append(ing)

        # 조리순서 텍스트 구성
        steps_text = ""
        for i, s in enumerate(steps):
            desc = s.get("description", "") if isinstance(s, dict) else str(s)
            if desc:
                steps_text += f"- {desc}\n"

        prompt = f'''레시피 정제

[원본]
제목: {title}
재료: {', '.join(ingredients[:10])}
조리순서:
{steps_text}

[필수 규칙]
1. food_name: 핵심 음식명만
2. recipe_source: 유명인만 (없으면 null)
3. steps:
   - 문체: 모든 문장 "~요"로 끝내기
   - 금지: "~ㅂ니다", "~한다", "~줘"
   - 괄호() 절대 사용 금지! 괄호 내용은 삭제하거나 문장에 녹여야 함
   - 잡담/광고 제거
   - 연속된 짧은 단계 합치기

{{"food_name":"","recipe_source":null,"steps":[]}}'''

        result = self._generate(prompt, max_tokens=1500)

        # JSON 파싱
        try:
            # JSON 블록 추출
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())

                source = parsed.get("recipe_source")
                if source in ["null", "None", None, ""]:
                    source = None

                processed["title_processed"] = parsed.get("food_name", title)
                processed["recipe_source"] = source

                # steps 처리 (단계 수가 다를 수 있음 - 합쳐지는 경우)
                new_steps = parsed.get("steps", [])
                if new_steps:
                    processed["steps_processed"] = []
                    for i, step_desc in enumerate(new_steps):
                        # 원본 이미지 URL 매핑 (가능한 경우)
                        original_image = ""
                        if i < len(steps) and isinstance(steps[i], dict):
                            original_image = steps[i].get("image_url", "")

                        processed["steps_processed"].append({
                            "step_num": i + 1,
                            "description": step_desc,
                            "image_url": original_image
                        })
                else:
                    # 빈 결과시 원본 유지
                    processed["steps_processed"] = steps

                return processed

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패: {title} -> {e}")

        # 실패시 원본 유지
        processed["title_processed"] = title
        processed["recipe_source"] = None
        processed["steps_processed"] = steps
        return processed

    def load_model(self):
        """API 사용이므로 별도 로드 불필요"""
        self._get_client()
        logger.info(f"Gemini API 초기화 완료: {self.model_name}")

    def unload_model(self):
        """API 사용이므로 별도 언로드 불필요"""
        self._client = None


# 규칙 기반 전처리 (LLM 없이 사용 가능)
class RuleBasedProcessor:
    """규칙 기반 제목 전처리 (LLM 대체용)"""

    # 제거할 접미사 패턴
    SUFFIX_PATTERNS = [
        r'\s*만들기$',
        r'\s*레시피$',
        r'\s*만드는\s*법$',
        r'\s*황금\s*레시피$',
        r'\s*꿀팁$',
    ]

    # 제거할 접두사 패턴
    PREFIX_PATTERNS = [
        r'^초간단\s*',
        r'^간단한?\s*',
        r'^맛있는\s*',
        r'^아삭하고\s*맛있는\s*',
        r'^따뜻한\s*',
        r'^시원한\s*',
        r'^\d+분\s*',
        r'^쉬운\s*',
    ]

    # 레시피 출처 패턴
    SOURCE_PATTERNS = [
        r'^([가-힣]+)의\s+',       # "백종원의 ..."
        r'^([가-힣]+)표\s+',       # "엄마표 ..."
        r'^\[([^\]]+)\]\s*',       # "[유튜버]의 ..."
    ]

    @classmethod
    def process_title(cls, title: str) -> Dict[str, Optional[str]]:
        """규칙 기반 제목 전처리"""
        food_name = title
        recipe_source = None

        # 출처 추출
        for pattern in cls.SOURCE_PATTERNS:
            match = re.match(pattern, food_name)
            if match:
                recipe_source = match.group(1)
                food_name = re.sub(pattern, '', food_name)
                break

        # 접두사 제거
        for pattern in cls.PREFIX_PATTERNS:
            food_name = re.sub(pattern, '', food_name)

        # 접미사 제거
        for pattern in cls.SUFFIX_PATTERNS:
            food_name = re.sub(pattern, '', food_name)

        # 특수문자 제거
        food_name = re.sub(r'[!~♥♡★☆]', '', food_name)

        # 공백 정리
        food_name = ' '.join(food_name.split()).strip()

        return {
            "food_name": food_name if food_name else title,
            "recipe_source": recipe_source
        }


if __name__ == "__main__":
    # 규칙 기반 테스트
    print("=== 규칙 기반 전처리 테스트 ===")
    test_titles = [
        "백종원의 돼지불백 만들기",
        "엄마표 김치찌개 황금레시피",
        "아삭하고 맛있는 오이고추된장무침 만들기",
        "초간단 10분 계란볶음밥 레시피",
        "[슈퍼주니어 규현] 규현의 떡볶이",
    ]

    for title in test_titles:
        result = RuleBasedProcessor.process_title(title)
        print(f"  {title}")
        print(f"    -> {result['food_name']} (출처: {result['recipe_source']})")
        print()
