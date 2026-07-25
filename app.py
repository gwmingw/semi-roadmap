import pdfplumber
import json
import os
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
from dotenv import load_dotenv
from llm2 import generate_consulting_cards

# .env 파일에서 환경 변수 로드
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPSTAGE_API_KEY = os.getenv('UPSTAGE_API_KEY')
if not UPSTAGE_API_KEY:
    print("경고: 환경 변수 'UPSTAGE_API_KEY'를 설정해주세요. (.env 파일 또는 시스템 환경 변수)")
    client = None
else:
    client = OpenAI(
        api_key=UPSTAGE_API_KEY,
        base_url="https://api.upstage.ai/v1/solar"
    )

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# Define persona prompts (default 제거)
PERSONA_PROMPTS = {
    "공정": "당신은 전문 공정 엔지니어 채용 담당자입니다. 제공된 이력서를 바탕으로 공정 기술, 생산 관리, 품질 관리, 문제 해결 능력, 관련 소프트웨어 활용 경험, 그리고 지원자의 공정 개선 기여 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요.",
    "설계": "당신은 전문 설계 엔지니어 채용 담당자입니다. 제공된 이력서를 바탕으로 CAD/CAM/CAE 역량, 설계 프로젝트 경험, 문제 해결을 위한 창의적 접근, 재료 역학 지식, 그리고 지원자의 설계 혁신 기여 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요.",
    "SW": "당신은 전문 소프트웨어 개발자 채용 담당자입니다. 제공된 이력서를 바탕으로 프로그래밍 언어 숙련도, 프레임워크 경험, 개발 방법론 이해 (Agile/Scrum), 프로젝트 기여도, 협업 능력, 그리고 지원자의 기술 스택 성장 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요.",
    "설비/인프라": "당신은 전문 설비/인프라 관리 채용 담당자입니다. 제공된 이력서를 바탕으로 설비 유지보수, 시스템 운영, 네트워크 관리, 보안 지식, 장애 대응 능력, 그리고 지원자의 안정적인 시스템 운영 기여 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요.",
    "경영": "당신은 전문 경영/기획 채용 담당자입니다. 제공된 이력서를 바탕으로 전략 기획, 사업 개발, 시장 분석, 리더십 역량, 의사결정 능력, 재무 이해, 그리고 지원자의 사업 성장 기여 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요.",
    "OSAT": "당신은 전문 OSAT 분야 채용 담당자입니다. 제공된 이력서를 바탕으로 반도체 패키징, 테스트 공정 이해, 수율 개선 경험, 장비 운용 능력, 그리고 지원자의 OSAT 산업 기여 가능성에 초점을 맞춰 한국어로 구체적인 요약 및 추천 사유를 작성해주세요."
}

# 직무 표시 이름 매핑
PERSONA_DISPLAY_NAMES = {
    "공정": "공정 (Process) 엔지니어",
    "설계": "설계 (Design) 엔지니어",
    "SW": "SW (Software) 개발자",
    "설비/인프라": "설비/인프라 (Infrastructure)",
    "경영": "경영 (Management) 및 기획",
    "OSAT": "OSAT (반도체 후공정)"
}

COMPETENCY_SYSTEM_PROMPT = """**[System Role]**
당신은 기업의 채용을 담당하는 10년 차 수석 HR 전문가이자 역량 평가 애널리스트입니다.
문서에서 추출된 지원자의 이력서/자기소개서 텍스트를 분석하여, 요구되는 역량의 보유 수준을 객관적으로 평가하는 것이 당신의 역할입니다.

**[Input Data]**
1. 추출된 지원자 텍스트 데이터 (JSON): {resume_data}
2. 평가 대상 직무 핵심 역량 (JSON): {job_competency_data}
3. 공통 역량 (어학/자격증 등) (JSON): {common_competency_data}

**[Task]**
제공된 텍스트 데이터를 꼼꼼히 읽고, 직무 핵심 역량과 공통 역량 각각에 대해 지원자의 수준을 분석하고 평가하십시오.

**[Evaluation Guidelines (Anti-Hallucination - 필수 준수)]**
1. 팩트 기반 검증 (Fact-checking): 텍스트 내에 흩어져 있는 구체적인 사실(경험, 행동, 자격증, 어학 점수)에 기반해서만 평가하십시오.
2. 절대 지어내지 마십시오: 이력서/자소서에 명시되지 않은 스펙(예: 기재되지 않은 자격증, 언급되지 않은 어학 점수 등)은 절대로 있다고 가정하거나 지어내어 평가해서는 안 됩니다. 명시된 내용(예: "오픽 AL")만 근거로 삼으십시오.
3. 데이터가 부족한 경우: 평가할 근거가 이력서에 부족하거나 없다면 등급을 '하'로 부여하고, "이력서 상 관련 경험/자격이 명시되어 있지 않음"이라고 이유를 작성하십시오.
4. 등급 (상/중/하):
   - 상: 탁월한 성과, 수치화된 데이터, 구체적인 사례 및 명확한 자격증/스펙이 기재된 경우
   - 중: 일반적인 경험, 추상적인 서술, 보통 수준의 자격증이 기재된 경우
   - 하: 관련 내용이 전혀 언급되어 있지 않거나 매우 부족한 경우

**[Output Format Requirements]**
결과는 반드시 아래의 JSON 스키마를 엄격히 준수하여 출력해야 하며, JSON 외의 추가적인 인사말, 설명, 마크다운 백틱(```)은 절대 포함하지 마십시오.

{{
  "job_evaluations": [
    {{
      "competency": "평가한 직무 역량 이름",
      "grade": "상/중/하",
      "reason": "평가 근거 (반드시 이력서에 기재된 팩트만 서술, 1~2문장)"
    }}
  ],
  "common_evaluations": [
    {{
      "competency": "어학 및 자격증",
      "grade": "상/중/하",
      "reason": "평가 근거 (반드시 이력서에 명시된 어학 점수, 자격증만 서술. 없다면 없다고 서술)"
    }}
  ]
}}"""

