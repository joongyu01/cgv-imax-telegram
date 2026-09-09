# cgv-imax-telegram

CGV **용산아이파크몰 IMAX관**의 **평일 20시 이후** 회차를 지켜보다가,
**예매가 새로 열리거나 취소표가 풀리면** 텔레그램으로 알려주는 봇.

CGV 신규 사이트(`cgv.co.kr`)의 공개 API를 주기적으로 조회해서, 직전 실행 때 없던 상영 회차가
생기면 알림을 보낸다. 서버 없이 **GitHub Actions 크론만으로** 돌아가고, 파이썬 표준 라이브러리
외에 설치할 게 없다.

```
준규의 용아맥 오디세이 연애💑프로젝트

🎟 예매 오픈 — 오디세이 · 용산아이파크몰

📅 2026년 9월 22일(화) 22:00 시작
     ~25:02 종료 · IMAX관 · IMAX LASER 2D · 잔여 624/624석

(조건 밖 회차 37개는 생략)

CGV 예매하기
```

```
준규의 용아맥 오디세이 연애💑프로젝트

🎫 취소표 — 오디세이 · 용산아이파크몰

📅 2026년 9월 12일(금) 21:30 시작
     ~24:32 종료 · IMAX관 · IMAX LASER 2D · 잔여 2/624석
     🎫 2석이 한 번에 풀렸습니다 → 현재 2석 남음

CGV 예매하기
```

첫 줄 문구는 `config.json` 의 `message_header` 로 바꿀 수 있고, 모든 메시지 맨 앞에 붙는다.
CGV는 자정 넘는 시각을 `25:02` 처럼 24를 넘겨 표기한다.

두 알림 모두 **연달아 10번** 보낸다(0.5초 간격 5회 + 1초 간격 5회). 자다가도 깨라고.

## 1. 텔레그램 봇 만들기

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 에게 `/newbot` → 이름 정하면 **토큰**을 준다.
2. 만든 봇과 대화방을 열고 아무 메시지나 한 번 보낸다. (봇은 먼저 말을 걸 수 없다)
3. 아래 주소를 브라우저에서 열어 `chat.id` 를 확인한다. 그게 **채팅 ID**다.

   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```

## 2. GitHub Actions 로 돌리기 (추천 · 무료)

1. 이 저장소를 본인 계정으로 fork 하거나 그대로 push 한다.
2. **Settings → Secrets and variables → Actions → New repository secret** 에 두 개 등록:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. **Actions** 탭에서 워크플로를 활성화한다.
4. `CGV 예매 오픈 감시` → **Run workflow** 로 한 번 수동 실행해서 정상 동작을 확인한다.

크론은 5분마다 돌지만, **잡 하나가 4분 동안 살아 있으면서 약 30초 간격으로** 확인한다.
확인한 회차 목록은 `state.json` 에 커밋되어 다음 실행과 비교된다.

> 첫 실행에서는 이미 열려 있는 회차를 전부 "신규"로 오해해 도배하지 않도록 알림을 보내지 않고
> 기준선만 저장한다. **두 번째 실행부터** 알림이 온다.

> GitHub 크론의 **최소 간격은 5분**이고, 그보다 짧게 적어도 무시된다. 게다가 러너가 붐비면
> 몇 분씩 밀린다. 그래서 이 워크플로는 잡 안에서 루프를 돌려 감지 주기를 30초까지 낮췄다.
> 밀린 실행은 취소하지 않고 줄을 세우므로(`cancel-in-progress: false`), 지연이 생겨도
> 대기 중이던 잡이 이어 돌면서 빈 시간을 메운다.

## 3. 내 서버 / 라즈베리파이에서 상주 실행

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python cgv_watch.py --loop --interval 30
```

도커:

```bash
docker build -t cgv-imax-telegram .
docker run -d --restart=always \
  -e TELEGRAM_BOT_TOKEN=... -e TELEGRAM_CHAT_ID=... \
  -v "$PWD/state.json:/app/state.json" \
  cgv-imax-telegram
```

## 4. 봇에게 물어보기

봇 채팅창에 명령을 치면 답한다. `/` 를 누르면 메뉴가 뜬다.

| 명령 | 하는 일 |
| --- | --- |
| `/status` | CGV API가 지금 살아 있는지 실제로 찔러 보고, 마지막 조회 시각·연속 실패·감시 조건을 보여준다 |
| `/list` | 지금 조건에 맞는 회차 전체 |
| `/help` | 명령 목록 |

