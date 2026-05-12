"""
LLM 기반 쿼리 확장 (Query Expansion)
======================================
사용자의 추상적인 자연어를 벡터 검색에 최적화된 풍부한 검색 문자열로 변환합니다.

역할: 자연어 → 확장된 search_query (벡터 유사도 검색에 사용)
     필터링(출처/근무지/경력)은 UI에서 사용자가 직접 설정

입력: "정보보안 관련 경험을 쌓고 싶어"
출력: {
    "search_query": "정보보안 보안엔지니어 침해대응 취약점분석 SOC SIEM 보안관제 모의해킹 security engineer",
    "summary":      "정보보안 분야 포지션 탐색"
}

지원 LLM (우선순위: Gemini → OpenAI → Bedrock → 규칙 기반 폴백):
  - Google Gemini  ← .env: GEMINI_API_KEY, GEMINI_MODEL (기본: gemini-2.5-flash)
  - OpenAI GPT     ← .env: OPENAI_API_KEY, OPENAI_EXPAND_MODEL (기본: gpt-4o-mini)
  - AWS Bedrock    ← .env: AWS_ACCESS_KEY_ID, BEDROCK_EXPAND_MODEL
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── 프롬프트 ─────────────────────────────────────────────────────
_SYSTEM_PROMPT = """당신은 IT/보안 채용 공고 검색 전문가입니다.
사용자의 자연어 입력을 분석하여 채용 공고 벡터 검색에 최적화된 검색 문자열을 생성하세요.

반환 형식 (JSON만 반환, 설명 없이):
{
  "search_query": "벡터 유사도 검색에 사용할 풍부한 검색 문자열. 관련 직무명, 기술명, 업무 키워드를 한국어와 영어로 모두 포함하세요. 동의어와 관련 직무도 포함하세요.",
  "summary": "사용자 의도 한 줄 요약 (20자 이내)"
}

예시:
- 입력: "정보보안 관련 경험을 쌓고 싶어"
  출력: {"search_query": "정보보안 보안엔지니어 침해대응 취약점분석 보안관제 SOC SIEM 모의해킹 security engineer vulnerability analysis", "summary": "정보보안 분야 포지션 탐색"}

- 입력: "신입으로 백엔드 개발 시작하고 싶어"
  출력: {"search_query": "백엔드 개발자 서버개발 신입 Spring Django FastAPI Node.js REST API backend developer junior", "summary": "백엔드 신입 개발자 포지션"}"""

_USER_PROMPT_TEMPLATE = "사용자 입력: {query}"


# ════════════════════════════════════════════════════════════════
# LLM 호출
# ════════════════════════════════════════════════════════════════

def _call_gemini(query: str) -> Optional[dict]:
    """Google Gemini로 쿼리 확장.
    Free tier  : gemini-2.5-flash  (GEMINI_MODEL 미설정 시 기본값)
    Advanced   : gemini-2.5-pro    (GEMINI_MODEL=gemini-2.5-pro 설정)
    """
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None

        model  = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
        client = genai.Client(api_key=api_key)
        prompt = f"{_SYSTEM_PROMPT}\n\n{_USER_PROMPT_TEMPLATE.format(query=query)}"

        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=256,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        return _parse_json(resp.text.strip())

    except Exception as e:
        logger.warning("[QueryExpander] Gemini 호출 실패: %s", e)
        return None


def _call_openai(query: str) -> Optional[dict]:
    """OpenAI GPT로 쿼리 확장."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model  = os.getenv("OPENAI_EXPAND_MODEL", "gpt-4o-mini")

        resp = client.chat.completions.create(
            model=model,
            max_tokens=256,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_PROMPT_TEMPLATE.format(query=query)},
            ],
        )
        return _parse_json(resp.choices[0].message.content.strip())

    except Exception as e:
        logger.warning("[QueryExpander] OpenAI 호출 실패: %s", e)
        return None


