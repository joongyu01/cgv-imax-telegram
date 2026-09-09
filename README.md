# cgv-imax-telegram

CGV **용산아이파크몰 IMAX관**의 **평일 19시 이후** 회차를 지켜보다가,
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

예매 오픈은 놓치면 끝이라 **연달아 10번** 보낸다(0.5초 간격 5회 + 1초 간격 5회).
취소표는 수시로 생겼다 사라지므로 **한 번만** 보낸다.

## 1. 텔레그램 봇 만들기

1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 에게 `/newbot` → 이름 정하면 **토큰**을 준다.
2. 만든 봇과 대화방을 열고 아무 메시지나 한 번 보낸다. (봇은 먼저 말을 걸 수 없다)
3. 아래 주소를 브라우저에서 열어 `chat.id` 를 확인한다. 그게 **채팅 ID**다.

   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```

## 2. 로컬 상주 실행 (지금 이 방식)

`run_local.bat.example` 을 `run_local.bat` 으로 복사하고 토큰과 채팅 ID 를 채운 뒤
**더블클릭**하면 끝이다. 창이 하나 뜨고 거기서 돈다. 창을 닫으면 봇도 멈춘다.
이미 돌고 있는 인스턴스가 있으면 배치 파일이 먼저 정리하므로, 여러 번 눌러도
두 개가 겹쳐 돌지 않는다.

> `.bat` 은 반드시 **cp949(ANSI)** 로 저장해야 한다. UTF-8 로 저장하면 한국어
> Windows 의 cmd 가 한글 줄을 깨뜨려 실행이 안 된다.

> 봇을 두 개 띄우면 텔레그램이 `409 Conflict` 를 내며 서로 명령을 뺏어간다.
> 배치 파일이 이걸 막아 준다.

창 없이 백그라운드로 띄우고 로그를 남기려면 PowerShell 에서:

```powershell
Start-Process python -ArgumentList 'cgv_watch.py','--loop','--interval','30','--jitter','0.4' -WorkingDirectory $PWD -WindowStyle Hidden -RedirectStandardOutput cgv-watch.log -RedirectStandardError cgv-watch.err
```

멈추려면:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*cgv_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

로그인할 때 자동으로 뜨게 하려면 `Win+R` → `shell:startup` 폴더에 `run_local.bat`
바로가기를 넣으면 된다.

**PC가 꺼져 있으면 감시도 멈춘다.** 그동안 열린 회차는 다음 실행 때 "신규"로
잡혀 알림이 오므로 놓치지는 않지만, 그만큼 늦는다.

## 3. GitHub Actions 로 돌리기 (지금은 꺼져 있음)

`.github/workflows/watch.yml` 의 `schedule` 이 주석 처리되어 **자동 실행은 꺼져 있다.**
Actions 탭에서 수동으로 `Run workflow` 를 눌렀을 때만 돈다. 되살리려면 주석을 풀면 된다.

크론으로 돌릴 때의 한계는 아래에 적어 둔다.

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

## 4. 도커로 돌리기

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
| `/status` | CGV API가 지금 살아 있는지 실제로 찔러 보고, 마지막 조회 시각·연속 실패를 보여준다 |
| `/list` | 지금 조건에 맞는 회차 전체 |
| `/settings` | 현재 설정 보기 |
| `/late_off` `/late_on` | 22시 이후 회차 추적 끄기/켜기 |
| `/repeat_3` | 취소표 알림을 3번 보냄 (1~20) |
| `/window_1900_2359` | 조회 시간대 변경 |
| `/set` | 나머지 값 전부 (목록은 `/set` 만 보내면 나온다) |
| `/reset` | 바꾼 설정 되돌리기. `/reset_seat` 처럼 하나만도 가능 |
| `/help` | 명령 목록 |

`/set` 으로 바꿀 수 있는 값:

| 항목 | 뜻 | 예 |
| --- | --- | --- |
| `interval` | 폴링 주기(초) | `/set_interval_60` |
| `seat` | 좌석 확인 주기(초) | `/set_seat_120` |
| `full` | 전체 스윕 주기(초) | `/set_full_300` |
| `minseats` | 취소표 판단 기준(석) | `/set_minseats_2` |
| `from` `until` | 조회 시작·종료 시각 | `/set_until_2159` |
| `weekdays` | 감시 요일 (월=0) | `/set_weekdays_0,1,2,3,4` |
| `halls` | 상영관 키워드 | `/set_halls_IMAX` |
| `repeat` `openrepeat` | 취소표·예매 오픈 알림 횟수 | `/set_openrepeat_10` |
| `quiet` `quietinterval` | 저속 시간대와 그 주기 | `/set_quiet_0_6` |
| `dates` | 상영일 목록 조회 주기(초) | `/set_dates_30` |
| `failafter` | 장애 알림 기준(연속 실패) | `/set_failafter_3` |
| `gap` | 요청 간 대기(초) | `/set_gap_0.4_1.6` |

값은 **언더바로 이어 붙인다.** 텔레그램은 메뉴에서 명령을 누르면 곧바로 전송해 버려서
인자를 덧붙일 틈이 없기 때문이다. `/set interval 60` 처럼 띄어 써도 동작한다.
`/set_interval` 처럼 값을 빼면 지금 값을 알려준다.

명령은 **1초 안에** 답이 온다. 조회 주기가 끝나기를 기다리지 않고, 대기 시간을
텔레그램 롱폴링(`getUpdates` 의 `timeout`)으로 채워 메시지가 오는 즉시 깨어난다.

봇으로 바꾼 값은 `state.json` 에 저장되어 **다시 켜도 유지된다.** `config.json` 은
건드리지 않으므로 `/reset` 하면 원래 값으로 돌아간다.

```
✅ CGV API — 정상 응답 (312ms)

