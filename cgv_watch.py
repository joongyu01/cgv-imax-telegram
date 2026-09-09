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
import random
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

# 요청 사이 최소 간격(초) 범위. 한 번에 여러 날짜를 훑을 때 초당 여러 건이
# 몰려 나가지 않도록 매 요청마다 이 범위에서 무작위로 쉬어 간다.
REQUEST_GAP = [0.4, 1.6]
_last_call = 0.0


def _throttle():
    global _last_call
    wait = _last_call + random.uniform(*REQUEST_GAP) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def api_get(path, **params):
    _throttle()
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
    """콘솔 로그용 한 줄."""
    d = parse_ymd(show["scnYmd"])
    seats = show.get("frSeatCnt")
    total = show.get("cpSeatCnt")
    tail = f" · 잔여 {seats}/{total}석" if seats and total else ""
    return (f"{d.strftime('%m/%d')}({WEEKDAY_KO[d.weekday()]}) "
            f"{hhmm(show.get('scnsrtTm'))}~{hhmm(show.get('scnendTm'))} "
            f"{show.get('scnsNm', '')} [{show.get('movkndDsplNm', '')}]{tail}")


def format_show_long(show):
    """텔레그램용. 날짜와 시작 시각을 앞에 굵게 세운다."""
    d = parse_ymd(show["scnYmd"])
    seats = show.get("frSeatCnt")
    total = show.get("cpSeatCnt")
    tail = f" · 잔여 {seats}/{total}석" if seats and total else ""
    return (f"📅 <b>{d.year}년 {d.month}월 {d.day}일({WEEKDAY_KO[d.weekday()]}) "
            f"{hhmm(show.get('scnsrtTm'))}</b> 시작\n"
            f"     ~{hhmm(show.get('scnendTm'))} 종료 · "
            f"{show.get('scnsNm', '')} · {show.get('movkndDsplNm', '')}{tail}")


# --------------------------------------------------------------------------
# 텔레그램
# --------------------------------------------------------------------------

def telegram_creds(cfg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or cfg.get("telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or cfg.get("telegram_chat_id")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 설정되지 않았습니다.")
    return token, str(chat_id)


def telegram_call(method, cfg, **fields):
    token, _ = telegram_creds(cfg)
    payload = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}", data=payload)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            if attempt == 2:
                raise RuntimeError(f"텔레그램 {method} 실패 {e.code}: {detail}")
        except Exception:
            if attempt == 2:
                raise
        time.sleep(3)


def telegram_send(text, cfg):
    _, chat_id = telegram_creds(cfg)
    header = cfg.get("message_header")
    if header:
        text = f"<b>{header}</b>\n\n{text}"
    return telegram_call("sendMessage", cfg, chat_id=chat_id, text=text,
                         parse_mode="HTML", disable_web_page_preview="true")


def telegram_alert(text, cfg):
    """놓치면 안 되는 알림은 여러 번 연달아 보내 확실히 깨운다.

    alert_burst 는 [[횟수, 간격초], ...] 형태. 기본값은 0.5초 간격 5회 +
    1초 간격 5회. 텔레그램이 한 채팅에 초당 여러 건을 보내면 429를 줄 수
    있는데, 그건 그 한 건만 건너뛰고 나머지는 계속 보낸다.
    """
    burst = cfg["filters"].get("alert_burst") or [[1, 0]]
    sent = 0
    for count, gap in burst:
        for _ in range(int(count)):
            try:
                telegram_send(text, cfg)
                sent += 1
            except Exception as exc:
                print(f"[warn] 반복 알림 {sent + 1}번째 실패: {exc}", file=sys.stderr)
            time.sleep(float(gap))
    print(f"[alert] {sent}회 발송")
    return sent


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
        "full_sweep_seconds": 300,
        "fail_alert_after": 3,
        "request_gap": [0.4, 1.6],
        "seat_watch_seconds": 60,
        "cancel_min_seats": 2,
        "alert_burst": [[5, 0.5], [5, 1.0]],
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