def _call_bedrock(query: str) -> Optional[dict]:
    """AWS Bedrock Claude로 쿼리 확장."""
    try:
        import boto3

        client   = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
        model_id = os.getenv("BEDROCK_EXPAND_MODEL", "anthropic.claude-3-5-haiku-20241022-v1:0")
        body     = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _USER_PROMPT_TEMPLATE.format(query=query)}],
        })

        resp    = client.invoke_model(modelId=model_id, body=body)
        content = json.loads(resp["body"].read())
        return _parse_json(content["content"][0]["text"].strip())

    except Exception as e:
        logger.warning("[QueryExpander] Bedrock 호출 실패: %s", e)
        return None


def _parse_json(text: str) -> Optional[dict]:
    """LLM 응답에서 JSON 추출 및 검증."""
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        data = json.loads(text)
        if "search_query" not in data or "summary" not in data:
            return None
        return data
    except (json.JSONDecodeError, ValueError):
        return None


# ════════════════════════════════════════════════════════════════
# 규칙 기반 폴백 (LLM 없을 때)
# ════════════════════════════════════════════════════════════════

_DOMAIN_MAP = {
    "보안":   "정보보안 보안엔지니어 침해대응 취약점분석 보안관제 SOC SIEM 모의해킹 security engineer",
    "백엔드": "백엔드 서버개발 API Spring Django FastAPI Node.js backend developer",
    "프론트": "프론트엔드 React Vue Angular UI개발 웹개발 frontend developer",
    "데이터": "데이터엔지니어 데이터분석 ML AI 머신러닝 Spark Kafka data engineer",
    "인프라": "DevOps SRE 클라우드 AWS Kubernetes Docker 인프라 infrastructure",
    "AI":     "AI엔지니어 LLM 딥러닝 PyTorch TensorFlow RAG AI engineer",
}


def _rule_based_expand(query: str) -> dict:
    """LLM 없을 때 규칙 기반으로 쿼리 확장."""
    q_lower = query.lower()
    expansions = []
    for domain, keywords in _DOMAIN_MAP.items():
        if domain.lower() in q_lower or any(k.lower() in q_lower for k in keywords.split()[:3]):
            expansions.append(keywords)

    search_query = query + (" " + " ".join(expansions) if expansions else "")
    return {
        "search_query": search_query.strip(),
        "summary":      f"{query[:20]}... 관련 포지션",
    }


# ════════════════════════════════════════════════════════════════
# 공개 API
# ════════════════════════════════════════════════════════════════

def expand_query(query: str) -> dict:
    """
    자연어 쿼리를 벡터 검색용 확장 문자열로 변환한다.

    LLM 우선순위: Gemini → OpenAI → Bedrock → 규칙 기반 폴백
    (환경변수에 API 키가 설정된 것을 자동 감지)

    Returns:
        {
            "search_query": str,   # 확장된 검색 문자열 (벡터 검색에 사용)
            "summary":      str,   # 의도 요약
            "provider":     str,   # 사용된 LLM ("gemini" | "openai" | "bedrock" | "rules")
        }
    """
    result = None
    provider = "rules"

    # 우선순위대로 시도
    if os.getenv("GEMINI_API_KEY"):
        result = _call_gemini(query)
        if result:
            provider = f"gemini ({os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')})"

    if result is None and os.getenv("OPENAI_API_KEY"):
        result = _call_openai(query)
        if result:
            provider = f"openai ({os.getenv('OPENAI_EXPAND_MODEL', 'gpt-4o-mini')})"

    if result is None and (os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_PROFILE")):
        result = _call_bedrock(query)
        if result:
            provider = "bedrock"

    if result is None:
        result = _rule_based_expand(query)
        logger.info("[QueryExpander] 규칙 기반 폴백 사용 (API 키 미설정)")
    else:
        logger.info("[QueryExpander] %s 확장 완료: %s", provider, result.get("summary", ""))

    result["provider"] = provider
    return result