감시 조건 · 월화수목금 · 19:00~23:59 · IMAX

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

- **감시 대상 날짜만 본다.** 조건에 맞는 회차가 있는 날짜(지금은 4일)만 잔여석을 확인한다.
  상영일 전체(6~7일)를 매번 훑지 않는다.
- **상영일 목록은 캐싱한다**(`dates_check_seconds`, 기본 30초). 이 목록은 새 날짜가
  열릴 때나 바뀌는데, 주기가 5초면 하루 17,280번을 받게 된다. 30초로 묶어 하루
  2,880번으로 줄였다. 하루 14,400건이 그냥 버려지던 호출이었다.
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

### 데이터를 얼마나 쓰나 (테더링으로 돌릴 때)

HTTP 레벨에서 직접 측정한 값이다.

| 구간 | 요청 수 | 실측 |
| --- | --- | --- |
| 평소 주기 | 1건 | 1.4 KB |
| 좌석 확인 | 5건 | 18.9 KB |
| 전체 스윕 | 8건 | 29.1 KB |
| 텔레그램 확인 | 1건 | 0.7 KB |

`--interval 30` 기준 하루 사용량은 `seat_watch_seconds` 가 좌우한다(TLS·TCP 오버헤드 20% 포함 추정):

| `seat_watch_seconds` | 하루 | 한 달 |
| --- | --- | --- |
| 30 (기본) | 68 MB | 2.0 GB |
| 60 | 41 MB | 1.2 GB |
| 120 | 26 MB | 0.8 GB |
| 180 | 21 MB | 0.6 GB |
| 300 | 17 MB | 0.5 GB |

심야에는 예매 오픈도 취소표도 거의 없으므로 `quiet_hours` 로 00~06시는 5분 주기로
늦춘다. 그만큼 하루 사용량이 더 줄어든다.

`--interval` 을 60초로 늘려도 별 차이가 없다. 평소 주기 요청은 1.4 KB뿐이라 거의 공짜고,
데이터를 쓰는 건 좌석 확인이기 때문이다. **줄이려면 `seat_watch_seconds` 를 올려라.**

두 가지를 손봐서 이 수준이 됐다.

- **gzip** — 날짜별 회차 응답이 40 KB인데 압축하면 2.9 KB다. 14배 차이다.
- **연결 재사용(keep-alive)** — 매 요청 새로 TLS를 맺으면 핸드셰이크에만 10 KB가 든다.
  실제 데이터보다 접속 비용이 더 컸다. 실측으로 요청당 12.7 KB → 5.4 KB로 줄었다.

둘 다 없으면 같은 설정에서 한 달 10 GB를 넘긴다.

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
    "start_time_from": "1900",
    "start_time_to": "2359",
    "full_sweep_seconds": 300,
    "seat_watch_seconds": 60,
    "cancel_min_seats": 2,
    "alert_burst": [[5, 0.5], [5, 1.0]],
    "cancel_alert_burst": [[1, 0]],
    "quiet_hours": [0, 6],
    "quiet_interval": 300,
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
| `dates_check_seconds` | 상영일 목록 조회 주기(초) |
| `poll_interval` | 폴링 주기(초) |
| `cancel_min_seats` | 잔여석이 한 번에 몇 석 늘면 취소표로 볼지 |
| `alert_burst` | 예매 오픈 알림 반복 방식. `[[횟수, 간격초], ...]` |
| `cancel_alert_burst` | 취소표 알림 반복 방식. 기본은 1회 |
| `quiet_hours` | 폴링을 늦출 시간대 `[시작시, 끝시]` (한국시간, 끝시 미포함) |
| `quiet_interval` | 그 시간대의 폴링 주기(초) |

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
