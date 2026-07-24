import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# .env 파일 로드 (이미 등록된 키를 활용)
load_dotenv()

def generate_consulting_cards(target_job: str, job_competencies_json: str, analysis_json_data: str) -> dict:
    """
    직무별 요구 역량과 지원자의 현재 역량을 비교 분석하여
    프론트엔드 UI 카드 렌더링용 JSON 데이터를 생성합니다.
    카드의 개수는 LLM이 분석 내용에 따라 동적으로 결정합니다 (최대 6개).
    
    :param target_job: 지원하는 목표 직무 (예: "공정 엔지니어", "SW 개발자")
    :param job_competencies_json: 해당 직무에서 요구하는 핵심 역량 기준 (JSON 문자열)
    :param analysis_json_data: 지원자의 현재 역량 평가 결과 (JSON 문자열)
    """
    
    api_key = os.environ.get("UPSTAGE_API_KEY")
    if not api_key:
        raise ValueError("API 키가 설정되지 않았습니다. 환경 변수 또는 .env 파일을 확인해주세요.")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1/solar"
    )

    # 🎯 프롬프트: 직무 요구치와 현재 상태를 비교하여 동적 카드 수로 컨설팅
    system_prompt = f"""
    당신은 '{target_job}' 직무 취업 및 커리어 성장을 돕는 최고 수준의 전문 컨설턴트입니다.
    아래 제공되는 해당 직무의 '요구 핵심 역량'과 지원자의 '현재 역량 평가 데이터'를 정밀하게 비교 분석하세요.
    지원자가 어떤 부분이 부족하고, 이를 어떻게 보완해야 하는지 구체적이고 실현 가능한 조언을 제공해야 합니다.

    [직무 요구 핵심 역량]
    {job_competencies_json}

    [지원자 현재 역량 평가]
    {analysis_json_data}

    **[핵심 규칙]**
    1. 분석 내용의 깊이와 직무 역량 개수에 따라 컨설팅 카드의 수를 유동적으로 결정하세요.
    2. 최소 2개, 최대 6개의 카드를 생성하세요.
    3. 각 카드는 서로 겹치지 않는 독립적인 주제를 다뤄야 합니다.
    4. 지원자의 강점과 약점의 개수, 직무별 필수역량의 개수에 맞게 카드 수를 조절하세요.
    5. 카드의 종류는 아래 예시 중에서 자유롭게 선택하되, 필요하다면 새로운 주제의 카드를 만들어도 됩니다:
       - 직무 적합도 및 Gap 분석
       - 핵심 강점 활용 전략
       - 핵심 약점 및 개선 방향
       - 우선순위 기반 보완 전략
       - 단기 실행 액션 플랜 (1~3개월)
       - 장기 성장 로드맵 (6개월~1년)
       - 추천 자격증/교육/프로젝트
       - 면접 대비 포인트

    반드시 아래의 JSON 형식으로만 응답하세요. 마크다운 기호(```json)나 부연 설명은 절대 포함하지 마세요.

    {{
      "consulting_cards": [
        {{
          "card_id": "고유한 영문 ID (snake_case)",
          "icon": "카드 주제에 어울리는 이모지 1개",
          "title": "카드 제목",
          "summary": "핵심 내용 한 줄 요약",
          "details": ["구체적인 조언 또는 분석 포인트 1", "구체적인 조언 또는 분석 포인트 2", "...필요한 만큼"]
        }}
      ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="solar-pro",
            messages=[
                {"role": "system", "content": system_prompt}
            ],
            temperature=0.6,
            response_format={"type": "json_object"} 
        )
        
        result_content = response.choices[0].message.content
        return json.loads(result_content)
        
    except json.JSONDecodeError:
        return {"error": "JSON 파싱에 실패했습니다. 모델의 응답 형식을 확인하세요."}
    except Exception as e:
        return {"error": f"컨설팅 보고서 생성 중 오류가 발생했습니다: {e}"}