# Localight — 네이버 마케팅 대시보드

네이버 검색광고 성과를 자동 수집·분석하고 데일리 리포트로 전달하기 위한 정적 UI MVP입니다.

## 현재 구현 범위

- 캠페인 분류: 플레이스 검색광고, 지역소상공인 광고, 파워링크
- 광고 지표: 광고비, 노출수, 클릭수, 클릭률, 평균 CPC
- 최근 7일/30일 전환, 성과 추이, 캠페인 비교, 데일리 리포트 미리보기
- 네이버 검색광고 API, Slack, 예약/POS, 콜 트래킹 연동 설계 화면
- GitHub Pages 배포

현재 공개 화면에는 **샘플 데이터만** 들어 있습니다. API 키를 브라우저 코드에 저장하지 않습니다.

## 자동화 원칙

1. 네이버 검색광고 공식 API에서 전일 데이터를 수집합니다.
2. 클릭률(`클릭수 ÷ 노출수`)과 평균 CPC(`광고비 ÷ 클릭수`)를 코드로 계산합니다.
3. 계산된 수치를 바탕으로 리포트 문장을 생성합니다.
4. 매일 오전 8시 30분(Asia/Seoul)에 Slack으로 전송합니다.

스마트플레이스 내부의 플레이스 유입, 리뷰, 유입 키워드 등은 공개 API가 없어 자동 수집 범위에서 제외합니다. 예약·주문·통화·POS 데이터는 각 서비스가 제공하는 공식 API 또는 Webhook이 확인될 때 연결합니다.

## 로컬 실행

추가 설치 없이 `index.html`을 열 수 있습니다. 로컬 서버로 확인하려면 다음 중 하나를 사용하세요.

```powershell
python -m http.server 4173
```

그다음 `http://localhost:4173`으로 접속합니다.

## 실제 데이터 연결에 필요한 값

아래 값은 공개 파일이 아니라 GitHub Actions Secrets 또는 서버 환경변수에 저장해야 합니다.

- `NAVER_CUSTOMER_ID`
- `NAVER_ACCESS_LICENSE`
- `NAVER_SECRET_KEY`
- `SLACK_WEBHOOK_URL`
- `OPENAI_API_KEY` (AI 요약을 사용할 때만)

## 다음 구현 단계

- 네이버 검색광고 API 수집기와 데이터베이스 연결
- 광고 상품/캠페인 이름 매핑 규칙 확정
- Slack Incoming Webhook 연결
- 실제 계정 데이터로 지표 검증
- 예약/POS/콜 트래킹 공급자별 연동 가능성 확인

## 공식 문서

- [네이버 검색광고 API](https://naver.github.io/searchad-apidoc/)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