def collect(target, cfg, skip_dates=None):
    """상영 회차를 (조건 통과, 조건 탈락, 전체 상영일) 로 반환.

    상영일 목록 조회는 1회로 끝나므로 매 주기 호출해도 부담이 없다. 반면
    날짜별 회차 조회는 상영일 수만큼 요청이 나가므로, 평소에는 skip_dates
    (이미 확인한 날짜) 를 빼고 새로 생긴 날짜만 확인한다.
    """
    dates = screening_dates(target["site_no"], target["mov_no"])
    scan = dates if skip_dates is None else [d for d in dates if d not in skip_dates]

    hit, miss = [], []
    for ymd in scan:
        for show in showtimes(target["site_no"], target["mov_no"], ymd):
            (hit if matches(show, cfg) else miss).append(show)
    hit.sort(key=lambda s: (s["scnYmd"], s.get("scnsrtTm") or ""))
    return hit, miss, dates


def load_entry(state, label):
    """상태 항목을 {dates, last_full, seen} 형태로 정규화해서 읽는다."""
    entry = state.get(label)
    if entry is None:
        return None
    # 예전 형식: {회차키: 시각} 이 그대로 들어 있던 경우
    if entry and all(isinstance(v, str) for v in entry.values()):
        return {"dates": [], "last_full": 0, "last_seat": 0,
                "seen": dict(entry), "seats": {}}
    return {
        "dates": entry.get("dates") or [],
        "last_full": entry.get("last_full") or 0,
        "last_seat": entry.get("last_seat") or 0,
        "seen": entry.get("seen") or {},
        "seats": entry.get("seats") or {},
    }


def health(state, label):
    return state.setdefault("_health", {}).setdefault(
        label, {"fail_streak": 0, "alerted": False})


def report_failure(label, exc, cfg, state, notify):
    """CGV 조회가 연속으로 실패하면 한 번만 알린다.

    Cloudflare 차단이든 CGV 점검이든, 봇이 조용히 죽어 있는 상태를 모르고
    지나가는 게 제일 나쁘다. 다만 매 주기 알리면 도배가 되므로 연속 실패가
    기준치를 넘는 순간 한 번만 보내고 복구될 때까지 입을 다문다.
    """
    h = health(state, label)
    h["fail_streak"] += 1
    h["last_error"] = f"{type(exc).__name__}: {exc}"[:300]

    threshold = int(cfg["filters"].get("fail_alert_after", 3))
    if not notify or h["alerted"] or h["fail_streak"] < threshold:
        return

    text = (f"⚠️ <b>조회 실패</b> — {label}\n\n"
            f"연속 {h['fail_streak']}회 실패했습니다. CGV 점검이거나 요청이 차단됐을 수 있습니다.\n"
            f"<code>{h['last_error']}</code>\n\n"
            f"복구되면 다시 알려드립니다.")
    try:
        telegram_send(text, cfg)
        h["alerted"] = True
    except Exception as send_exc:      # 알림 경로까지 죽었으면 로그만 남긴다
        print(f"[error] 실패 알림 전송 실패: {send_exc}", file=sys.stderr)


