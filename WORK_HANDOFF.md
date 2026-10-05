# 작업 인계 문서

최종 갱신: 2026-10-05 (KST)

## 커밋 기준 상태

| 구분 | 커밋 / 상태 | 내용 |
| --- | --- | --- |
| 원격 최신본 | `4a754d7` (`master`, `origin/master`) | 대기 표기 문구와 짧은 `-` 표시까지 배포된 상태 |
| 실측 데이터 | `eea145d`, `dcef5f3` | `data/rank_history.json`에 네이버 플레이스 순위/검색량 측정 결과 누적 |
| 순위 자동화 최초 추가 | `728276f` | GitHub Actions, 순위 수집기, 설정/이력 파일, 기본 테스트 추가 |
| 정적 대시보드 최초 추가 | `6c501ea` | `index.html`, `tracker.js`, `tracker.css` 추가 |
| 현재 로컬 미커밋 작업 | 커밋 필요 | 키워드 파일 동기화 Worker, 화면 동기화 로직, 키워드 4개 설정 반영 |

다른 컴퓨터에서 시작할 때는 먼저 `4a754d7` 이상인지 확인한다.

```powershell
git log -1 --oneline
git status --short
```

현재 로컬 미커밋 변경을 커밋할 때 권장 메시지:

```powershell
git add .github/workflows/naver-place-rank.yml README.md data/tracker_config.json data/keyword_sync.json index.html tracker.js worker WORK_HANDOFF.md
git commit -m "feat: sync tracked keywords to config"
```

## 프로젝트와 배포

- 로컬 경로: `D:\ClamProject.v2\gpttest`
- GitHub 저장소: `taekwonv80/gpttest`
- 공개 사이트: `https://taekwonv80.github.io/gpttest`
- 배포: 프로젝트 루트에서 `deploy.bat` 실행
- 정적 화면: `index.html`, `tracker.js`, `tracker.css`, `dashboard.css`, `pending.css`
- 작업 권장 모델: `GPT-5.6 Terra` / 추론 수준 `Medium` (`AGENTS.md`에도 기록됨). 실제 선택은 Codex 앱 설정이 우선한다.

## 현재 구현 상태

### 네이버 플레이스 순위 측정

- 대상 플레이스: `https://map.naver.com/p/entry/place/1827896507`
- 설정 파일: `data/tracker_config.json`
- 측정 결과 파일: `data/rank_history.json`
- GitHub Actions: `.github/workflows/naver-place-rank.yml`
- 매일 오전 09:15 KST에 실행하며, 수동 실행도 가능하다.
- `repository_dispatch`의 `tracker-config-updated` 이벤트도 순위 측정을 실행한다.
- 최근 실측 기록: `장현동맛집` 5위, 2026-10-05 17:18:32+09:00, 월 검색량 1,320회 (PC 130 / 모바일 1,190).

### 검색량

- `scripts/naver_place_rank_collector.py`가 네이버 SearchAd Keyword Tool API로 월간 PC/모바일 검색량을 조회한다.
- GitHub Actions Secrets 필요:
  - `NAVER_CUSTOMER_ID`
  - `NAVER_ACCESS_LICENSE`
  - `NAVER_SECRET_KEY`
- API 키가 없거나 호출에 실패하면 순위 수집은 계속 진행하고 화면에는 `검색량(측정대기)`를 표시한다.
- 직접 실행 시 발생하던 `ModuleNotFoundError: No module named 'scripts'`는 수정했다.

### 키워드 파일 동기화

문제: GitHub Pages는 정적 사이트여서 화면 JavaScript만으로 GitHub 파일을 쓸 수 없다. 기존 화면의 키워드 등록은 브라우저 `localStorage`에만 저장되어 GitHub Actions 측정 대상과 달랐다.

해결 구조:

```text
화면 등록/삭제
  → Cloudflare Worker
  → GitHub data/tracker_config.json 커밋
  → repository_dispatch (tracker-config-updated)
  → GitHub Actions 순위 측정
  → data/rank_history.json 갱신
```

추가한 파일:

- `worker/src/index.mjs`: 키워드 목록 API (`GET/POST /keywords`), GitHub 설정 파일 저장, 측정 이벤트 요청
- `worker/wrangler.toml`: Worker 이름·허용 origin·저장소 설정
- `data/keyword_sync.json`: 배포된 Worker 주소를 넣는 공개 설정 파일

화면 동작:

