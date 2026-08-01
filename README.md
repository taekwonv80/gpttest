# 택이네조개전골 장현점 바다를품다 광고 대시보드

네이버 검색광고 성과를 자동 수집하고, Streamlit·Plotly 대시보드와 Slack 데일리 리포트로 전달하는 서버리스 프로젝트입니다. UI는 stlite를 통해 GitHub Pages에서 실행되고, 비밀키가 필요한 수집 작업은 GitHub Actions에서만 실행됩니다.

## 공개 대시보드

- <https://taekwonv80.github.io/gpttest>
- 캠페인 분류: 플레이스 검색광고, 지역소상공인 광고, 파워링크
- 광고 지표: 광고비, 노출수, 클릭수, 클릭률, 평균 CPC
- 월요일~일요일 기준 최근 5개 주간 선택
- 최근 일자 선택과 전일 대비 일일 분석
- 일별 클릭 추이, 캠페인 비교, Slack 일일 리포트 미리보기

첫 자동 수집이 성공하기 전에는 `data/campaign_weekly.json`의 샘플 데이터가 표시됩니다. 성공 후에는 네이버 SearchAd API 집계 데이터로 자동 교체됩니다.

## 자동화 흐름

1. 매일 오전 8시 30분(KST)에 GitHub Actions가 실행됩니다.
2. 네이버 SearchAd API에서 같은 종류의 캠페인 ID를 묶어 일자별 기간 합계 통계를 수집합니다.
3. 플레이스·지역소상공인·파워링크로 분류하고 월요일~일요일 기준 5개 주간 및 일일 지표를 계산합니다.
4. 집계 데이터만 `data/*.json`에 저장하고 GitHub Pages를 갱신합니다.
5. 전일 핵심 지표를 Slack Incoming Webhook으로 전송합니다.

GitHub의 예약 실행은 지연될 수 있으므로 발송 시각은 08:30 이후 몇 분 정도 차이 날 수 있습니다.

## 필요한 GitHub Actions Secrets

저장소의 `Settings → Secrets and variables → Actions`에 다음 Repository secrets를 등록합니다.

- `NAVER_CUSTOMER_ID`
- `NAVER_ACCESS_LICENSE`
- `NAVER_SECRET_KEY`
- `SLACK_WEBHOOK_URL`

비밀값은 코드, JSON, 로그, 이슈에 저장하지 않습니다. 공개 저장소에는 광고 성과 집계 수치와 연결 성공 상태만 기록됩니다.

## 수동 연결 테스트

1. GitHub 저장소의 `Actions` 탭을 엽니다.
2. `Naver daily marketing report`를 선택합니다.
3. `Run workflow`를 실행합니다.
4. 실행이 성공하면 Slack 메시지가 도착하고 `data/connections.json`이 `연결됨`으로 갱신됩니다.

`report_date`를 비워두면 한국시간 기준 전일을 조회합니다. 과거 날짜를 테스트하려면 `YYYY-MM-DD` 형식으로 입력합니다.

## 로컬 검증

```powershell
python -m unittest discover -s tests -v
python -m http.server 4173
```

그다음 <http://127.0.0.1:4173>으로 접속합니다. `file://`로는 stlite와 데이터 파일을 불러올 수 없습니다.

## 지원 범위

네이버 SearchAd API로 제공되는 광고 통계만 자동 수집합니다. 플레이스 유입, 예약·주문, 스마트콜, 리뷰, 유입채널·키워드 같은 플레이스 사업자 통계는 동일 API에서 제공되지 않으므로 현재 자동화 대상에 포함되지 않습니다.

## 공식 문서

- [네이버 SearchAd API](https://naver.github.io/searchad-apidoc/)
- [Slack Incoming Webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks)
- [GitHub Actions 예약 실행](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#schedule)
