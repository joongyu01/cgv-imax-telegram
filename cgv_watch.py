#!/usr/bin/env python3
"""CGV 예매 오픈 알림 — 용산아이파크몰 IMAX / 평일 20시 이후.

CGV 신규 사이트(cgv.co.kr)의 공개 BFF API를 폴링해서, 이전에 못 보던
상영 회차가 새로 생기면 텔레그램으로 알린다. 의존성 없음(표준 라이브러리만).

  python cgv_watch.py            # 1회 검사 후 종료 (GitHub Actions용)
  python cgv_watch.py --loop     # 상주 실행 (서버/도커용)
  python cgv_watch.py --report   # 알림 없이 현재 조건에 맞는 회차만 출력
  python cgv_watch.py --ping     # 텔레그램 연결 테스트
  python cgv_watch.py --find-movie 오디세이   # 영화 번호 찾기
  python cgv_watch.py --find-site 용산        # 극장 번호 찾기
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

API = "https://cgv.co.kr/api/v1"
CO_CD = "A420"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "state.json")

BOOKING_URL = "https://cgv.co.kr/cnm/movieBook/movie"


# --------------------------------------------------------------------------
# CGV API
# --------------------------------------------------------------------------

def api_get(path, **params):
    params.setdefault("coCd", CO_CD)
    url = f"{API}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": "https://cgv.co.kr/",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if str(body.get("statusCode")) not in ("0", "200"):
        raise RuntimeError(f"CGV API {path} 실패: {body.get('statusMessage')}")
    return body.get("data")


def search_movies(keyword):
    """상영/예매 가능한 영화 중 이름에 keyword가 들어간 것들."""
    found, seen = [], set()
    for path in ("/booking/searchAtktTopPostrList", "/booking/searchOnlyCgvMovList"):
        try:
            rows = api_get(path) or []
        except Exception:
            continue
        for m in rows:
            key = m.get("movNo")
            if key in seen:
                continue
            seen.add(key)
            name = m.get("movNm") or ""
            eng = m.get("movEnm") or ""
            if keyword.lower() in name.lower() or keyword.lower() in eng.lower():
                found.append({"movNo": key, "movNm": name})
    return found


def search_sites(keyword):
    data = api_get("/content/site/searchAllRegionAndSite") or {}
    return [s for s in (data.get("siteInfo") or []) if keyword in s.get("siteNm", "")]


def screening_dates(site_no, mov_no):
    rows = api_get("/booking/searchSiteScnscYmdListByMov",
                   siteNo=site_no, movNo=mov_no) or []
    return [r["scnYmd"] for r in rows if r.get("scnYmd")]


def showtimes(site_no, mov_no, ymd):
    return api_get("/booking/searchSchByMov", siteNo=site_no, movNo=mov_no,
                   scnYmd=ymd, rtctlScopCd="1") or []


# --------------------------------------------------------------------------
# 필터
# --------------------------------------------------------------------------

WEEKDAY_KO = "월화수목금토일"


def parse_ymd(ymd):
    return datetime.strptime(ymd, "%Y%m%d").replace(tzinfo=KST)


def hhmm(tm):
    tm = (tm or "").zfill(4)
    return f"{tm[:2]}:{tm[2:]}"


def matches(show, cfg):
    """설정된 상영관/요일/시간 조건에 맞는 회차인가."""
    f = cfg["filters"]

    halls = f.get("hall_keywords") or []
    if halls:
        blob = f"{show.get('scnsNm', '')} {show.get('movkndDsplNm', '')}"
        if not any(k.lower() in blob.lower() for k in halls):
            return False

    weekday = parse_ymd(show["scnYmd"]).weekday()  # 월=0 … 일=6
    allowed = f.get("weekdays")
    if allowed and weekday not in allowed:
        return False

    start = int((show.get("scnsrtTm") or "0000").zfill(4))
    if start < int(f.get("start_time_from", "0000")):
        return False
    if start > int(f.get("start_time_to", "2359")):
        return False

    return True


def show_key(show):
    return "|".join([
        show.get("scnYmd", ""),
        show.get("scnsNo", ""),
        show.get("scnsrtTm", ""),
        show.get("scnSseq", ""),
    ])


def format_show(show):
    d = parse_ymd(show["scnYmd"])
    seats = show.get("frSeatCnt")
    total = show.get("cpSeatCnt")
    tail = f" · 잔여 {seats}/{total}석" if seats and total else ""
    return (f"{d.strftime('%m/%d')}({WEEKDAY_KO[d.weekday()]}) "
            f"{hhmm(show.get('scnsrtTm'))}~{hhmm(show.get('scnendTm'))} "
            f"{show.get('scnsNm', '')} [{show.get('movkndDsplNm', '')}]{tail}")


# --------------------------------------------------------------------------
# 텔레그램
# --------------------------------------------------------------------------

def telegram_send(text, cfg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("telegram_chat_id")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 설정되지 않았습니다.")

    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            if attempt == 2:
                raise RuntimeError(f"텔레그램 전송 실패 {e.code}: {detail}")
        except Exception:
            if attempt == 2:
                raise
        time.sleep(3)


# --------------------------------------------------------------------------
# 설정 / 상태
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "targets": [
        {
            "name": "용산 IMAX 오디세이",
            "site_no": "0013",
            "site_name": "용산아이파크몰",
            "mov_no": "30001323",
            "movie_name": "오디세이",
        }
    ],
    "filters": {
        "hall_keywords": ["IMAX"],
        "weekdays": [0, 1, 2, 3, 4],
        "start_time_from": "2000",
        "start_time_to": "2359",
    },
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    with open(CONFIG_PATH, encoding="utf-8") as fp:
        cfg = json.load(fp)
    cfg.setdefault("targets", DEFAULT_CONFIG["targets"])
    filters = dict(DEFAULT_CONFIG["filters"])
    filters.update(cfg.get("filters") or {})
    cfg["filters"] = filters
    return cfg


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as fp:
            return json.load(fp)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as fp:
        json.dump(state, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write("\n")


def prune(seen):
    """지나간 날짜의 회차는 상태에서 버린다."""
    today = datetime.now(KST).strftime("%Y%m%d")
    return {k: v for k, v in seen.items() if k.split("|", 1)[0] >= today}


# --------------------------------------------------------------------------
# 본 로직
# --------------------------------------------------------------------------

def resolve_target(target):
    """설정에 mov_no / site_no 가 비어 있으면 이름으로 찾아 채운다."""
    if not target.get("mov_no"):
        hits = search_movies(target.get("movie_name", ""))
        if not hits:
            return None
        target["mov_no"] = hits[0]["movNo"]
        target.setdefault("movie_name", hits[0]["movNm"])
    if not target.get("site_no"):
        hits = search_sites(target.get("site_name", ""))
        if not hits:
            return None
        target["site_no"] = hits[0]["siteNo"]
    return target


def collect(target, cfg):
    """대상의 현재 상영 회차를 (조건 통과, 조건 탈락) 으로 나눠 반환."""
    dates = screening_dates(target["site_no"], target["mov_no"])
    hit, miss = [], []
    for ymd in dates:
        for show in showtimes(target["site_no"], target["mov_no"], ymd):
            (hit if matches(show, cfg) else miss).append(show)
    hit.sort(key=lambda s: (s["scnYmd"], s.get("scnsrtTm") or ""))
    return hit, miss


def check(cfg, state, notify=True, verbose=True):
    """새로 열린 회차를 찾아 알린다. 알린 개수를 반환."""
    total_new = 0

    for raw in cfg["targets"]:
        target = resolve_target(dict(raw))
        if target is None:
            if verbose:
                print(f"[skip] {raw.get('name')}: 아직 영화/극장을 찾을 수 없음")
            continue

        label = target.get("name") or target.get("movie_name")
        try:
            hit, miss = collect(target, cfg)
        except Exception as exc:
            print(f"[error] {label}: {exc}", file=sys.stderr)
            continue

        first_run = label not in state
        seen = prune(state.get(label, {}))
        fresh_keys = {show_key(s) for s in hit} - set(seen)
        fresh = [s for s in hit if show_key(s) in fresh_keys]

        if verbose:
            print(f"[{label}] 조건 일치 {len(hit)}개 / 그 외 {len(miss)}개 "
                  f"/ 신규 {len(fresh)}개" + (" (최초 실행)" if first_run else ""))
            for s in hit:
                mark = "NEW " if show_key(s) in fresh_keys else "    "
                print(f"  {mark}{format_show(s)}")

        now = datetime.now(KST).isoformat(timespec="seconds")
        for s in hit:
            seen.setdefault(show_key(s), now)
        state[label] = seen

        # 최초 실행 때는 기존 회차를 전부 새것으로 오인해 도배하므로 알리지 않는다.
        if fresh and notify and not first_run:
            movie = target.get("movie_name", "")
            site = target.get("site_name", "")
            lines = [f"🎟 <b>예매 오픈</b> — {movie} · {site}", ""]
            lines += [f"• {format_show(s)}" for s in fresh]
            if miss:
                lines.append("")
                lines.append(f"<i>(조건 밖 회차 {len(miss)}개는 생략)</i>")
            lines.append("")
            lines.append(f'<a href="{BOOKING_URL}">CGV 예매하기</a>')
            telegram_send("\n".join(lines), cfg)
            total_new += len(fresh)

    return total_new


def main():
    ap = argparse.ArgumentParser(description="CGV 예매 오픈 텔레그램 알림")
    ap.add_argument("--loop", action="store_true", help="상주 실행")
    ap.add_argument("--interval", type=int, default=300, help="--loop 폴링 주기(초)")
    ap.add_argument("--report", action="store_true", help="알림 없이 현황만 출력")
    ap.add_argument("--ping", action="store_true", help="텔레그램 연결 테스트")
    ap.add_argument("--find-movie", metavar="이름", help="영화 번호 찾기")
    ap.add_argument("--find-site", metavar="이름", help="극장 번호 찾기")
    args = ap.parse_args()

    cfg = load_config()

    if args.find_movie:
        for m in search_movies(args.find_movie):
            print(f'{m["movNo"]}\t{m["movNm"]}')
        return 0

    if args.find_site:
        for s in search_sites(args.find_site):
            print(f'{s["siteNo"]}\t{s["siteNm"]}')
        return 0

    if args.ping:
        telegram_send("✅ cgv-open-push 텔레그램 연결 정상", cfg)
        print("텔레그램 전송 성공")
        return 0

    if args.report:
        check(cfg, load_state(), notify=False)
        return 0

    if args.loop:
        state = load_state()
        while True:
            try:
                check(cfg, state)
                save_state(state)
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)
            time.sleep(args.interval)

    state = load_state()
    check(cfg, state)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
