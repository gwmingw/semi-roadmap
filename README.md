# SEMI-ROADMAP

## 🚀 AI Document Builders Challenge with Upstage

---

## 👥 [팀 챌린저스] 팀원 소개

* **구제현** (약학과)
* **민경원** (산업공학과)
* **박재성** (화학공학과)
* **장건** (화학공학과)

반도체 산업에 관심이 높고 취업 준비를 앞둔 학생들로 구성된 팀입니다.

---

## 📌 프로젝트 개요

### 1. 서비스명

> **SEMI-ROADMAP : 반도체 취준생을 위한 스펙 진단 및 성장 로드맵 추천 서비스**

### 2. 기획 배경 (Problem)

* **경험 연결의 어려움:** 반도체 취업 준비생들은 기업의 요구사항(JD)을 이해하기 어렵고, 본인의 경험을 직무 역량과 매칭하는 데 한계를 느낍니다.
* **기존 서비스의 한계:** 범용 LLM은 단일 채용공고 분석에 그치며, 산업·직무 전반을 아우르는 인사이트나 체계적인 역량 프레임워크를 제공하지 못합니다.

### 3. 핵심 아이디어 (Solution)

* 다량의 반도체 기업 채용공고(JD) 데이터를 분석하여 **산업 및 직무 특화 역량 체계**를 도출
* 이를 기반으로 **JD 해석 ➡️ 경험 매칭 ➡️ 갭(Gap) 분석 ➡️ 맞춤형 성장 로드맵**을 제공

---

## Tech Stack

- Frontend: HTML, CSS, JavaScript

- Backend: Flask

- PDF Parsing: pdfplumber

- AI API: Upstage Solar API

- LLM Client: OpenAI Python SDK

- Deployment: GitHub, Vercel

- Data: JSON, CSV

---

## 프로젝트 문서

프로젝트와 관련된 자료는 `docs/` 디렉터리에 정리되어 있습니다.

- `docs/slides/`: 발표 자료

- `docs/DB/`: 직무 그룹별 채용공고 텍스트 데이터

- `docs/charts/`: 직무 그룹별 클러스터링 결과 시각화

- `docs/wordclouds/`: 직무 그룹별 키워드 워드클라우드

- `docs/CV_sample/`: 테스트용 샘플 CV 파일

> 테스트 방법  

서비스 기능을 빠르게 확인하려면 `docs/CV_sample/CV_sample.pdf` 파일을 업로드하여 분석 결과를 확인할 수 있습니다.

---

## 서비스 시연 영상

[서비스 시연 영상 보기](https://www.youtube.com/watch?v=hUBDH0tpKbU)