def report_recovery(label, cfg, state, notify):
    h = health(state, label)
    h["last_ok"] = datetime.now(KST).strftime("%m/%d %H:%M:%S")
    if h["fail_streak"] == 0:
        return
    was_alerted = h["alerted"]
    streak = h["fail_streak"]
    h["fail_streak"] = 0
    h["alerted"] = False
    h.pop("last_error", None)
    if notify and was_alerted:
        try:
            telegram_send(f"✅ <b>복구</b> — {label}\n\n"
                          f"{streak}회 실패 후 정상 조회를 재개했습니다.", cfg)
        except Exception as exc:
            print(f"[error] 복구 알림 전송 실패: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# 봇 명령 처리 (/status 등)
# --------------------------------------------------------------------------

COMMANDS = [
    ("status", "감시 상태와 CGV API 정상 여부"),
    ("list", "지금 조건에 맞는 회차 목록"),
    ("help", "명령 목록"),
]

HELP_TEXT = ("<b>사용할 수 있는 명령</b>\n\n"
             + "\n".join(f"/{c} — {d}" for c, d in COMMANDS))


def probe_api():
    """CGV API를 실제로 한 번 찔러 보고 (정상여부, 소요ms, 메시지) 반환."""
    started = time.monotonic()
    try:
        api_get("/booking/searchLastScnDay")
        return True, int((time.monotonic() - started) * 1000), "정상 응답"
    except Exception as exc:
        return False, int((time.monotonic() - started) * 1000), f"{type(exc).__name__}: {exc}"[:200]


def status_text(cfg, state):
    ok, ms, detail = probe_api()
    lines = [f"{'✅' if ok else '⚠️'} <b>CGV API</b> — {detail} ({ms}ms)", ""]

    f = cfg["filters"]
    days = "".join(WEEKDAY_KO[d] for d in sorted(f.get("weekdays") or range(7)))
    lines.append(f"<b>감시 조건</b> · {days} · "
                 f"{hhmm(f['start_time_from'])}~{hhmm(f['start_time_to'])} · "
                 f"{'/'.join(f.get('hall_keywords') or ['전체'])}")

    for raw in cfg["targets"]:
        label = raw.get("name") or raw.get("movie_name")
        h = (state.get("_health") or {}).get(label, {})
        entry = load_entry(state, label)
        lines.append("")
        lines.append(f"<b>{label}</b>")
        if entry is None:
            lines.append("  아직 한 번도 조회하지 못했습니다.")
            continue
        lines.append(f"  감시 중인 회차 {len(entry['seen'])}개 / 상영일 {len(entry['dates'])}일")
        if entry["last_full"]:
            ago = int(time.time() - entry["last_full"])
            lines.append(f"  마지막 전체 조회 {ago // 60}분 {ago % 60}초 전")
        if entry["last_seat"]:
            ago = int(time.time() - entry["last_seat"])
            lines.append(f"  마지막 좌석 확인 {ago // 60}분 {ago % 60}초 전")
        if h.get("last_ok"):
            lines.append(f"  마지막 정상 조회 {h['last_ok']}")
        streak = h.get("fail_streak", 0)
        if streak:
            lines.append(f"  ⚠️ 연속 실패 {streak}회 — <code>{h.get('last_error', '')}</code>")

    return "\n".join(lines)


def list_text(cfg, state):
    lines = []
    for raw in cfg["targets"]:
        target = resolve_target(dict(raw))
        label = raw.get("name") or raw.get("movie_name")
        if target is None:
            lines.append(f"<b>{label}</b>\n  영화/극장을 찾을 수 없습니다.")
            continue
        try:
            hit, miss, dates = collect(target, cfg)
        except Exception as exc:
            lines.append(f"<b>{label}</b>\n  조회 실패: <code>{exc}</code>")
            continue
        lines.append(f"<b>{label}</b> — 조건 일치 {len(hit)}개 (그 외 {len(miss)}개)")
        lines += [format_show_long(s) for s in hit] or ["  (없음)"]
    return "\n".join(lines) or "감시 대상이 없습니다."


def handle_commands(cfg, state):
    """텔레그램에 들어온 명령에 답한다. 등록된 chat_id 외에는 무시."""
    try:
        _, my_chat = telegram_creds(cfg)
    except RuntimeError:
        return

    offset = state.get("_tg_offset", 0)
    try:
        res = telegram_call("getUpdates", cfg, offset=offset, timeout=0,
                            allowed_updates=json.dumps(["message"]))
    except Exception as exc:
        print(f"[error] getUpdates 실패: {exc}", file=sys.stderr)
        return

    for upd in res.get("result", []):
        state["_tg_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip()
        # 봇 링크를 아는 사람은 누구나 말을 걸 수 있으므로 본인 채팅만 응답한다.
        if str((msg.get("chat") or {}).get("id")) != my_chat or not text.startswith("/"):
            continue

        cmd = text[1:].split("@")[0].split()[0].lower()
        print(f"[cmd] /{cmd}")
        try:
            if cmd == "status":
                reply = status_text(cfg, state)
            elif cmd in ("list", "now"):
                reply = list_text(cfg, state)
            elif cmd in ("help", "start"):
                reply = HELP_TEXT
            else:
                reply = f"모르는 명령입니다.\n\n{HELP_TEXT}"
            telegram_send(reply, cfg)
        except Exception as exc:
            print(f"[error] /{cmd} 처리 실패: {exc}", file=sys.stderr)


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
        entry = load_entry(state, label)

        now_ts = time.time()
        f = cfg["filters"]
        full = entry is None or now_ts - entry["last_full"] >= int(f.get("full_sweep_seconds", 300))
        seat_due = entry is not None and (
            now_ts - entry["last_seat"] >= int(f.get("seat_watch_seconds", 60)))

        if full:
            known = None                       # 모든 상영일
        elif seat_due:
            # 조건에 맞는 회차가 있는 날짜만 = 취소표를 지켜볼 가치가 있는 날짜만
            watch = {k.split("|", 1)[0] for k in entry["seen"]}
            known = {d for d in entry["dates"] if d not in watch}
        else:
            known = set(entry["dates"])        # 새로 생긴 날짜만

        try:
            hit, miss, dates = collect(target, cfg, skip_dates=known)
        except Exception as exc:
            print(f"[error] {label}: {exc}", file=sys.stderr)
            report_failure(label, exc, cfg, state, notify)
            continue

        report_recovery(label, cfg, state, notify)

        first_run = entry is None
        seen = prune(entry["seen"]) if entry else {}
        seats = dict(entry["seats"]) if entry else {}
        fresh_keys = {show_key(s) for s in hit} - set(seen)
        fresh = [s for s in hit if show_key(s) in fresh_keys]

        # 잔여 좌석이 한 번에 여러 석 늘었다면 그만큼 동시에 취소된 것이다.
        # 붙어 있는 자리인지는 좌석배치도 없이 알 수 없지만, 2인이 함께
        # 취소하면 연석이 통째로 풀리므로 "동시 증가폭"이 가장 가까운 신호다.
        min_seats = int(f.get("cancel_min_seats", 2))
        cancels = []
        for s in hit:
            key = show_key(s)
            try:
                now_free = int(s.get("frSeatCnt"))
            except (TypeError, ValueError):
                continue
            before = seats.get(key)
            if before is not None and now_free - before >= min_seats:
                cancels.append((s, now_free - before, now_free))
            seats[key] = now_free

        if verbose:
            scanned = len(dates) if full else len([d for d in dates if d not in known])
            scope = "전체 스윕" if full else ("좌석 확인" if seat_due else "신규 날짜만")
            print(f"[{label}] {scope} · 상영일 {len(dates)}일 중 {scanned}일 조회 "
                  f"→ 조건 일치 {len(hit)}개 / 그 외 {len(miss)}개 / "
                  f"신규 {len(fresh)}개 / 취소표 {len(cancels)}건"
                  + (" (최초 실행)" if first_run else ""))
            for s in hit:
                mark = "NEW " if show_key(s) in fresh_keys else "    "
                print(f"  {mark}{format_show(s)}")

        now = datetime.now(KST).isoformat(timespec="seconds")
        for s in hit:
            seen.setdefault(show_key(s), now)
        keep = set(seen)
        state[label] = {
            "dates": dates,
            "last_full": now_ts if full else (entry["last_full"] if entry else 0),
            "last_seat": now_ts if (full or seat_due) else (entry["last_seat"] if entry else 0),
            "seen": seen,
            "seats": {k: v for k, v in seats.items() if k in keep},
        }

        if not notify or first_run:
            # 최초 실행 때는 기존 회차를 전부 새것으로 오인해 도배하므로 알리지 않는다.
            continue

        movie = target.get("movie_name", "")
        site = target.get("site_name", "")

        if fresh:
            lines = [f"🎟 <b>예매 오픈</b> — {movie} · {site}", ""]
            lines += [format_show_long(s) for s in fresh]
            if miss:
                lines.append("")
                lines.append(f"<i>(조건 밖 회차 {len(miss)}개는 생략)</i>")
            lines.append("")
            lines.append(f'<a href="{BOOKING_URL}">CGV 예매하기</a>')
            telegram_alert("\n".join(lines), cfg)
            total_new += len(fresh)

        if cancels:
            lines = [f"🎫 <b>취소표</b> — {movie} · {site}", ""]
            for s, delta, free in cancels:
                lines.append(format_show_long(s))
                lines.append(f"     🎫 <b>{delta}석이 한 번에</b> 풀렸습니다 "
                             f"→ 현재 {free}석 남음")
            lines.append("")
            lines.append(f'<a href="{BOOKING_URL}">CGV 예매하기</a>')
            telegram_alert("\n".join(lines), cfg)
            total_new += len(cancels)

    return total_new


def main():
    ap = argparse.ArgumentParser(description="CGV 예매 오픈 텔레그램 알림")
    ap.add_argument("--loop", action="store_true", help="상주 실행")
    ap.add_argument("--interval", type=int, default=300, help="--loop 폴링 주기(초)")
    ap.add_argument("--duration", type=int, default=0,
                    help="--loop 최대 실행 시간(초). 0이면 무한")
    ap.add_argument("--jitter", type=float, default=0.4,
                    help="주기 흔들림 비율 0~0.9 (0.4면 interval의 60~140%%)")
    ap.add_argument("--report", action="store_true", help="알림 없이 현황만 출력")
    ap.add_argument("--ping", action="store_true", help="텔레그램 연결 테스트")
    ap.add_argument("--find-movie", metavar="이름", help="영화 번호 찾기")
    ap.add_argument("--find-site", metavar="이름", help="극장 번호 찾기")
    args = ap.parse_args()

    cfg = load_config()

    gap = cfg["filters"].get("request_gap")
    if isinstance(gap, (list, tuple)) and len(gap) == 2:
        REQUEST_GAP[:] = [float(gap[0]), float(gap[1])]

    if args.find_movie:
        for m in search_movies(args.find_movie):
            print(f'{m["movNo"]}\t{m["movNm"]}')
        return 0

    if args.find_site:
        for s in search_sites(args.find_site):
            print(f'{s["siteNo"]}\t{s["siteNm"]}')
        return 0

    if args.ping:
        telegram_call("setMyCommands", cfg, commands=json.dumps(
            [{"command": c, "description": d} for c, d in COMMANDS]))
        telegram_send("✅ 연결 정상\n\n" + HELP_TEXT, cfg)
        print("텔레그램 전송 성공 · 명령 메뉴 등록 완료")
        return 0

    if args.report:
        check(cfg, {}, notify=False)   # 빈 상태로 돌려 항상 전체를 조회한다
        return 0

    if args.loop:
        state = load_state()
        deadline = time.monotonic() + args.duration if args.duration else None
        jitter = max(0.0, min(0.9, args.jitter))
        while True:
            try:
                check(cfg, state)
                handle_commands(cfg, state)
                save_state(state)
            except Exception as exc:
                print(f"[error] {exc}", file=sys.stderr)

            # 매번 똑같은 초에 때리지 않도록 주기를 흔든다.
            nap = args.interval * random.uniform(1 - jitter, 1 + jitter)
            if deadline and time.monotonic() + nap >= deadline:
                print("[loop] 지정한 실행 시간에 도달, 종료")
                return 0
            print(f"[loop] {nap:.1f}초 대기")
            time.sleep(nap)

    state = load_state()
    check(cfg, state)
    handle_commands(cfg, state)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