```
✅ CGV API — 정상 응답 (312ms)

감시 조건 · 월화수목금 · 20:00~23:59 · IMAX

용산 IMAX 오디세이
  감시 중인 회차 4개 / 상영일 7일
  마지막 전체 조회 2분 14초 전
  마지막 좌석 확인 0분 31초 전
  마지막 정상 조회 09/12 21:04:33
```

명령은 **등록된 `TELEGRAM_CHAT_ID` 에서 온 것만** 처리한다. 봇 주소를 아는 다른 사람이
말을 걸어도 무시한다.

명령 메뉴 등록은 `--ping` 한 번이면 된다:

```bash
python cgv_watch.py --ping
```

## 5. 취소표는 어떻게 잡나

CGV 공개 API로는 **좌석배치도를 볼 수 없다**(로그인 뒤 예매 흐름 안에만 있다). 그래서
"붙어 있는 2연석"인지는 알 방법이 없다.

대신 회차 정보에 들어 있는 **잔여 좌석 수(`frSeatCnt`)** 를 계속 지켜보다가, 직전에 본
값보다 **한 번에 `cancel_min_seats`(기본 2)석 이상 늘어난 순간**을 취소표로 본다.
2인이 같이 취소하면 연석이 통째로 풀리므로, 이 "동시 증가폭"이 실제로 원하는 신호에
가장 가깝다. 1석씩 따로 빠지는 건 걸러진다.

좌석 확인은 `seat_watch_seconds`(기본 60초)마다, **조건에 맞는 회차가 있는 날짜만** 본다.

## 6. 요청량과 장애 감지

### CGV 서버에 요청을 얼마나 보내나

CGV API에는 공개된 호출 한도가 없다(비공식 엔드포인트라 공지 자체가 없다). 응답에
rate-limit 헤더도 없다. 하지만 앞단이 Cloudflare라 과하게 때리면 차단될 수 있으므로,
요청 수를 두 가지 방법으로 줄였다.

- **상영일 목록만 매 주기 확인한다.** `searchSiteScnscYmdListByMov` 한 번이면 그 영화의
  상영일이 통째로 나온다. 예매가 새로 열리면 여기에 날짜가 늘어난다. 그래서 평소 한 주기는
  **요청 1건**이고, 새 날짜가 보일 때만 그 날짜의 회차를 가져온다.
- **1분마다 감시 대상 날짜만 본다**(`seat_watch_seconds`). 취소표 감지용이자, 그 날짜에
  회차가 추가되는 것도 같이 잡는다. 지금 조건이면 4건.
- **5분마다 한 번은 전체를 훑는다**(`full_sweep_seconds`). 아직 감시 대상이 없는 날짜에
  회차가 생기는 경우를 놓치지 않기 위한 보정이다. `상영일 수 + 1` 건.

실측 요청 수는 평소 주기 **1건**, 좌석 확인 주기 **5건**, 전체 스윕 **8건**이다.
30초 주기로 하루 종일 돌려도 약 1만 건 남짓으로, 날짜별 회차를 매번 전부 가져오는
방식(2만 건 이상)의 절반 이하다.

또 요청이 한꺼번에 몰리지 않도록 **호출 사이에 0.4~1.6초를 무작위로 쉬고**(`request_gap`),
폴링 주기도 `--jitter` 만큼 흔들어 매번 같은 초에 때리지 않게 했다. 정확히 30초마다 같은
패턴으로 두드리는 것보다 낫다는 정도이지, 차단을 뚫는 장치는 아니다. 진짜 방어책은 위의
요청 수 절감이다.

### 조회가 막히면 알려준다

봇이 조용히 죽어 있는 걸 모르고 지나가는 게 제일 나쁘다. 그래서 CGV 조회가 **연속
3회**(`fail_alert_after`) 실패하면 텔레그램으로 한 번 알린다.

```
⚠️ 조회 실패 — 용산 IMAX 오디세이

연속 3회 실패했습니다. CGV 점검이거나 요청이 차단됐을 수 있습니다.
TimeoutError: The read operation timed out

복구되면 다시 알려드립니다.
```

도배를 막기 위해 실패 알림은 **한 번만** 보내고, 정상으로 돌아오면 복구 알림을 보낸 뒤
다시 감시 상태로 돌아간다.

## 7. 설정 바꾸기 — `config.json`