- `tracker.js`는 `data/tracker_config.json`을 키워드 기준 목록으로 사용한다.
- Worker 주소가 설정된 뒤 등록·삭제하면 `동기화키`를 최초 1회 입력한다.
- 동기화키는 `sessionStorage`에만 보관하므로 탭/브라우저를 닫으면 제거된다.
- Worker가 성공 응답을 줄 때만 화면 목록을 갱신한다. 브라우저에만 저장하는 방식은 제거했다.

## Cloudflare Worker 연결 (아직 필요)

Worker 코드만 추가되어 있으며 실제 Cloudflare 배포 및 Secret 등록은 아직 하지 않았다.

1. Cloudflare 계정으로 로그인한 터미널에서 실행한다.

   ```powershell
   cd D:\ClamProject.v2\gpttest\worker
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler secret put ADMIN_KEY
   npx wrangler deploy
   ```

2. `GITHUB_TOKEN`은 `taekwonv80/gpttest` 저장소에만 적용되는 GitHub fine-grained PAT를 만든다.
   - Repository permissions: `Contents: Read and write`
   - 토큰/비밀값을 저장소 파일, GitHub Actions 로그, 채팅, README에 넣지 않는다.

3. `ADMIN_KEY`는 화면 등록·삭제용 별도 강한 임의 문자열이다. GitHub 토큰과 다른 값으로 만든다.

4. `npx wrangler deploy` 출력의 Worker URL을 아래처럼 `data/keyword_sync.json`에 입력한다.

   ```json
   {
     "endpoint": "https://<worker-name>.<account-subdomain>.workers.dev"
   }
   ```

5. 프로젝트 루트에서 `deploy.bat`을 실행한다.

6. 공개 사이트에서 키워드를 하나 등록해 확인한다.
   - Worker가 `data/tracker_config.json`을 커밋해야 한다.
   - GitHub Actions의 `Naver Place keyword rank`가 시작되어야 한다.
   - 측정 완료 후 `data/rank_history.json`에 해당 키워드가 추가되어야 한다.

## 현재 자동 측정 키워드

`data/tracker_config.json`에 아래 5개가 반영돼 있다.

1. 장현동맛집
2. 시흥능곡샤브샤브
3. 장곡동샤브샤브
4. 능곡동칼국수
5. 장곡동점심맛집

## 화면 표시 원칙

- 실제 `rank_history.json`에 있는 값만 순위 및 검색량으로 표시한다.
- 검색량이 없으면 `검색량(측정대기)`로 표시한다.
- 순위가 없으면 `순위(측정대기)`로 표시한다.
- 순위 이력이 부족하면 `순위추이(측정대기)`로 표시한다.
- 시즌 정보는 `시즌일정(설정대기)`로 표시한다.
- 빈 수치는 긴 대시가 아닌 짧은 `-` 하나로 표시한다.

## 주요 변경 파일

- `index.html`: 순위 대시보드 UI, 키워드 동기화 상태 문구
- `tracker.js`: 실제 결과 로딩, 대기 표기, Worker 동기화 등록/삭제
- `data/tracker_config.json`: 자동 측정 키워드 목록
- `data/rank_history.json`: 순위/검색량 실측 이력
- `scripts/naver_place_rank_collector.py`: 네이버 지도 순위 + SearchAd 검색량 수집
- `.github/workflows/naver-place-rank.yml`: 예약/수동/키워드 변경 이벤트 측정
- `worker/src/index.mjs`: Cloudflare Worker API
- `worker/wrangler.toml`: Cloudflare Worker 배포 설정
- `data/keyword_sync.json`: Worker endpoint 설정 (현재 빈 값)

## 검증 완료

다음 검증은 통과했다.

```powershell
node --check tracker.js
node --check worker\src\index.mjs
python -m unittest discover -s tests -p test_naver_place_rank_collector.py -v
git diff --check
```

순위 수집 테스트 3개가 통과했다.

## 주의 사항

- GitHub Pages만으로는 버튼 클릭이 GitHub 파일을 수정할 수 없다. Worker의 GitHub API 쓰기 권한이 필요하다.
- `GITHUB_TOKEN`, `ADMIN_KEY`, Naver API Secret, Slack Webhook은 절대 커밋하지 않는다.
- Worker를 배포하기 전에는 화면 등록/삭제가 파일을 변경하지 않고, `자동동기화 서버가 아직 연결되지 않았습니다.`라고 표시되는 것이 정상이다.
- 현재 변경분은 아직 `deploy.bat`으로 원격 저장소에 반영하지 않은 상태일 수 있으므로, 다른 컴퓨터에서 작업 전 `git status`와 `git pull` 상태를 먼저 확인한다.
