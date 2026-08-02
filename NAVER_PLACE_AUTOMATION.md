# 네이버 스마트플레이스 통계 자동 수집

GitHub Actions가 매일 오전 9시 10분(KST)에 스마트플레이스 통계 화면을 열어 누적 수치를 저장합니다. PC가 꺼져 있어도 실행됩니다.

## 최초 1회 로그인 등록

PC에 Python과 GitHub CLI(`gh`)가 설치되고 현재 저장소에 로그인되어 있어야 합니다.

```powershell
pip install "playwright>=1.54,<2"
python -m playwright install chromium
gh auth login
python scripts/setup_naver_place_session.py
```

열린 브라우저에서 네이버 로그인 → 대상 업체 → **통계** 화면으로 이동한 후 터미널 안내에 맞춰 다음 5개 탭을 차례로 엽니다.

1. 리포트
2. 플레이스
3. 스마트콜
4. 예약주문
5. 리뷰

각 탭을 연 뒤 터미널에서 Enter를 누르면 해당 주소가 등록됩니다.

탭 주소에 포함된 조회 날짜는 저장된 값을 그대로 사용하지 않습니다. Actions 실행 시마다 서울 날짜를 기준으로 이번 주 월요일부터 실행일까지 자동 갱신합니다.

다음 Repository Secret이 자동 등록됩니다.

- `NAVER_PLACE_STORAGE_STATE_B64`: 로그인 쿠키가 포함된 브라우저 세션
- `NAVER_PLACE_REPORT_URL`: 전체 핵심 지표 리포트 화면 주소
- `NAVER_PLACE_STATS_URL`: 플레이스 유입·채널·키워드 화면 주소
- `NAVER_PLACE_SMARTCALL_STATS_URL`: 스마트콜 통계 화면 주소
- `NAVER_PLACE_RESERVATION_STATS_URL`: 예약주문 유입·신청·취소·유입채널 화면 주소
- `NAVER_PLACE_REVIEW_STATS_URL`: 리뷰 통계 화면 주소

비밀번호는 저장하지 않습니다. 세션 데이터에는 로그인 쿠키가 포함되며 base64는 암호화가 아니라 전송용 인코딩입니다. 인코딩된 값은 GitHub Actions의 암호화된 Secret으로만 보관되고 로컬 임시 파일은 등록 직후 삭제됩니다. 이 세션은 계정 접근 권한을 가지므로 저장소 관리자 외에는 Secrets 접근 권한을 주지 마세요.

## 실행과 결과

GitHub 저장소의 **Actions → Naver SmartPlace daily statistics → Run workflow**에서 최초 실행을 시험합니다.

- `data/naver_place_daily.csv`: 5개 통계 탭에서 수집한 날짜별 누적 수치 및 전일 대비 증가분. 플레이스 유입·예약/주문 신청·스마트콜·리뷰, 유입채널·유입키워드, 예약 유입·신청·취소·완료·유입채널이 누적됩니다.
- `data/naver_place_latest.json`: 마지막 수집 결과

로그인 만료나 화면 변경으로 실패하면 실행 페이지의 `naver-place-diagnostic` 파일에서 3일 동안 진단 캡처를 받을 수 있습니다. 로그인 세션이 만료되면 위 설정 스크립트를 다시 한 번 실행합니다.

## 연동 방식과 제한

네이버 공식 도움말은 이 통계를 스마트플레이스 PC 화면에서 확인하도록 안내하지만 공개 통계 API 연동 방법은 제공하지 않습니다. 따라서 이 자동화는 공식 API가 아니라 본인 계정의 로그인 세션으로 화면에 표시된 텍스트를 하루 한 번 읽는 방식입니다. 화면 구조가 바뀌거나 보안 확인이 발생하면 수집이 멈출 수 있으며, 이때 진단 캡처를 확인하고 세션 또는 수집 규칙을 갱신해야 합니다.

## 비용 제한

이 작업은 보통 하루 몇 분만 사용하므로 GitHub Free의 월간 Actions 한도 안에서 실행됩니다. GitHub **Settings → Billing and licensing → Budgets and alerts**에서 Actions 예산을 0달러로 두고 한도 도달 시 중지하도록 설정하면 초과 과금을 차단할 수 있습니다.