HTML_PAGE = '''
<!DOCTYPE html>
<html data-theme="light">
<head>
    <title>Resume Insight Pro - Semiconductor Edition</title>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Rajdhani:wght@500;700&family=Noto+Sans+KR:wght@300;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Light Theme (Default) - Comfortable & Professional */
            --bg-color: #f4f6f9;
            --panel-bg: rgba(255, 255, 255, 0.88);
            --accent-main: #0056b3;
            --accent-glow: rgba(0, 86, 179, 0.4);
            --accent-blue: #004494;
            --text-main: #2c3e50;
            --text-muted: #5a6a7c;
            --border-color: rgba(0, 0, 0, 0.1);
            --border-glow: rgba(0, 86, 179, 0.15);
            --bg-image: url('/static/bg_light.jpg');
            --btn-text: #ffffff;
            --gradient-start: #007bff;
            --gradient-end: #0056b3;
            --tab-active-bg: rgba(227, 242, 253, 0.8);
            --tab-active-text: #0056b3;
            --list-bullet: #0056b3;
            --panel-shadow: 0 10px 30px rgba(0, 0, 0, 0.08), 0 0 15px rgba(0, 86, 179, 0.05);
            --input-bg: rgba(255, 255, 255, 0.95);
            --result-bg: rgba(248, 250, 252, 0.8);
            --consulting-card-bg: rgba(255, 255, 255, 0.92);
            --consulting-card-border: rgba(0, 86, 179, 0.12);
            --consulting-card-shadow: 0 8px 32px rgba(0, 86, 179, 0.08);
            --consulting-card-hover-shadow: 0 16px 48px rgba(0, 86, 179, 0.18);
            --consulting-icon-bg: rgba(0, 86, 179, 0.08);
            --consulting-detail-bg: rgba(0, 86, 179, 0.04);
            --consulting-detail-bullet: #0056b3;
        }

        [data-theme="dark"] {
            /* Dark Theme (Neon Cybernetic) */
            --bg-color: #0b0f19;
            --panel-bg: rgba(15, 23, 42, 0.85);
            --accent-main: #00ffcc;
            --accent-glow: rgba(0, 255, 204, 0.4);
            --accent-blue: #00d2ff;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --border-color: rgba(0, 255, 204, 0.15);
            --border-glow: rgba(0, 255, 204, 0.4);
            --bg-image: url('/static/bg.jpg');
            --btn-text: #0b0f19;
            --gradient-start: #00d2ff;
            --gradient-end: #00ffcc;
            --tab-active-bg: linear-gradient(135deg, rgba(0, 255, 204, 0.15) 0%, rgba(0, 210, 255, 0.15) 100%);
            --tab-active-text: #00ffcc;
            --list-bullet: #00ffcc;
            --panel-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 0 30px rgba(0, 255, 204, 0.05);
            --input-bg: rgba(15, 23, 42, 0.9);
            --result-bg: rgba(15, 23, 42, 0.6);
            --consulting-card-bg: rgba(15, 23, 42, 0.7);
            --consulting-card-border: rgba(0, 255, 204, 0.15);
            --consulting-card-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            --consulting-card-hover-shadow: 0 16px 48px rgba(0, 255, 204, 0.12);
            --consulting-icon-bg: rgba(0, 255, 204, 0.1);
            --consulting-detail-bg: rgba(0, 255, 204, 0.05);
            --consulting-detail-bullet: #00ffcc;
        }
        
        body {
            font-family: 'Noto Sans KR', sans-serif;
            margin: 0;
            padding: 40px 20px;
            background-color: var(--bg-color);
            background-image: var(--bg-image);
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            transition: all 0.4s ease;
        }

        /* Dark overlay to soften the background image slightly */
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: var(--bg-color);
            opacity: 0.15;
            z-index: -1;
            pointer-events: none;
            transition: opacity 0.4s ease;
        }

        [data-theme="dark"] body::before {
            opacity: 0.85; /* Darker overlay in dark mode */
        }

        .container {
            width: 100%;
            max-width: 950px;
            background: var(--panel-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            padding: 40px;
            border-radius: 20px;
            border: 1px solid var(--border-color);
            box-shadow: var(--panel-shadow);
            transition: all 0.4s ease;
            position: relative;
            overflow: hidden;
        }

        /* Decorative semiconductor line animation */
        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, transparent, var(--accent-main), var(--accent-blue), transparent);
            animation: circuit-flow 3s linear infinite;
        }

        @keyframes circuit-flow {
            0% { background-position: -950px 0; }
            100% { background-position: 950px 0; }
        }
        
        .header-wrapper {
            position: relative;
            margin-bottom: 35px;
        }

        h2 {
            font-family: 'Orbitron', sans-serif;
            text-align: center;
            font-size: 2.2rem;
            letter-spacing: 2px;
            margin: 0;
            background: linear-gradient(to right, var(--accent-main), var(--accent-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 15px rgba(0, 0, 0, 0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }

        [data-theme="dark"] h2 {
            text-shadow: 0 0 15px rgba(0, 255, 204, 0.2);
        }

        /* Theme Toggle Button */
        .theme-toggle {
            position: absolute;
            right: 0;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: 1px solid var(--border-color);
            border-radius: 50px;
            padding: 8px 16px;
            color: var(--text-main);
            font-family: 'Rajdhani', sans-serif;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
        }

        .theme-toggle:hover {
            border-color: var(--accent-main);
            box-shadow: 0 0 10px var(--border-glow);
        }

        /* Side Menu styling */
        .hamburger-btn {
            position: fixed;
            top: 25px;
            left: 25px;
            z-index: 1000;
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            width: 50px;
            height: 50px;
            border-radius: 12px;
            cursor: pointer;
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
        }

        .hamburger-btn:hover {
            border-color: var(--accent-main);
            box-shadow: 0 0 15px var(--border-glow);
            transform: scale(1.05);
        }

        .side-menu {
            position: fixed;
            top: 0;
            left: -320px;
            width: 280px;
            height: 100vh;
            background: var(--bg-color);
            box-shadow: 4px 0 25px rgba(0,0,0,0.1);
            z-index: 1001;
            transition: left 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
            padding: 80px 20px 20px;
            display: flex;
            flex-direction: column;
            gap: 15px;
            border-right: 1px solid var(--border-color);
        }

        .side-menu.open {
            left: 0;
        }

        .side-menu-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0,0,0,0.4);
            backdrop-filter: blur(3px);
            z-index: 1000;
            display: none;
            opacity: 0;
            transition: opacity 0.4s ease;
        }

        .side-menu-overlay.open {
            display: block;
            opacity: 1;
        }

        .menu-link {
            padding: 16px 20px;
            cursor: pointer;
            border: none;
            background: transparent;
            font-size: 16px;
            font-weight: 700;
            color: var(--text-muted);
            border-radius: 12px;
            transition: all 0.3s ease;
            font-family: 'Orbitron', 'Rajdhani', sans-serif;
            text-align: left;
            width: 100%;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .menu-link:hover {
            background: rgba(0, 0, 0, 0.03);
            color: var(--text-main);
        }

        [data-theme="dark"] .menu-link:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .menu-link.active {
            color: var(--accent-main);
            background: rgba(0, 86, 179, 0.08);
            box-shadow: inset 3px 0 0 var(--accent-main);
        }

        [data-theme="dark"] .menu-link.active {
            background: rgba(0, 255, 204, 0.1);
            box-shadow: inset 3px 0 0 var(--accent-main);
        }

        .tab-content {
            display: none;
            animation: fadeIn 0.5s ease-in-out;
        }

        .tab-content.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* ===== CORE UPLOAD REDESIGN ===== */
        .persona-btn-group {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 30px;
            justify-content: center;
        }

        .persona-btn {
            padding: 12px 20px;
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            color: var(--text-main);
            border-radius: 12px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: 'Noto Sans KR', sans-serif;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02);
        }

        .persona-btn:hover {
            border-color: var(--accent-main);
            box-shadow: 0 4px 12px var(--border-glow);
            transform: translateY(-2px);
        }

        .persona-btn.selected {
            background: var(--accent-main);
            color: #fff;
            border-color: var(--accent-main);
            box-shadow: 0 4px 15px var(--accent-glow);
        }

        .upload-dropzone {
            background: var(--input-bg);
            border: 2px dashed var(--border-color);
            border-radius: 20px;
            padding: 60px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            position: relative;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.02);
        }

        .upload-dropzone:hover, .upload-dropzone.dragover {
            border-color: var(--accent-main);
            background: rgba(0, 86, 179, 0.02);
        }

        [data-theme="dark"] .upload-dropzone:hover, [data-theme="dark"] .upload-dropzone.dragover {
            background: rgba(0, 255, 204, 0.05);
        }

        .upload-icon {
            font-size: 4rem;
            margin-bottom: 20px;
        }

        .upload-title {
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 10px;
        }

        .upload-subtitle {
            font-size: 1rem;
            color: var(--text-muted);
            margin-bottom: 30px;
        }

        .upload-btn {
            background: #4763F7;
            color: white;
            border: none;
            padding: 16px 40px;
            border-radius: 8px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 4px 15px rgba(71, 99, 247, 0.3);
            margin-bottom: 15px;
            display: inline-block;
            font-family: 'Noto Sans KR', sans-serif;
        }

        .upload-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(71, 99, 247, 0.4);
        }

        .sample-resume-btn {
            display: inline-block;
            background: #ffffff;
            color: #000000;
            border: 1.5px solid #000000;
            padding: 11px 28px;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-bottom: 15px;
            font-family: 'Noto Sans KR', sans-serif;
            text-decoration: none;
        }

        .sample-resume-btn:hover {
            background: #f7f7f7;
            transform: translateY(-1px);
            text-decoration: none;
        }

        .upload-drag-text {
            color: var(--text-muted);
            font-size: 0.95rem;
        }

        .file-selected-text {
            color: var(--accent-main);
            font-weight: 700;
            font-size: 1.1rem;
            margin-top: 20px;
            display: none;
        }

        .btn {
            background: linear-gradient(135deg, var(--gradient-start) 0%, var(--gradient-end) 100%);
            color: var(--btn-text);
            border: none;
            padding: 16px 32px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 700;
            width: 100%;
            transition: all 0.3s ease;
            box-shadow: 0 5px 15px var(--border-glow);
            text-transform: uppercase;
            letter-spacing: 1px;
            font-family: 'Rajdhani', sans-serif;
        }

        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px var(--accent-glow);
        }

        .btn:disabled {
            background: #cbd5e1;
            color: #64748b;
            cursor: not-allowed;
            box-shadow: none;
        }

        [data-theme="dark"] .btn:disabled {
            background: #1e293b;
            color: #475569;
        }

        /* Loading UI */
        .loading-container {
            display: none;
            flex-direction: column;
            align-items: center;
            margin-top: 30px;
        }

        .pulse-loader {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--accent-main);
            animation: pulse 1.5s infinite ease-in-out;
            box-shadow: 0 0 20px var(--accent-glow);
        }

        @keyframes pulse {
            0% { transform: scale(0.6); opacity: 0.8; }
            100% { transform: scale(1.2); opacity: 0; }
        }

        .loading-text {
            color: var(--accent-main);
            margin-top: 15px;
            font-weight: 600;
            letter-spacing: 1px;
            animation: text-pulse 1.5s infinite alternate;
        }

        @keyframes text-pulse {
            0% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        /* Results view elements */
        h3 {
            font-family: 'Orbitron', sans-serif;
            color: var(--accent-main);
            font-size: 1.2rem;
            border-left: 3px solid var(--accent-main);
            padding-left: 12px;
            margin-top: 30px;
            margin-bottom: 15px;
        }

        #llmAnalysisResult {
            white-space: pre-wrap;
            background: var(--result-bg);
            padding: 24px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            line-height: 1.8;
            margin-bottom: 25px;
            color: var(--text-main);
        }

        .carousel-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
        }
        
        .carousel-dots {
            display: flex;
            gap: 8px;
            margin-top: 15px;
            margin-bottom: 5px;
        }
        
        .carousel-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: rgba(0,0,0,0.15);
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        [data-theme="dark"] .carousel-dot {
            background: rgba(255,255,255,0.2);
        }
        
        .carousel-dot.active {
            background: var(--accent-main);
            width: 24px;
            border-radius: 4px;
        }

        /* ===== COMPETENCY GRADE VISUALIZATION (SCROLL) ===== */
        .carousel-wrapper {
            display: flex;
            align-items: flex-start;
            overflow-x: auto;
            gap: 20px;
            padding: 20px 5px;
            margin-top: 10px;
            width: 100%;
            scroll-behavior: smooth;
            scroll-snap-type: x mandatory;
            -ms-overflow-style: none;
            scrollbar-width: none;
            cursor: grab;
            user-select: none;
            touch-action: pan-y;
        }

        .carousel-wrapper.dragging {
            cursor: grabbing;
            scroll-behavior: auto;
            scroll-snap-type: none;
        }
        
        .carousel-wrapper::-webkit-scrollbar {
            display: none;
        }

        .comp-card {
            flex: 0 0 250px;
            height: 250px;
            scroll-snap-align: start;
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.04);
            border-radius: 20px;
            padding: 30px 24px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            gap: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.03);
            transition: all 0.35s cubic-bezier(0.25, 1, 0.5, 1);
            cursor: pointer;
            position: relative;
            word-break: keep-all;
        }
        
        [data-theme="dark"] .comp-card {
            background: var(--result-bg);
            border-color: var(--border-color);
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }
        
        .comp-card.expanded {
            height: auto;
            min-height: 250px;
            transform: translateY(-4px) scale(1.01);
            box-shadow: 0 15px 35px rgba(0,0,0,0.08);
            z-index: 10;
            border: 1px solid var(--accent-main);
            cursor: pointer;
            justify-content: flex-start;
            align-items: flex-start;
            text-align: left;
        }
        
        .comp-card-common {
            height: 180px;
        }
        
        .comp-card-common.expanded {
            min-height: 180px;
        }
        
        [data-theme="dark"] .comp-card.expanded {
            box-shadow: 0 12px 25px rgba(0, 255, 204, 0.1);
        }

        .comp-card-high {
            background: rgba(34, 197, 94, 0.08);
            border-color: rgba(34, 197, 94, 0.25);
            box-shadow: 0 4px 12px rgba(34, 197, 94, 0.08);
        }

        [data-theme="dark"] .comp-card-high {
            background: rgba(34, 197, 94, 0.1);
            border-color: rgba(34, 197, 94, 0.3);
            box-shadow: 0 4px 16px rgba(34, 197, 94, 0.1);
        }

        .comp-card-high .comp-card-title {
            color: #16a34a;
        }

        [data-theme="dark"] .comp-card-high .comp-card-title {
            color: #4ade80;
        }

        .comp-card-low .comp-card-title {
            color: #dc2626;
        }

        [data-theme="dark"] .comp-card-low .comp-card-title {
            color: #f87171;
        }

        .comp-card-header {
            display: flex;
            justify-content: center;
            align-items: center;
            width: 100%;
        }
        
        .comp-card.expanded .comp-card-header {
            justify-content: flex-start;
        }

        .comp-card-title {
            font-weight: 700;
            color: var(--text-main);
            font-size: 1.2em;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .comp-card-indicator-high {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: rgba(34, 197, 94, 0.15);
            color: #16a34a;
            font-size: 14px;
            flex-shrink: 0;
        }

        [data-theme="dark"] .comp-card-indicator-high {
            background: rgba(34, 197, 94, 0.2);
            color: #4ade80;
        }

        .comp-card-indicator-low {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: rgba(239, 68, 68, 0.12);
            color: #dc2626;
            font-size: 14px;
            flex-shrink: 0;
        }

        [data-theme="dark"] .comp-card-indicator-low {
            background: rgba(239, 68, 68, 0.18);
            color: #f87171;
        }

        .comp-card-reason {
            font-size: 0.95em;
            color: var(--text-muted);
            line-height: 1.6;
            display: none;
        }

        .comp-card.expanded .comp-card-reason {
            display: block;
            margin-top: 10px;
            opacity: 1;
            animation: fadeIn 0.4s ease forwards;
        }
        
        .comp-card-action {
            margin-top: 15px;
            padding-top: 15px;
            color: var(--accent-blue);
            font-weight: 700;
            font-size: 0.9em;
            text-align: right;
            transition: color 0.3s ease;
        }
        
        .comp-card:hover .comp-card-action {
            color: var(--accent-main);
        }

        .comp-card.expanded .comp-card-action {
            display: none;
        }

        #competencyAnalysisResult {
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            background: var(--result-bg);
            margin-bottom: 25px;
        }

        .competency-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 10px;
            border-bottom: 1px dashed var(--border-color);
        }

        .competency-item:last-child {
            border-bottom: none;
        }

        .competency-name {
            font-weight: 500;
            color: var(--text-main);
        }

        .competency-rating {
            font-family: 'Rajdhani', sans-serif;
            font-size: 1.2em;
            font-weight: 700;
            color: var(--accent-main);
            text-shadow: 0 0 8px rgba(0, 0, 0, 0.05);
        }
        
        [data-theme="dark"] .competency-rating {
            text-shadow: 0 0 8px rgba(0, 255, 204, 0.4);
        }

        ul {
            list-style-type: none;
            padding: 0;
            margin: 0;
        }

        li {
            margin-bottom: 12px;
            padding-left: 20px;
            position: relative;
        }

        li::before {
            content: '◆';
            position: absolute;
            left: 0;
            color: var(--list-bullet);
            font-size: 10px;
            top: 6px;
        }

        a {
            color: var(--accent-main);
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }

        a:hover {
            color: var(--accent-blue);
            text-decoration: underline;
        }
        
        /* ===== AI CAREER CONSULTING SPLIT-PANE ===== */
        .consulting-split-layout {
            display: flex;
            gap: 20px;
            margin-top: 20px;
            min-height: 550px;
            background: var(--consulting-card-bg);
            border: 1px solid var(--consulting-card-border);
            border-radius: 16px;
            box-shadow: var(--consulting-card-shadow);
            overflow: hidden;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
        }

        .consulting-sidebar {
            width: 35%;
            background: rgba(0,0,0,0.02);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            max-height: 600px;
        }

        [data-theme="dark"] .consulting-sidebar {
            background: rgba(255,255,255,0.02);
        }

        .consulting-sidebar-item {
            padding: 20px;
            cursor: pointer;
            border-bottom: 1px solid var(--border-color);
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 15px;
            border-left: 4px solid transparent;
        }

        .consulting-sidebar-item:hover {
            background: var(--consulting-detail-bg);
        }

        .consulting-sidebar-item.active {
            background: var(--consulting-detail-bg);
            border-left: 4px solid var(--accent-main);
        }

        .consulting-sidebar-icon {
            font-size: 1.8rem;
            width: 50px;
            height: 50px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--consulting-icon-bg);
            border-radius: 12px;
            flex-shrink: 0;
        }

        .consulting-sidebar-text {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .consulting-sidebar-title {
            font-family: 'Rajdhani', sans-serif;
            font-weight: 700;
            color: var(--text-main);
            font-size: 1.15rem;
        }

        .consulting-sidebar-subtitle {
            font-size: 0.85rem;
            color: var(--text-muted);
            line-height: 1.4;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }

        .consulting-content-view {
            width: 65%;
            padding: 35px 30px;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            max-height: 600px;
        }

        .consulting-content-header {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-bottom: 25px;
        }

        .consulting-content-title {
            font-family: 'Rajdhani', sans-serif;
            font-size: 1.6rem;
            font-weight: 700;
            color: var(--text-main);
        }

        .consulting-content-summary-box {
            background: var(--consulting-detail-bg);
            border-left: 4px solid var(--accent-main);
            padding: 20px;
            border-radius: 0 12px 12px 0;
            margin-bottom: 30px;
            color: var(--accent-blue);
            font-weight: 700;
            font-size: 1.1rem;
            line-height: 1.5;
        }
        
        [data-theme="dark"] .consulting-content-summary-box {
            color: var(--accent-main);
        }

        .consulting-content-details {
            list-style: none;
            padding: 0;
            margin: 0 0 40px 0;
            flex-grow: 1;
        }

        .consulting-content-details li {
            position: relative;
            padding-left: 24px;
            margin-bottom: 16px;
            line-height: 1.6;
            color: var(--text-muted);
            font-size: 1.05rem;
            border-bottom: none;
        }

        .consulting-content-details li::before {
            content: "•";
            position: absolute;
            left: 0;
            color: var(--accent-main);
            font-size: 1.5rem;
            top: -4px;
        }

        .consulting-resources-title {
            font-family: 'Rajdhani', sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-top: 25px;
            border-top: 1px dashed var(--border-color);
        }

        .consulting-resources-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            padding-bottom: 20px;
        }

        .resource-pill {
            padding: 10px 18px;
            background: rgba(0, 86, 179, 0.08);
            color: var(--accent-blue);
            border-radius: 30px;
            text-decoration: none;
            font-weight: 700;
            font-size: 0.95rem;
            transition: all 0.2s;
            border: 1px solid rgba(0, 86, 179, 0.15);
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        [data-theme="dark"] .resource-pill {
            background: rgba(0, 255, 204, 0.08);
            color: var(--accent-main);
            border: 1px solid rgba(0, 255, 204, 0.15);
        }

        .resource-pill:hover {
            transform: translateY(-2px);
            background: var(--accent-main);
            color: white;
            border-color: var(--accent-main);
            text-decoration: none;
        }

        .consulting-placeholder {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }

        .consulting-placeholder-icon {
            font-size: 3rem;
            margin-bottom: 15px;
            opacity: 0.5;
        }

        .consulting-placeholder-text {
            font-size: 1rem;
            line-height: 1.6;
        }

        @keyframes cardSlideIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .consulting-card.animate-in {
            animation: cardSlideIn 0.5s ease-out forwards;
        }
    </style>
</head>
<body>
    <!-- Side Menu -->
    <button class="hamburger-btn" onclick="toggleSideMenu()">☰</button>
    <div class="side-menu-overlay" id="sideMenuOverlay" onclick="toggleSideMenu()"></div>
    <div class="side-menu" id="sideMenu">
        <h3 style="margin: 0 0 20px 10px; color: var(--accent-main); font-family: 'Orbitron', sans-serif; letter-spacing: 2px;">MENU</h3>
        <button class="menu-link active" onclick="openTab(event, 'uploadTab')">🔵 HOME</button>
        <button class="menu-link" id="resultTabBtn" onclick="openTab(event, 'resultTab')">🔵 ANALYSIS</button>
        <button class="menu-link" id="consultingTabBtn" onclick="openTab(event, 'consultingTab')">🔵 CONSULTING</button>
    </div>

    <div class="container">
        <div class="header-wrapper">
            <h2>SEMI ROADMAP</h2>
            <button class="theme-toggle" id="themeToggleBtn" onclick="toggleTheme()">
                🌙 다크 모드
            </button>
        </div>

        <div id="uploadTab" class="tab-content active">
            <form id="uploadForm">
                <!-- Job Persona Buttons -->
                <div class="persona-btn-group" id="personaBtnGroup">
                    <button type="button" class="persona-btn selected" data-value="공정">공정 엔지니어</button>
                    <button type="button" class="persona-btn" data-value="설계">설계 엔지니어</button>
                    <button type="button" class="persona-btn" data-value="SW">SW 엔지니어</button>
                    <button type="button" class="persona-btn" data-value="설비/인프라">설비/인프라</button>
                    <button type="button" class="persona-btn" data-value="경영">경영지원</button>
                    <button type="button" class="persona-btn" data-value="OSAT">OSAT (후공정)</button>
                </div>
                <input type="hidden" name="persona" id="personaHiddenInput" value="공정">

                <!-- Upload Dropzone -->
                <div class="upload-dropzone" id="uploadDropzone">
                    <input type="file" name="file" id="fileInput" accept=".pdf" style="display: none;" required>
                    <div class="upload-icon">📄</div>
                    <div class="upload-title"> PDF 업로드</div>
                    <div class="upload-subtitle">이미지 PDF 업로드 불가 (최대 4MB)</div>
                    <button type="button" class="upload-btn" id="customUploadBtn">파일 선택</button>
                    <a class="sample-resume-btn" href="https://drive.google.com/file/d/1-b7oQsrFxJtreqJTPGP-Sz67MhXRjYVu/view?usp=sharing" target="_blank" rel="noopener noreferrer">샘플 이력서 PDF 다운로드</a>
                    <div class="file-selected-text" id="fileSelectedText">선택된 파일: 없음</div>
                </div>
                
                <input type="submit" class="btn" id="submitBtn" value="업로드하고 분석하기" disabled>
            </form>
            
            <div class="loading-container" id="status">
                <div class="pulse-loader"></div>
                <div class="loading-text">이력서 원천 데이터 추출 및 AI 정밀 분석 중...</div>
            </div>
        </div>

        <div id="resultTab" class="tab-content">
            <h3>ANALYSIS</h3>
            <div id="llmAnalysisResult">대기 중... 먼저 파일 업로드를 수행하십시오.</div>

            <h3>직무별 핵심 역량</h3>
            <div id="jobCompetencyResult">대기 중...</div>

            <h3>공통 역량</h3>
            <div id="commonCompetencyResult">대기 중...</div>

            <div style="text-align: center; margin-top: 50px; margin-bottom: 20px;">
                <button type="button" class="btn" onclick="document.getElementById('consultingTabBtn').click()" style="width: auto; padding: 16px 40px; font-size: 1.1em; border-radius: 30px;"> 컨설팅 결과 보기</button>
            </div>
        </div>

        <div id="consultingTab" class="tab-content">
            <h3> CONSULTING</h3>
            <div id="consultingResult">
                <div class="consulting-placeholder">
                    <div class="consulting-placeholder-icon">🎯</div>
                    <div class="consulting-placeholder-text">
                        이력서 분석 후 AI 컨설턴트가<br>
                        직무 맞춤형 커리어 컨설팅 카드를 생성합니다.<br><br>
                        <strong></strong> 탭에서 이력서를 업로드해주세요.
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        // Theme toggling logic
        function toggleTheme() {
            const htmlElement = document.documentElement;
            const themeBtn = document.getElementById('themeToggleBtn');
            const currentTheme = htmlElement.getAttribute('data-theme');
            
            if (currentTheme === 'light') {
                htmlElement.setAttribute('data-theme', 'dark');
                themeBtn.innerHTML = '☀️ 라이트 모드';
                localStorage.setItem('theme', 'dark');
            } else {
                htmlElement.setAttribute('data-theme', 'light');
                themeBtn.innerHTML = '🌙 다크 모드';
                localStorage.setItem('theme', 'light');
            }
        }

        // Apply saved theme on load
        window.onload = () => {
            const savedTheme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', savedTheme);
            const themeBtn = document.getElementById('themeToggleBtn');
            if (savedTheme === 'dark') {
                themeBtn.innerHTML = '☀️ 라이트 모드';
            }
        };

        window.updateCarouselDots = function(wrapper) {
            const dotsContainer = wrapper.nextElementSibling;
            if (!dotsContainer || !dotsContainer.classList.contains('carousel-dots')) return;
            const scrollLeft = wrapper.scrollLeft;
            const scrollWidth = wrapper.scrollWidth;
            const clientWidth = wrapper.clientWidth;
            const cards = wrapper.children;
            if (cards.length === 0) return;
            
            let activeIndex = 0;
            if (scrollLeft + clientWidth >= scrollWidth - 5) {
                // User has scrolled all the way to the right
                activeIndex = cards.length - 1;
            } else {
                const cardWidth = cards[0].offsetWidth + 20; 
                activeIndex = Math.round(scrollLeft / cardWidth);
            }
            
            if (activeIndex < 0) activeIndex = 0;
            if (activeIndex >= cards.length) activeIndex = cards.length - 1;
            
            const dots = dotsContainer.querySelectorAll('.carousel-dot');
            dots.forEach((dot, index) => {
                dot.classList.toggle('active', index === activeIndex);
            });
        };

        function enableCarouselDrag(wrapper) {
            if (!wrapper || wrapper.dataset.dragBound === 'true') return;
            wrapper.dataset.dragBound = 'true';

            let isDown = false;
            let startX = 0;
            let startScrollLeft = 0;
            let hasDragged = false;
            let hasPointerCapture = false;

            wrapper.addEventListener('pointerdown', (event) => {
                if (event.button !== 0 || event.pointerType === 'touch') return;

                isDown = true;
                hasDragged = false;
                wrapper.dataset.dragged = 'false';
                startX = event.clientX;
                startScrollLeft = wrapper.scrollLeft;
                wrapper.classList.add('dragging');
            });

            wrapper.addEventListener('pointermove', (event) => {
                if (!isDown) return;

                const deltaX = event.clientX - startX;
                if (Math.abs(deltaX) > 8) {
                    hasDragged = true;
                    wrapper.dataset.dragged = 'true';
                    if (!hasPointerCapture) {
                        wrapper.setPointerCapture(event.pointerId);
                        hasPointerCapture = true;
                    }
                }
                wrapper.scrollLeft = startScrollLeft - deltaX;
            });

            const endDrag = (event) => {
                if (!isDown) return;

                isDown = false;
                hasPointerCapture = false;
                wrapper.classList.remove('dragging');
                if (wrapper.hasPointerCapture(event.pointerId)) {
                    wrapper.releasePointerCapture(event.pointerId);
                }
                updateCarouselDots(wrapper);
            };

            wrapper.addEventListener('pointerup', endDrag);
            wrapper.addEventListener('pointercancel', endDrag);
            wrapper.addEventListener('pointerleave', endDrag);
            wrapper.addEventListener('click', (event) => {
                if (wrapper.dataset.dragged === 'true') {
                    event.preventDefault();
                    event.stopPropagation();
                    wrapper.dataset.dragged = 'false';
                }
            }, true);
        }

        function initCarouselDrag() {
            document.querySelectorAll('.carousel-wrapper').forEach(enableCarouselDrag);
        }

        function toggleSideMenu() {
            const sideMenu = document.getElementById('sideMenu');
            const overlay = document.getElementById('sideMenuOverlay');
            sideMenu.classList.toggle('open');
            overlay.classList.toggle('open');
        }

        // Run UI binding after DOM is fully loaded to prevent JS errors
        document.addEventListener('DOMContentLoaded', () => {
            // Job Persona Button Logic
            const personaBtns = document.querySelectorAll('.persona-btn');
            const personaHiddenInput = document.getElementById('personaHiddenInput');
            if(personaBtns.length > 0 && personaHiddenInput) {
                personaBtns.forEach(btn => {
                    btn.addEventListener('click', () => {
                        personaBtns.forEach(b => b.classList.remove('selected'));
                        btn.classList.add('selected');
                        personaHiddenInput.value = btn.getAttribute('data-value');
                    });
                });
            }

            // Drag and Drop Upload Logic
            const dropzone = document.getElementById('uploadDropzone');
            const fileInput = document.getElementById('fileInput');
            const customUploadBtn = document.getElementById('customUploadBtn');
            const fileSelectedText = document.getElementById('fileSelectedText');
            const submitBtn = document.getElementById('submitBtn');

            if(dropzone && fileInput && customUploadBtn) {
                customUploadBtn.addEventListener('click', () => {
                    fileInput.click();
                });

                fileInput.addEventListener('change', handleFileSelect);

                dropzone.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropzone.classList.add('dragover');
                });

                dropzone.addEventListener('dragleave', (e) => {
                    e.preventDefault();
                    dropzone.classList.remove('dragover');
                });

                dropzone.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropzone.classList.remove('dragover');
                    if (e.dataTransfer.files.length) {
                        fileInput.files = e.dataTransfer.files;
                        handleFileSelect();
                    }
                });

                function handleFileSelect() {
                    if (fileInput.files.length > 0) {
                        fileSelectedText.innerText = `✅ 선택된 파일: ${fileInput.files[0].name}`;
                        fileSelectedText.style.display = 'block';
                        submitBtn.disabled = false;
                        submitBtn.value = "분석 시작";
                        // Scroll to submit button smoothly
                        setTimeout(() => {
                            submitBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }, 100);
                    } else {
                        fileSelectedText.style.display = 'none';
                        submitBtn.disabled = true;
                        submitBtn.value = "업로드 하고 분석하기";
                    }
                }
            }
        });

        function openTab(evt, tabName) {
            const contents = document.getElementsByClassName("tab-content");
            for (let i = 0; i < contents.length; i++) contents[i].classList.remove("active");
            const links = document.getElementsByClassName("menu-link");
            for (let i = 0; i < links.length; i++) links[i].classList.remove("active");
            document.getElementById(tabName).classList.add("active");
            evt.currentTarget.classList.add("active");

            // Close sidebar when a tab is clicked
            const sideMenu = document.getElementById('sideMenu');
            const overlay = document.getElementById('sideMenuOverlay');
            if(sideMenu.classList.contains('open')) {
                sideMenu.classList.remove('open');
                overlay.classList.remove('open');
            }
        }

        window.consultingCardsData = []; // Store cards globally for click events

        window.selectConsultingCard = function(index) {
            // Update Sidebar Active State
            const items = document.querySelectorAll('.consulting-sidebar-item');
            items.forEach((el, i) => {
                if(i === index) el.classList.add('active');
                else el.classList.remove('active');
            });

            // Update Main Content
            const card = window.consultingCardsData[index];
            if(!card) return;

            let detailsHtml = '<ul class="consulting-content-details">';
            if(card.details && card.details.length) {
                card.details.forEach(d => {
                    detailsHtml += `<li>${d}</li>`;
                });
            }
            detailsHtml += '</ul>';

            let resourcesHtml = '';
            if (card.resources && card.resources.length) {
                resourcesHtml += '<div class="consulting-resources-title">🔗 추천 리소스</div>';
                resourcesHtml += '<div class="consulting-resources-grid">';
                card.resources.forEach(res => {
                    resourcesHtml += `<a href="${res.url}" target="_blank" class="resource-pill">📝 ${res.name} ↗</a>`;
                });
                resourcesHtml += '</div>';
            }

            const contentView = document.getElementById('consultingContentView');
            contentView.innerHTML = `
                <div class="consulting-content-header">
                    <div class="consulting-sidebar-icon" style="font-size:2rem; width:60px; height:60px;">${card.icon || '📋'}</div>
                    <div class="consulting-content-title">${card.title}</div>
                </div>
                <div class="consulting-content-summary-box">${card.summary}</div>
                ${detailsHtml}
                ${resourcesHtml}
            `;
        };

        function renderConsultingCards(cards) {
            const container = document.getElementById('consultingResult');
            if (!cards || cards.length === 0) {
                container.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:40px;">컨설팅 데이터를 생성하지 못했습니다.</p>';
                return;
            }

            window.consultingCardsData = cards;
            
            let sidebarHtml = '<div class="consulting-sidebar" id="consultingSidebar">';
            cards.forEach((card, index) => {
                sidebarHtml += `
                    <div class="consulting-sidebar-item ${index === 0 ? 'active' : ''}" onclick="selectConsultingCard(${index})">
                        <div class="consulting-sidebar-icon">${card.icon || '📋'}</div>
                        <div class="consulting-sidebar-text">
                            <div class="consulting-sidebar-title">${card.title}</div>
                            <div class="consulting-sidebar-subtitle">${card.summary}</div>
                        </div>
                    </div>
                `;
            });
            sidebarHtml += '</div>';
            
            const contentHtml = '<div class="consulting-content-view" id="consultingContentView"></div>';

            container.innerHTML = `<div class="consulting-split-layout">${sidebarHtml}${contentHtml}</div>`;
            
            // Automatically select the first item to render its content
            setTimeout(() => {
                selectConsultingCard(0);
            }, 50);
        }

        document.getElementById('uploadForm').onsubmit = async (e) => {
            e.preventDefault();
            const status = document.getElementById('status');
            const btn = document.getElementById('submitBtn');
            const llmResultDiv = document.getElementById('llmAnalysisResult');
            const jobCompetencyResultDiv = document.getElementById('jobCompetencyResult');
            const commonCompetencyResultDiv = document.getElementById('commonCompetencyResult');
            const consultingResultDiv = document.getElementById('consultingResult');

            status.style.display = "flex";
            btn.disabled = true;
            llmResultDiv.innerText = "분석 연산 처리 중...";
            jobCompetencyResultDiv.innerText = "분석 연산 처리 중...";
            commonCompetencyResultDiv.innerText = "분석 연산 처리 중...";
            consultingResultDiv.innerHTML = '<div class="consulting-placeholder"><div class="pulse-loader" style="margin:0 auto;"></div><div class="loading-text" style="margin-top:20px;">AI 컨설턴트가 맞춤형 컨설팅 카드를 생성 중...</div></div>';

            const formData = new FormData(e.target);
            try {
                const res = await fetch('/api/analyze_resume', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.error) {
                    alert("에러: " + data.error);
                    status.style.display = "none";
                } else {
                    if (typeof data.llm_analysis === 'object') {
                        llmResultDiv.style.whiteSpace = 'normal';
                        let html = `
                            <div style="background: var(--bg-color); padding: 15px; border-radius: 10px; border-left: 4px solid var(--accent-main); margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                                <strong style="color: var(--accent-main);">💡 핵심 요약</strong>
                                <p style="margin: 10px 0 0 0; color: var(--text-main); font-weight: 500; font-size: 1.05em;">${data.llm_analysis.summary}</p>
                            </div>
                            <div>
                                <strong style="color: var(--accent-main); display: block; margin-bottom: 10px;">✨ 주요 강점</strong>
                                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                        `;
                        data.llm_analysis.strengths.forEach(s => {
                            html += `<span style="background: linear-gradient(135deg, var(--gradient-start) 0%, var(--gradient-end) 100%); color: var(--btn-text); padding: 6px 16px; border-radius: 25px; font-size: 0.9em; font-weight: 700; letter-spacing: 0.5px; box-shadow: 0 4px 15px var(--border-glow);">${s}</span>`;
                        });
                        html += `
                                </div>
                            </div>
                        `;
                        llmResultDiv.innerHTML = html;
                    } else {
                        llmResultDiv.innerText = data.llm_analysis;
                    }

                    // Reusable card creation logic
                    const createCard = (item, isCommon = false) => {
                        let cardClass = 'comp-card';
                        if (isCommon) cardClass += ' comp-card-common';
                        let titleIndicator = '';
                        if (item.grade === '상') {
                            cardClass += ' comp-card-high';
                            titleIndicator = '<span class="comp-card-indicator-high">✓</span>';
                        } else if (item.grade === '하') {
                            cardClass += ' comp-card-low';
                            titleIndicator = '<span class="comp-card-indicator-low">⚠</span>';
                        }
                        
                        const safeCompetency = (item.competency || "").replace(/_/g, ' ');
                        const safeReason = (item.reason || "").replace(/_/g, ' ');
                        
                        return `<div class="${cardClass}" onclick="expandCard(this)">
                                    <div class="comp-card-header">
                                        <span class="comp-card-title">${safeCompetency} ${titleIndicator}</span>
                                    </div>
                                    <div class="comp-card-reason">${safeReason}</div>
                                    <div class="comp-card-action">🔍 자세히 알아보기</div>
                                </div>`;
                    };

                    const renderCarousel = (items, isCommon = false) => {
                        if (!items || items.length === 0) return '<p style="color:var(--text-muted);">데이터가 제공되지 않았습니다.</p>';
                        
                        let html = '<div class="carousel-container">';
                        html += '<div class="carousel-wrapper" onscroll="updateCarouselDots(this)">';
                        html += items.map(item => createCard(item, isCommon)).join('');
                        html += '</div>';
                        
                        // Render Dots
                        if (items.length > 1) {
                            html += '<div class="carousel-dots">';
                            items.forEach((_, i) => {
                                html += `<div class="carousel-dot ${i === 0 ? 'active' : ''}"></div>`;
                            });
                            html += '</div>';
                        }
                        html += '</div>';
                        return html;
                    };

                    // Render job competency analysis
                    if (data.competency_analysis && data.competency_analysis.job_evaluations && data.competency_analysis.job_evaluations.length > 0) {
                        jobCompetencyResultDiv.innerHTML = renderCarousel(data.competency_analysis.job_evaluations.slice(0, 6), false);
                    } else {
                        jobCompetencyResultDiv.innerHTML = '<p style="color:var(--text-muted);">해당 직무의 역량 데이터 파일이 제공되지 않았습니다. 추후 반영 예정입니다.</p>';
                    }

                    // Render common competency analysis
                    if (data.competency_analysis && data.competency_analysis.common_evaluations && data.competency_analysis.common_evaluations.length > 0) {
                        commonCompetencyResultDiv.innerHTML = renderCarousel(data.competency_analysis.common_evaluations, true);
                    } else {
                        commonCompetencyResultDiv.innerHTML = '<p style="color:var(--text-muted);">공통 역량 평가 결과가 없습니다.</p>';
                    }


                    // Render consulting cards (LLM2 결과)
                    initCarouselDrag();

                    if (data.consulting_cards && data.consulting_cards.length > 0) {
                        renderConsultingCards(data.consulting_cards);
                    } else if (data.consulting_error) {
                        consultingResultDiv.innerHTML = `<div class="consulting-placeholder"><div class="consulting-placeholder-icon">⚠️</div><div class="consulting-placeholder-text">${data.consulting_error}</div></div>`;
                    } else {
                        consultingResultDiv.innerHTML = '<div class="consulting-placeholder"><div class="consulting-placeholder-icon">⚠️</div><div class="consulting-placeholder-text">컨설팅 카드를 생성하지 못했습니다.</div></div>';
                    }

                    status.style.display = "none";
                    document.getElementById('resultTabBtn').click();
                }
            } catch (err) {
                alert("서버 통신 에러가 발생했습니다.");
                status.style.display = "none";
            } finally {
                btn.disabled = false;
            }
        };

        // Carousel Logic
        window.expandCard = function(card) {
            const wrapper = card.closest('.carousel-wrapper');
            if (card.classList.contains('expanded')) {
                card.classList.remove('expanded');
                return;
            }
            
            wrapper.querySelectorAll('.comp-card.expanded').forEach(c => c.classList.remove('expanded'));
            card.classList.add('expanded');
        }
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

@app.route('/api/analyze_resume', methods=['POST'])
def analyze_resume():
    if client is None:
        return jsonify({"error": "UPSTAGE_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요."}), 500

    if 'file' not in request.files:
        return jsonify({"error": "파일이 없습니다."}), 400
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "PDF 파일만 가능합니다."}), 400

    persona_key = request.form.get('persona', '공정')
    base_prompt = PERSONA_PROMPTS.get(persona_key)
    if not base_prompt:
        return jsonify({"error": f"지원하지 않는 페르소나입니다: {persona_key}"}), 400

    # base_prompt에 직무별 맞춤형 출력 형식을 강제
    system_prompt = base_prompt + """
    
    [출력 형식]
    반드시 마크다운이나 다른 설명 없이, 아래 JSON 스키마를 엄격히 준수하여 응답하세요.
    {
        "summary": "지원자에 대한 1~2줄 핵심 요약",
        "strengths": ["주요 강점 1 (단어 또는 짧은 구)", "주요 강점 2", "주요 강점 3"],
        "weakness": "해당 직무 관점에서 지원자가 보완해야 할 점 1줄"
    }
    """

    extracted_text = ""
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: extracted_text += text + "\n"
    except Exception as e:
        return jsonify({"error": f"파일 처리 오류: {str(e)}"}), 500

    if not extracted_text.strip():
        return jsonify({"error": "텍스트를 추출할 수 없습니다."}), 400

    try:
        response = client.chat.completions.create(
            model="solar-pro3",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": extracted_text}
            ],
            temperature=0.1
        )
        raw_llm = response.choices[0].message.content.strip()
        if raw_llm.startswith("```json"): raw_llm = raw_llm[7:]
        elif raw_llm.startswith("```"): raw_llm = raw_llm[3:]
        if raw_llm.endswith("```"): raw_llm = raw_llm[:-3]
        llm_feedback = json.loads(raw_llm.strip())
    except Exception as e:
        llm_feedback = {"summary": f"분석 실패: {str(e)}", "strengths": [], "weakness": ""}

    # 역량별 품질 분석 (새로운 프롬프트 기반 JSON 응답 추출)
    competency_analysis_result = []
    
    # 직무별 역량 데이터 파일 매핑
    file_map = {
        "공정": "process_competency_data.json",
        "설계": "design_competency_data.json",
        "SW": "sw_competency_data.json",
        "설비/인프라": "facilityinfra_competency_data.json",
        "경영": "management_competency_data.json",
        "OSAT": "osat_competency_data.json"
    }
    
    json_filename = file_map.get(persona_key)
    core_competencies = []
    job_competencies_raw = {}
    
    if json_filename:
        if os.path.exists(json_filename):
            try:
                with open(json_filename, "r", encoding="utf-8") as f:
                    comp_data = json.load(f)
                    core_competencies = comp_data.get("competencies", [])
                    job_competencies_raw = comp_data
            except Exception as e:
                print(f"{json_filename} 로드 실패: {e}")

    # 공통 역량 세팅
    COMMON_COMPETENCY = [
        {
            "name": "어학 및 자격증 (공통 역량)",
            "definition": "지원자의 공인어학성적(OPIc, TOEIC 등) 및 직무와 관련된 주요 자격증 보유 현황과 팩트 체크"
        }
    ]

    try:
        comp_prompt = COMPETENCY_SYSTEM_PROMPT.format(
            resume_data=json.dumps({"text": extracted_text}, ensure_ascii=False),
            job_competency_data=json.dumps({"core_competencies": core_competencies}, ensure_ascii=False),
            common_competency_data=json.dumps({"common_competencies": COMMON_COMPETENCY}, ensure_ascii=False)
        )
        
        comp_response = client.chat.completions.create(
            model="solar-pro3",
            messages=[
                {"role": "system", "content": comp_prompt}
            ],
            temperature=0.1
        )
        
        raw_json = comp_response.choices[0].message.content.strip()
        # 마크다운 백틱 제거 처리
        if raw_json.startswith("```json"):
            raw_json = raw_json[7:]
        elif raw_json.startswith("```"):
            raw_json = raw_json[3:]
        if raw_json.endswith("```"):
            raw_json = raw_json[:-3]
            
        parsed = json.loads(raw_json.strip())
        competency_analysis_result = parsed
    except Exception as e:
        competency_analysis_result = {"job_evaluations": [], "common_evaluations": []}
        print(f"평가 모델 오류: {str(e)}")

    # ===== LLM2: 컨설팅 에이전트 호출 =====
    consulting_cards = []
    consulting_error = None
    try:
        target_job_name = PERSONA_DISPLAY_NAMES.get(persona_key, persona_key)
        job_comp_json_str = json.dumps(job_competencies_raw, ensure_ascii=False)
        analysis_json_str = json.dumps({
            "llm_analysis": llm_feedback,
            "competency_analysis": competency_analysis_result
        }, ensure_ascii=False)
        
        llm2_result = generate_consulting_cards(
            target_job=target_job_name,
            job_competencies_json=job_comp_json_str,
            analysis_json_data=analysis_json_str
        )
        
        if "error" in llm2_result:
            consulting_error = llm2_result["error"]
            print(f"LLM2 컨설팅 오류: {consulting_error}")
        else:
            consulting_cards = llm2_result.get("consulting_cards", [])
    except Exception as e:
        consulting_error = f"컨설팅 에이전트 호출 실패: {str(e)}"
        print(consulting_error)

    return jsonify({
        "llm_analysis": llm_feedback,
        "competency_analysis": competency_analysis_result,
        "consulting_cards": consulting_cards,
        "consulting_error": consulting_error
    })

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Resume Insight Pro 서버 시작")
    print("📌 접속 주소: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