```json
{
  "message_header": "준규의 용아맥 오디세이 연애💑프로젝트",
  "targets": [
    {
      "name": "용산 IMAX 오디세이",
      "site_no": "0013",
      "site_name": "용산아이파크몰",
      "mov_no": "30001323",
      "movie_name": "오디세이"
    }
  ],
  "filters": {
    "hall_keywords": ["IMAX"],
    "weekdays": [0, 1, 2, 3, 4],
    "start_time_from": "2000",
    "start_time_to": "2359",
    "full_sweep_seconds": 300,
    "seat_watch_seconds": 60,
    "cancel_min_seats": 2,
    "alert_burst": [[5, 0.5], [5, 1.0]],
    "fail_alert_after": 3,
    "request_gap": [0.4, 1.6]
  }
}
```

| 항목 | 설명 |
| --- | --- |
| `message_header` | 모든 메시지 첫 줄에 붙는 문구. 비우면 안 붙는다 |
| `site_no` | 극장 번호. 용산아이파크몰 = `0013` |
| `mov_no` | 영화 번호. 오디세이 = `30001323`. **비워두면** `movie_name` 으로 자동 검색 |
| `hall_keywords` | 상영관 이름 / 상영 형태에 이 단어가 들어간 회차만. `["IMAX"]` 는 `IMAX관`·`IMAX LASER 2D` 를 잡는다 |
| `weekdays` | 월=0 … 일=6. `[0,1,2,3,4]` 가 평일 |
| `start_time_from` / `_to` | 상영 시작 시각 범위 (`HHMM`) |
| `full_sweep_seconds` | 전체 날짜를 다시 훑는 주기(초) |
| `fail_alert_after` | 연속 몇 회 실패하면 장애 알림을 보낼지 |
| `request_gap` | 요청 사이 무작위 대기 범위(초) |
| `seat_watch_seconds` | 취소표 확인 주기(초) |
| `cancel_min_seats` | 잔여석이 한 번에 몇 석 늘면 취소표로 볼지 |
| `alert_burst` | 알림 반복 방식. `[[횟수, 간격초], ...]` |

CGV는 자정 넘는 심야 회차를 **`2530` = 새벽 1시 30분** 처럼 24를 넘겨 표기한다.
기본 설정은 `2359` 까지라 심야 회차가 빠지는데, 심야도 받고 싶으면 `start_time_to` 를
`"2959"` 로 바꾸면 된다.

번호를 모를 때는 직접 찾을 수 있다:

```bash
python cgv_watch.py --find-site 용산      # 0013  용산아이파크몰
python cgv_watch.py --find-movie 오디세이  # 30001323  오디세이
```

여러 영화·극장을 동시에 감시하려면 `targets` 배열에 항목을 더 넣으면 된다.

## 8. 그 밖의 명령

```bash
python cgv_watch.py --report   # 알림 없이 지금 조건에 맞는 회차만 출력
python cgv_watch.py --ping     # 텔레그램 연결 테스트
```

`--loop` 옵션:

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--interval` | `300` | 폴링 주기(초) |
| `--jitter` | `0.4` | 주기를 이 비율만큼 흔든다. `0.4`면 주기의 60~140% |
| `--duration` | `0` | 이 시간(초)이 지나면 종료. `0`이면 무한 |

## 사용한 CGV API

전부 인증 없이 열려 있는 공개 엔드포인트다. 회사코드 `coCd` 는 CGV가 `A420`.

| 용도 | 엔드포인트 |
| --- | --- |
| 지역/극장 목록 | `GET /api/v1/content/site/searchAllRegionAndSite` |
| 예매 중인 영화 목록 | `GET /api/v1/booking/searchAtktTopPostrList` |
| 특정 영화의 극장별 상영일 | `GET /api/v1/booking/searchSiteScnscYmdListByMov?siteNo=&movNo=` |
| 특정 날짜의 회차 목록 | `GET /api/v1/booking/searchSchByMov?siteNo=&movNo=&scnYmd=&rtctlScopCd=1` |

좌석배치도 API는 이 목록에 없다. 예매 흐름 안(로그인 필요)에만 있어 공개 조회가 안 된다.

폴링 주기를 무리하게 줄이지 말 것.

## 참고

접근 방식은 [0w0i0n0g0/cgv-open-push](https://github.com/0w0i0n0g0/cgv-open-push) (디스코드,
AGPL-3.0) 에서 아이디어를 얻었다(그쪽은 5분 주기). 다만 그쪽이 쓰던 구 `ticket.cgv.co.kr`
POST API는 현재 CloudFront가 POST를 막아 동작하지 않아, 이 저장소는 신규 사이트 API 기준으로
새로 작성했다. 코드를 가져다 쓰지 않았다.

## 라이선스

MIT
