# cgv-imax-telegram

CGV **용산아이파크몰 IMAX관**의 **평일 20시 이후** 회차가 새로 열리면 텔레그램으로 알려주는 봇.

CGV 신규 사이트(`cgv.co.kr`)의 공개 API를 주기적으로 조회해서, 직전 실행 때 없던 상영 회차가
생기면 알림을 보낸다. 서버 없이 **GitHub Actions 크론만으로** 돌아가고, 파이썬 표준 라이브러리
외에 설치할 게 없다.

```
🎟 예매 오픈 — 오디세이 · 용산아이파크몰

• 09/22(화) 22:00~25:02 IMAX관 [IMAX LASER 2D] · 잔여 624/624석
• 09/23(수) 21:30~24:32 IMAX관 [IMAX LASER 2D] · 잔여 624/624석

(조건 밖 회차 37개는 생략)

CGV 예매하기
```

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

이후 5분마다 자동으로 돌고, 확인한 회차 목록은 `state.json` 에 커밋되어 다음 실행과 비교된다.

> 첫 실행에서는 이미 열려 있는 회차를 전부 "신규"로 오해해 도배하지 않도록 알림을 보내지 않고
> 기준선만 저장한다. **두 번째 실행부터** 알림이 온다.

> GitHub의 크론은 정확히 5분마다가 아니라 러너가 붐비면 **몇 분에서 십수 분까지 밀릴 수 있다.**
> 티켓 오픈 순간을 초 단위로 잡아야 한다면 아래 상주 실행을 쓰는 게 낫다.

## 3. 내 서버 / 라즈베리파이에서 상주 실행

```bash
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python cgv_watch.py --loop --interval 60
```

도커:

```bash
docker build -t cgv-imax-telegram .
docker run -d --restart=always \
  -e TELEGRAM_BOT_TOKEN=... -e TELEGRAM_CHAT_ID=... \
  -v "$PWD/state.json:/app/state.json" \
  cgv-imax-telegram
```

## 4. 설정 바꾸기 — `config.json`

```json
{
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
    "start_time_to": "2359"
  }
}
```

| 항목 | 설명 |
| --- | --- |
| `site_no` | 극장 번호. 용산아이파크몰 = `0013` |
| `mov_no` | 영화 번호. 오디세이 = `30001323`. **비워두면** `movie_name` 으로 자동 검색 |
| `hall_keywords` | 상영관 이름 / 상영 형태에 이 단어가 들어간 회차만. `["IMAX"]` 는 `IMAX관`·`IMAX LASER 2D` 를 잡는다 |
| `weekdays` | 월=0 … 일=6. `[0,1,2,3,4]` 가 평일 |
| `start_time_from` / `_to` | 상영 시작 시각 범위 (`HHMM`) |

CGV는 자정 넘는 심야 회차를 **`2530` = 새벽 1시 30분** 처럼 24를 넘겨 표기한다.
기본 설정은 `2359` 까지라 심야 회차가 빠지는데, 심야도 받고 싶으면 `start_time_to` 를
`"2959"` 로 바꾸면 된다.

번호를 모를 때는 직접 찾을 수 있다:

```bash
python cgv_watch.py --find-site 용산      # 0013  용산아이파크몰
python cgv_watch.py --find-movie 오디세이  # 30001323  오디세이
```

여러 영화·극장을 동시에 감시하려면 `targets` 배열에 항목을 더 넣으면 된다.

## 5. 그 밖의 명령

```bash
python cgv_watch.py --report   # 알림 없이 지금 조건에 맞는 회차만 출력
python cgv_watch.py --ping     # 텔레그램 연결 테스트
```

## 사용한 CGV API

전부 인증 없이 열려 있는 공개 엔드포인트다. 회사코드 `coCd` 는 CGV가 `A420`.

| 용도 | 엔드포인트 |
| --- | --- |
| 지역/극장 목록 | `GET /api/v1/content/site/searchAllRegionAndSite` |
| 예매 중인 영화 목록 | `GET /api/v1/booking/searchAtktTopPostrList` |
| 특정 영화의 극장별 상영일 | `GET /api/v1/booking/searchSiteScnscYmdListByMov?siteNo=&movNo=` |
| 특정 날짜의 회차 목록 | `GET /api/v1/booking/searchSchByMov?siteNo=&movNo=&scnYmd=&rtctlScopCd=1` |

호출은 한 번 검사할 때 `상영일 수 + 1` 회 정도(보통 10회 미만)라 부담이 크지 않다.
폴링 주기를 무리하게 줄이지 말 것.

## 참고

접근 방식은 [0w0i0n0g0/cgv-open-push](https://github.com/0w0i0n0g0/cgv-open-push) (디스코드,
AGPL-3.0) 에서 아이디어를 얻었다. 다만 그쪽이 쓰던 구 `ticket.cgv.co.kr` POST API는 현재
CloudFront가 POST를 막아 동작하지 않아, 이 저장소는 신규 사이트 API 기준으로 새로 작성했다.
코드를 가져다 쓰지 않았다.

## 라이선스

MIT
