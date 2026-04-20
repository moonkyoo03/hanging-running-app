import calendar
import hashlib
import html
import json
import math
import os
import random
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta, time as dt_time

import folium
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────
st.set_page_config(page_title="한강 러닝 루트 추천", layout="wide")

st.markdown(
    """
    <style>
    /* 모바일·좁은 화면: 루트 탭 Folium 직후 iframe만 높이 축소 (마커 div + 인접 컴포넌트) */
    @media screen and (max-width: 768px) {
        .block-container { padding-top: 0.75rem !important; padding-bottom: 0.75rem !important; }
        div.element-container:has(.hangang-folium-marker) + div.element-container iframe {
            height: 320px !important;
            max-height: 42vh !important;
            min-height: 240px !important;
        }
    }
    /* 러닝 기록 탭 – 달력 카드 톤 */
    .rj-hero {
        background: linear-gradient(135deg, #0f766e 0%, #115e59 45%, #134e4a 100%);
        color: #ecfeff;
        padding: 1.25rem 1.35rem;
        border-radius: 18px;
        margin-bottom: 1rem;
        box-shadow: 0 16px 40px rgba(15, 118, 110, 0.35);
        border: 1px solid rgba(204, 251, 241, 0.25);
    }
    .rj-hero h2 { margin: 0 0 0.35rem 0; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }
    .rj-hero p { margin: 0; opacity: 0.92; font-size: 0.92rem; line-height: 1.45; }
    .rj-cal-wrap {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border-radius: 16px;
        padding: 1rem 0.75rem 1.1rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
        margin-bottom: 1rem;
    }
    .rj-day-head {
        text-align: center;
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.06em;
        padding: 0.15rem 0 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 한강 공원
HANGANG_PARKS = [
    ("여의도한강공원", 37.5271, 126.9326),
    ("반포한강공원",   37.5096, 126.9945),
    ("뚝섬한강공원",   37.5293, 127.0720),
    ("잠실한강공원",   37.5188, 127.0875),
    ("망원한강공원",   37.5555, 126.8976),
    ("이촌한강공원",   37.5226, 126.9722),
    ("난지한강공원",   37.5667, 126.8765),
]

# 한강변 시설 및 랜드마크
HANGANG_LANDMARKS = [
    # 교량
    ("한강대교 남단",     37.5186, 126.9641),
    ("마포대교 북단",     37.5390, 126.9477),
    ("원효대교 북단",     37.5353, 126.9568),
    ("반포대교 북단",     37.5148, 126.9987),
    ("동작대교 북단",     37.5087, 126.9807),
    ("잠수교 북단",       37.5126, 126.9996),
    ("성수대교 북단",     37.5373, 127.0558),
    ("영동대교 북단",     37.5295, 127.0637),
    ("잠실대교 북단",     37.5221, 127.0857),
    # 체육·문화 시설
    ("세빛섬",            37.5073, 126.9977),
    ("노들섬",            37.5170, 126.9600),
    ("선유도공원",        37.5382, 126.8986),
    ("서울마리나",        37.5302, 126.8832),
    ("여의나루역",        37.5280, 126.9337),
    ("뚝섬유원지역",      37.5306, 127.0668),
    ("잠실나루역",        37.5181, 127.0832),
    # 운동·편의 시설
    ("반포 수상택시 승강장", 37.5089, 126.9971),
    ("이촌 한강 수영장",     37.5191, 126.9693),
    ("뚝섬 자전거공원",      37.5303, 127.0735),
    ("망원 수변무대",        37.5563, 126.8989),
    ("여의도 물빛광장",      37.5261, 126.9290),
    ("잠실 수상스키장",      37.5200, 127.0910),
    ("광나루 자전거공원",    37.5447, 127.1092),
    ("암사 생태공원",        37.5540, 127.1337),
]

# 루트 생성에 사용할 전체 후보 지점
HANGANG_SPOTS = HANGANG_PARKS + HANGANG_LANDMARKS

PARK_FACILITIES = {
    "여의도한강공원": {
        "difficulty": "쉬움", "surface": "아스팔트 + 자전거도로 주의",
        "facilities": ["화장실 다수", "편의점 CU·GS", "자전거 대여소", "음수대"],
        "tip": "여의도 순환 코스로 5.5km 루프 가능",
    },
    "반포한강공원": {
        "difficulty": "쉬움", "surface": "포장 트랙, 평탄",
        "facilities": ["화장실", "세빛섬 카페", "음수대"],
        "tip": "달빛무지개분수 야간 러닝 명소",
    },
    "뚝섬한강공원": {
        "difficulty": "보통", "surface": "포장 + 일부 잔디",
        "facilities": ["화장실", "뚝섬유원지역 근접", "샤워시설"],
        "tip": "강 조망 구간이 길어 페이스런에 적합",
    },
    "잠실한강공원": {
        "difficulty": "보통", "surface": "포장 트랙",
        "facilities": ["화장실", "편의점", "운동시설"],
        "tip": "잠실대교~올림픽대교 구간 직선 코스",
    },
    "망원한강공원": {
        "difficulty": "쉬움", "surface": "포장, 넓은 광장",
        "facilities": ["화장실", "음수대", "농구장"],
        "tip": "노을공원 연계 언덕 코스 도전 가능",
    },
    "이촌한강공원": {
        "difficulty": "쉬움", "surface": "포장, 평탄",
        "facilities": ["화장실", "자전거도로 병행"],
        "tip": "국립중앙박물관 방면 산책로 연계",
    },
    "난지한강공원": {
        "difficulty": "어려움", "surface": "언덕 구간 포함",
        "facilities": ["화장실", "캠핑장"],
        "tip": "하늘공원 계단 업힐 훈련에 최적",
    },
}

HANGANG_CENTER = (37.53, 126.98)
OSRM_URL = "https://router.project-osrm.org/route/v1/foot"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT_ROUTE = 5
TIMEOUT_INFO = 8

USERS_FILE = "users.json"
SHARES_FILE = "shared_runs.json"
FRIENDS_PREFIX = "friends_"
INBOX_PREFIX = "inbox_"
DIFFICULTY_COLOR = {"쉬움": "🟢", "보통": "🟡", "어려움": "🔴"}

WMO_ICON = {
    0: ("맑음", "☀️"), 1: ("대체로 맑음", "🌤️"), 2: ("구름 조금", "⛅"),
    3: ("흐림", "☁️"), 45: ("안개", "🌫️"), 48: ("안개", "🌫️"),
    51: ("이슬비", "🌦️"), 53: ("이슬비", "🌦️"), 55: ("이슬비", "🌦️"),
    61: ("비", "🌧️"), 63: ("비", "🌧️"), 65: ("강한 비", "🌧️"),
    71: ("눈", "❄️"), 73: ("눈", "❄️"), 75: ("강한 눈", "❄️"),
    80: ("소나기", "🌦️"), 81: ("소나기", "🌦️"), 95: ("뇌우", "⛈️"),
}

INDOOR_ALTERNATIVES = [
    "실내 트레드밀 30분 + 가벼운 스트레칭",
    "홈트 유산소 20분 + 하체 보강 10분",
    "실내 자전거 40분",
    "가벼운 코어 운동 + 걷기 대체",
]

# ──────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pace_to_string(minutes_per_km):
    if not minutes_per_km or minutes_per_km <= 0:
        return "-"
    total_sec = int(round(minutes_per_km * 60))
    return f"{total_sec // 60}:{total_sec % 60:02d}/km"


def pace_to_minutes(pace_str):
    try:
        parts = pace_str.replace("/km", "").split(":")
        return int(parts[0]) + int(parts[1]) / 60
    except Exception:
        return None


def estimate_calories(weight_kg, distance_km):
    if weight_kg <= 0 or distance_km <= 0:
        return 0
    return round(weight_kg * distance_km)


def wmo_label(code):
    if code is None:
        return ("알 수 없음", "❓")
    return WMO_ICON.get(int(code), ("흐림", "☁️"))


def weather_category(temperature, pm25, wcode):
    if wcode is not None and int(wcode) >= 61:
        return "비/눈"
    if temperature is not None and temperature >= 28:
        return "더운 날"
    if temperature is not None and temperature <= 3:
        return "추운 날"
    if pm25 is not None and pm25 > 35:
        return "미세먼지"
    return "맑음/쾌청"


# ──────────────────────────────────────────────────────────
# 로그인 / 사용자 관리
# ──────────────────────────────────────────────────────────
def _safe_read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _safe_write_json(path: str, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_users():
    return _safe_read_json(USERS_FILE, {})


def save_users(users):
    _safe_write_json(USERS_FILE, users)


def register_user(username, password):
    users = load_users()
    if username in users:
        return False, "이미 존재하는 아이디입니다."
    if len(username) < 2:
        return False, "아이디는 2자 이상이어야 합니다."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상이어야 합니다."
    users[username] = hash_pw(password)
    save_users(users)
    return True, "회원가입 완료!"


def login_user(username, password):
    users = load_users()
    if username not in users:
        return False, "존재하지 않는 아이디입니다."
    if users[username] != hash_pw(password):
        return False, "비밀번호가 틀렸습니다."
    return True, "로그인 성공!"


# ──────────────────────────────────────────────────────────
# 러닝 메이트(친구) / 공유
# ──────────────────────────────────────────────────────────
def friends_path(username: str) -> str:
    return f"{FRIENDS_PREFIX}{username}.json"


def inbox_path(username: str) -> str:
    return f"{INBOX_PREFIX}{username}.json"


def load_friends(username: str):
    return _safe_read_json(friends_path(username), [])


def save_friends(username: str, friends):
    uniq = []
    for f in friends or []:
        if f and f not in uniq:
            uniq.append(f)
    _safe_write_json(friends_path(username), uniq[:200])


def add_friend(username: str, friend_id: str):
    friend_id = (friend_id or "").strip()
    if not friend_id:
        return False, "친구 아이디를 입력해주세요."
    if friend_id == username:
        return False, "본인은 친구로 추가할 수 없습니다."
    users = load_users()
    if friend_id not in users:
        return False, "존재하지 않는 아이디입니다."
    fs = load_friends(username)
    if friend_id in fs:
        return False, "이미 친구로 추가되어 있습니다."
    fs.insert(0, friend_id)
    save_friends(username, fs)
    return True, f"'{friend_id}' 님을 러닝 메이트로 추가했습니다!"


def load_inbox(username: str):
    return _safe_read_json(inbox_path(username), [])


def push_inbox(to_user: str, payload: dict):
    inbox = load_inbox(to_user)
    inbox.insert(0, payload)
    _safe_write_json(inbox_path(to_user), inbox[:80])


def load_shares():
    return _safe_read_json(SHARES_FILE, {})


def save_shares(shares: dict):
    _safe_write_json(SHARES_FILE, shares)


def make_share_token(owner: str, saved_at: str) -> str:
    seed = f"{owner}|{saved_at}|{random.random()}|{datetime.now().timestamp()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def upsert_share(owner: str, run_item: dict):
    saved_at = str(run_item.get("saved_at", "")).strip()
    if not saved_at:
        return None
    token = make_share_token(owner, saved_at)
    shares = load_shares()
    shares[token] = {
        "token": token,
        "owner": owner,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run": run_item,
    }
    save_shares(shares)
    return token


def render_share_card(owner: str, run_item: dict, token: str):
    snap = run_item.get("weather_snapshot") or {}
    w_badge = ""
    if snap:
        w_badge = (
            f"{snap.get('weather_icon', '')} {snap.get('weather_label', '')} "
            f"{snap.get('temperature', '-')}°C"
        )
    spots = run_item.get("spots") or []
    spots_txt = " → ".join(spots) if spots else "—"
    memo = str(run_item.get("memo") or "").strip()
    memo_html = (
        f"<div style='margin-top:0.55rem;padding:0.55rem 0.7rem;"
        f"background:rgba(240,253,250,0.65);border-radius:10px;"
        f"border:1px solid rgba(20,184,166,0.22);'>"
        f"💬 {html.escape(memo)}</div>"
        if memo
        else ""
    )
    st.markdown(
        f"""
        <div style="border-radius:18px;padding:1.05rem 1.15rem;
                    background:linear-gradient(135deg,#0f766e 0%,#115e59 50%,#134e4a 100%);
                    color:#ecfeff;border:1px solid rgba(204,251,241,0.22);
                    box-shadow:0 16px 44px rgba(15,118,110,0.35);">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
            <div>
              <div style="font-size:0.78rem;opacity:0.92;">🏃 러닝 기록 공유 카드</div>
              <div style="font-size:1.18rem;font-weight:800;letter-spacing:-0.02em;margin-top:0.15rem;">
                {html.escape(owner)}님의 러닝
              </div>
            </div>
            <div style="text-align:right;font-size:0.85rem;opacity:0.95;">
              <div style="font-weight:700;">공유 코드</div>
              <div style="font-size:1.05rem;font-weight:900;letter-spacing:0.06em;">{html.escape(token)}</div>
            </div>
          </div>
          <div style="margin-top:0.75rem;display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
            <div style="background:rgba(255,255,255,0.10);border-radius:12px;padding:0.55rem 0.65rem;">
              <div style="font-size:0.72rem;opacity:0.9;">거리</div>
              <div style="font-size:1.05rem;font-weight:800;">{html.escape(str(run_item.get('distance_km','-')))} km</div>
            </div>
            <div style="background:rgba(255,255,255,0.10);border-radius:12px;padding:0.55rem 0.65rem;">
              <div style="font-size:0.72rem;opacity:0.9;">페이스</div>
              <div style="font-size:1.05rem;font-weight:800;">{html.escape(str(run_item.get('pace','-')))}</div>
            </div>
            <div style="background:rgba(255,255,255,0.10);border-radius:12px;padding:0.55rem 0.65rem;">
              <div style="font-size:0.72rem;opacity:0.9;">칼로리</div>
              <div style="font-size:1.05rem;font-weight:800;">{html.escape(str(run_item.get('calories_kcal','-')))} kcal</div>
            </div>
          </div>
          <div style="margin-top:0.7rem;font-size:0.9rem;opacity:0.96;">
            📍 {html.escape(spots_txt)}
            {f"<div style='margin-top:0.25rem;font-size:0.85rem;opacity:0.95;'>{html.escape(w_badge)}</div>" if w_badge else ""}
            {memo_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────
# JSON I/O (유저별)
# ──────────────────────────────────────────────────────────
def _load_json(path, default):
    return _safe_read_json(path, default)


def _save_json(path, data):
    _safe_write_json(path, data)


def history_path(username):
    return f"history_{username}.json"


def favorites_path(username):
    return f"favorites_{username}.json"


def goal_path(username):
    return f"goal_{username}.json"


def load_history(username):
    return _load_json(history_path(username), [])


def save_history(username, entry):
    h = load_history(username)
    h.insert(0, entry)
    _save_json(history_path(username), h[:50])


def load_favorites(username):
    return _load_json(favorites_path(username), [])


def save_favorite(username, entry):
    f = load_favorites(username)
    f.insert(0, entry)
    _save_json(favorites_path(username), f[:10])


def delete_favorite(username, idx):
    f = load_favorites(username)
    if 0 <= idx < len(f):
        f.pop(idx)
    _save_json(favorites_path(username), f)


def load_goal(username):
    return _load_json(goal_path(username), {"monthly_km": 50.0})


def save_goal(username, goal_km):
    _save_json(goal_path(username), {"monthly_km": goal_km})


# ──────────────────────────────────────────────────────────
# 외부 API
# ──────────────────────────────────────────────────────────
def get_current_weather():
    lat, lon = HANGANG_CENTER
    advice = {
        "temperature": None, "pm10": None, "pm25": None,
        "precipitation": None, "recommend": None, "wcode": None,
        "message": "날씨 정보를 가져오지 못했습니다.",
    }
    try:
        wr = requests.get(WEATHER_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation,weathercode",
        }, timeout=TIMEOUT_INFO)
        wr.raise_for_status()
        weather = wr.json().get("current", {})

        ar = requests.get(AIR_QUALITY_URL, params={
            "latitude": lat, "longitude": lon, "current": "pm10,pm2_5",
        }, timeout=TIMEOUT_INFO)
        ar.raise_for_status()
        air = ar.json().get("current", {})

        t = weather.get("temperature_2m")
        prec = weather.get("precipitation", 0)
        wcode = weather.get("weathercode")
        pm10 = air.get("pm10")
        pm25 = air.get("pm2_5")
        advice.update({"temperature": t, "pm10": pm10, "pm25": pm25,
                        "precipitation": prec, "wcode": wcode})

        bad, reasons = False, []
        if t is not None and (t < -5 or t > 32):
            bad = True; reasons.append("기온이 극단적")
        if prec is not None and prec > 0.5:
            bad = True; reasons.append("비")
        if pm10 is not None and pm10 > 80:
            bad = True; reasons.append("미세먼지 높음")
        if pm25 is not None and pm25 > 35:
            bad = True; reasons.append("초미세먼지 높음")

        advice["recommend"] = not bad
        advice["message"] = ("오늘은 러닝 비추천 (" + ", ".join(reasons) + ")"
                              if bad else "오늘은 러닝 추천 👍")
    except Exception:
        pass
    return advice


def get_7day_forecast():
    lat, lon = HANGANG_CENTER
    try:
        res = requests.get(WEATHER_URL, params={
            "latitude": lat, "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
            "forecast_days": 7, "timezone": "Asia/Seoul",
        }, timeout=TIMEOUT_INFO)
        res.raise_for_status()
        daily = res.json().get("daily", {})
        return list(zip(
            daily.get("time", []),
            daily.get("temperature_2m_max", []),
            daily.get("temperature_2m_min", []),
            daily.get("precipitation_sum", []),
            daily.get("weathercode", []),
        ))
    except Exception:
        return []


def is_good_running_day(tmax, tmin, prec, wcode):
    if tmax is None or tmin is None:
        return False
    avg_t = (tmax + tmin) / 2
    if avg_t < -5 or avg_t > 32:
        return False
    if prec is not None and prec > 2.0:
        return False
    if wcode is not None and int(wcode) >= 61:
        return False
    return True


# ──────────────────────────────────────────────────────────
# OSRM 경로
# ──────────────────────────────────────────────────────────
def osrm_route(coords):
    try:
        coord_str = ";".join([f"{lon},{lat}" for lat, lon in coords])
        res = requests.get(
            f"{OSRM_URL}/{coord_str}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=TIMEOUT_ROUTE,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None, None
        route = data["routes"][0]
        return route["distance"], route["geometry"]["coordinates"]
    except Exception:
        return None, None


def generate_random_route(
    target_km,
    route_mode,
    tolerance_ratio=0.08,
    max_try=30,
    start_hint=None,
    departure_time_str=None,
    condition_level="보통",
    waypoint_count=None,
):
    """공원 + 시설/랜드마크를 모두 활용한 다양한 루트 생성"""
    target_m = target_km * 1000.0
    best, best_diff = None, float("inf")

    for attempt in range(max_try):
        # 매 시도마다 시드 변경으로 다양성 확보
        time_seed = 0
        if departure_time_str:
            try:
                time_seed = int(departure_time_str.replace(":", ""))
            except Exception:
                time_seed = 0
        random.seed(
            st.session_state.get("seed", 0)
            + attempt * 37
            + int(target_km * 100)
            + time_seed
        )

        max_points = min(10, len(HANGANG_SPOTS))
        if condition_level == "나쁨":
            max_points = min(6, max_points)
        if waypoint_count is not None:
            try:
                point_count = int(waypoint_count)
                point_count = max(2, min(point_count, max_points))
            except Exception:
                point_count = random.randint(2, min(6, max_points))
        else:
            point_count = random.randint(2, min(6 if condition_level == "나쁨" else 8, max_points))

        # 출발은 반드시 공원 중에서 선택
        start = None
        if start_hint:
            for s in HANGANG_PARKS:
                if s[0] == start_hint:
                    start = s
                    break
        if not start:
            if condition_level == "나쁨":
                easy_parks = [p for p in HANGANG_PARKS if PARK_FACILITIES.get(p[0], {}).get("difficulty") == "쉬움"]
                start = random.choice(easy_parks) if easy_parks else random.choice(HANGANG_PARKS)
            else:
                start = random.choice(HANGANG_PARKS)

        # 나머지 경유지: 공원 + 랜드마크 전체에서 랜덤 선택
        remaining = [s for s in HANGANG_SPOTS if s != start]
        random.shuffle(remaining)
        waypoints = [start] + remaining[:point_count - 1]
        random.shuffle(waypoints[1:])  # 출발지 고정, 경유 순서만 셔플

        route_points = [(s[1], s[2]) for s in waypoints]
        if route_mode == "왕복":
            route_points.append((waypoints[0][1], waypoints[0][2]))

        # 대략적인 거리 사전 체크
        rough_km = sum(
            haversine_km(route_points[i][0], route_points[i][1],
                         route_points[i+1][0], route_points[i+1][1])
            for i in range(len(route_points) - 1)
        )
        if rough_km < target_km * 0.4 or rough_km > target_km * 2.0:
            continue

        dist_m, line = osrm_route(route_points)
        if dist_m is None:
            continue

        diff = abs(dist_m - target_m)
        if diff < best_diff:
            best_diff = diff
            best = {"dist_m": dist_m, "line": line, "spots": waypoints}

        if diff <= target_m * tolerance_ratio:
            break

    return best


# ──────────────────────────────────────────────────────────
# 지도
# ──────────────────────────────────────────────────────────
def build_map(result=None, extra_pois=None):
    m = folium.Map(location=list(HANGANG_CENTER), zoom_start=12, tiles="CartoDB positron")
    if result:
        latlon_line = [(lat, lon) for lon, lat in result["line"]]
        folium.PolyLine(latlon_line, color="red", weight=6, opacity=0.9).add_to(m)
        for idx, (name, lat, lon) in enumerate(result.get("spots") or []):
            folium.CircleMarker(
                location=[lat, lon],
                radius=7 if idx == 0 else 5,
                color="#10b981" if idx == 0 else "#3b82f6",
                fill=True,
                fill_opacity=0.9,
                popup=name,
            ).add_to(m)
    else:
        for name, lat, lon in HANGANG_PARKS:
            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color="gray",
                fill=True,
                fill_opacity=0.6,
                popup=name,
            ).add_to(m)
    for poi in extra_pois or []:
        try:
            folium.Marker(
                location=[poi["lat"], poi["lon"]],
                popup=poi.get("label") or poi.get("type") or "POI",
                icon=folium.Icon(color=poi.get("color") or "purple", icon="info-sign"),
            ).add_to(m)
        except Exception:
            pass
    return m


def overpass_search_pois(center_lat, center_lon, radius_m, categories):
    cat_to_queries = {
        "편의점": ['node["shop"="convenience"]'],
        "화장실": ['node["amenity"="toilets"]'],
        "지하철": ['node["railway"="station"]["station"="subway"]', 'node["public_transport"="station"]["subway"="yes"]'],
        "카페": ['node["amenity"="cafe"]'],
        "물(음수대)": ['node["amenity"="drinking_water"]'],
    }
    selected = []
    for c in categories or []:
        selected.extend(cat_to_queries.get(c, []))
    if not selected:
        return []

    query_parts = []
    for q in selected:
        query_parts.append(f'{q}(around:{int(radius_m)},{center_lat},{center_lon});')
    ql = f"""
    [out:json][timeout:10];
    (
      {"".join(query_parts)}
    );
    out 40;
    """
    try:
        r = requests.post("https://overpass-api.de/api/interpreter", data=ql.encode("utf-8"), timeout=12)
        r.raise_for_status()
        data = r.json()
        pois = []
        for el in data.get("elements", []):
            lat, lon = el.get("lat"), el.get("lon")
            tags = el.get("tags") or {}
            name = tags.get("name") or tags.get("brand") or tags.get("operator") or "이름 없음"
            poi_type = tags.get("amenity") or tags.get("shop") or tags.get("railway") or "poi"
            pois.append({
                "lat": lat,
                "lon": lon,
                "label": f"{name} ({poi_type})",
                "type": poi_type,
                "color": "purple",
            })
        return [p for p in pois if p.get("lat") and p.get("lon")]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────
# 통계 유틸
# ──────────────────────────────────────────────────────────
def calc_streak(history):
    if not history:
        return 0, 0
    run_dates = set()
    for h in history:
        try:
            dt = datetime.strptime(h["saved_at"], "%Y-%m-%d %H:%M:%S")
            run_dates.add(dt.date())
        except Exception:
            pass
    if not run_dates:
        return 0, 0
    today = datetime.now().date()
    current_streak = 0
    check = today
    while check in run_dates:
        current_streak += 1
        check -= timedelta(days=1)
    if current_streak == 0:
        check = today - timedelta(days=1)
        while check in run_dates:
            current_streak += 1
            check -= timedelta(days=1)
    sorted_dates = sorted(run_dates, reverse=True)
    best_streak, temp = 1, 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i-1] - sorted_dates[i]).days == 1:
            temp += 1
            best_streak = max(best_streak, temp)
        else:
            temp = 1
    return current_streak, best_streak


def this_month_dist(history):
    now = datetime.now()
    total = 0.0
    for h in history:
        try:
            dt = datetime.strptime(h["saved_at"], "%Y-%m-%d %H:%M:%S")
            if dt.year == now.year and dt.month == now.month:
                total += h.get("distance_km", 0)
        except Exception:
            pass
    return round(total, 2)


def analyze_weather_pace(history):
    category_paces = defaultdict(list)
    for h in history:
        p = pace_to_minutes(h.get("pace", ""))
        snap = h.get("weather_snapshot", {})
        if p and snap:
            cat = weather_category(snap.get("temperature"), snap.get("pm25"), snap.get("wcode"))
            category_paces[cat].append(p)
    return {cat: sum(paces) / len(paces) for cat, paces in category_paces.items()}


def group_history_by_date(history):
    """saved_at 기준 YYYY-MM-DD 그룹 (최신 날짜가 먼저 오도록 키 정렬용으로만 사용)"""
    date_groups = OrderedDict()
    for item in history:
        try:
            date_key = item["saved_at"][:10]
            if date_key not in date_groups:
                date_groups[date_key] = []
            date_groups[date_key].append(item)
        except Exception:
            pass
    return date_groups


def build_chart_data(history):
    if not history:
        return None
    total_dist = sum(h.get("distance_km", 0) for h in history)
    total_cal = sum(h.get("calories_kcal", 0) for h in history)
    weekly = defaultdict(float)
    for h in history:
        try:
            dt = datetime.strptime(h["saved_at"], "%Y-%m-%d %H:%M:%S")
            weekly[dt.strftime("%m/%d")] += h.get("distance_km", 0)
        except Exception:
            pass
    sorted_weeks = sorted(weekly.items())[-8:]
    paces, dates = [], []
    for h in reversed(history[-10:]):
        p = pace_to_minutes(h.get("pace", ""))
        if p:
            paces.append(p)
            dates.append(h["saved_at"][:10])
    return {
        "total_dist": total_dist, "total_cal": total_cal, "run_count": len(history),
        "week_labels": [w[0] for w in sorted_weeks],
        "week_vals": [w[1] for w in sorted_weeks],
        "pace_dates": dates, "pace_vals": paces,
    }


# ──────────────────────────────────────────────────────────
# 세션 초기화
# ──────────────────────────────────────────────────────────
for k, v in [
    ("user", None),
    ("seed", 0),
    ("last_result", None),
    ("saved_last", False),
    ("show_register", False),
    ("post_register_toast", False),
    ("route_pois", []),
    ("last_share_token", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════
# 로그인 화면
# ══════════════════════════════════════════════════════════
if not st.session_state["user"]:
    st.title("🏃 한강 러닝 루트 추천")
    st.write("로그인 후 이용할 수 있습니다.")

    if st.session_state.get("post_register_toast"):
        st.toast("가입이 완료되었습니다. 로그인해주세요.", icon="✅")
        st.session_state["post_register_toast"] = False

    if not st.session_state["show_register"]:
        # 로그인
        st.subheader("로그인")
        login_id = st.text_input("아이디", key="login_id")
        login_pw = st.text_input("비밀번호", type="password", key="login_pw")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("로그인", type="primary", use_container_width=True):
                ok, msg = login_user(login_id, login_pw)
                if ok:
                    st.session_state["user"] = login_id
                    st.rerun()
                else:
                    st.error(msg)
        with col2:
            if st.button("회원가입하기", use_container_width=True):
                st.session_state["show_register"] = True
                st.rerun()
    else:
        # 회원가입
        st.subheader("회원가입")
        reg_id = st.text_input("아이디 (2자 이상)", key="reg_id")
        reg_pw = st.text_input("비밀번호 (4자 이상)", type="password", key="reg_pw")
        reg_pw2 = st.text_input("비밀번호 확인", type="password", key="reg_pw2")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("가입하기", type="primary", use_container_width=True):
                if reg_pw != reg_pw2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    ok, msg = register_user(reg_id, reg_pw)
                    if ok:
                        st.success(msg)
                        st.session_state["post_register_toast"] = True
                        st.session_state["show_register"] = False
                        st.rerun()
                    else:
                        st.error(msg)
        with col2:
            if st.button("로그인으로 돌아가기", use_container_width=True):
                st.session_state["show_register"] = False
                st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════
# 로그인 후 메인 앱
# ══════════════════════════════════════════════════════════
username = st.session_state["user"]

# 상단 헤더
header_col, logout_col = st.columns([5, 1])
with header_col:
    st.title("🏃 한강 러닝 루트 추천")
with logout_col:
    st.write("")
    st.write(f"👤 **{username}**")
    if st.button("로그아웃", use_container_width=True):
        st.session_state["user"] = None
        st.session_state["last_result"] = None
        st.session_state["saved_last"] = False
        st.rerun()

# 현재 날씨
weather = get_current_weather()
if weather["recommend"] is True:
    st.success(weather["message"])
elif weather["recommend"] is False:
    st.warning(weather["message"])
else:
    st.info(weather["message"])

w1, w2, w3, w4 = st.columns(4)
with w1:
    if weather["temperature"] is not None:
        st.metric("현재 기온", f"{weather['temperature']:.1f}°C")
with w2:
    if weather["pm10"] is not None:
        st.metric("PM10", f"{weather['pm10']:.0f} µg/m³")
with w3:
    if weather["pm25"] is not None:
        st.metric("PM2.5", f"{weather['pm25']:.0f} µg/m³")
with w4:
    if weather["precipitation"] is not None:
        st.metric("강수", f"{weather['precipitation']:.1f} mm")

# ──────────────────────────────────────────────────────────
# 탭
# ──────────────────────────────────────────────────────────
tab_route, tab_weather, tab_journal, tab_mates, tab_stats, tab_favs = st.tabs([
    "🗺️ 루트 추천", "🌤️ 7일 예보", "📓 러닝 기록", "🤝 러닝 메이트", "📊 나의 통계", "⭐ 즐겨찾기",
])

# ════════════════════════════════════════════════════════
# 탭 1: 루트 추천
# ════════════════════════════════════════════════════════
with tab_route:
    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("루트 추천")
        target_km = st.number_input("목표 거리 (km)", 2.0, 30.0, 8.0, 0.5, key="target_km")
        route_mode = st.radio("루트 형태", ["왕복", "편도"], horizontal=True)
        tolerance_pct = st.slider("거리 허용 오차 (%)", 3, 15, 8, 1)
        user_level = st.selectbox("러닝 레벨", ["초급", "중급", "고급"])
        condition_level = st.selectbox("오늘 컨디션", ["좋음", "보통", "나쁨"], index=1)
        condition_note = st.text_input("컨디션 메모 (선택)", placeholder="예: 다리가 무겁다 / 바람이 많이 분다")
        departure_time = st.time_input("출발 시각", value=datetime.now().time().replace(second=0, microsecond=0))
        start_park = st.selectbox("출발 공원(선택)", ["자동"] + [p[0] for p in HANGANG_PARKS])
        waypoint_count = st.slider("경유 지점 수(많이 늘리기)", 2, 10, 6)

        base = {"초급": (3, 5), "중급": (5, 8), "고급": (8, 12)}[user_level]
        suggest = round(random.uniform(*base), 1)
        if condition_level == "나쁨":
            suggest = max(2.0, round(suggest * 0.75, 1))
        elif condition_level == "좋음":
            suggest = min(30.0, round(suggest * 1.05, 1))
        st.caption(f"오늘의 추천 거리: 약 {suggest} km")

        if weather.get("recommend") is False:
            st.info("실외 러닝이 부담스러우면 실내 대안을 고려해보세요.")
            st.write("• " + random.choice(INDOOR_ALTERNATIVES))

        if st.button("🎲 루트 생성", type="primary"):
            with st.spinner("다양한 루트 조합 중..."):
                st.session_state["seed"] += 1
                st.session_state["route_pois"] = []
                st.session_state["last_result"] = generate_random_route(
                    target_km=target_km,
                    route_mode=route_mode,
                    tolerance_ratio=tolerance_pct / 100.0,
                    max_try=30,
                    start_hint=None if start_park == "자동" else start_park,
                    departure_time_str=departure_time.strftime("%H:%M"),
                    condition_level=condition_level,
                    waypoint_count=waypoint_count,
                )
                st.session_state["saved_last"] = False

    with right:
        st.subheader("운동 계산기")
        weight_kg = st.number_input("체중 (kg)", 30.0, 150.0, 65.0, 0.5)
        target_time = st.number_input("목표 시간 (분)", 10, 300, 48, 1)
        pace_val = target_time / target_km if target_km > 0 else None
        calories = estimate_calories(weight_kg, target_km)
        c1, c2 = st.columns(2)
        c1.metric("예상 페이스", pace_to_string(pace_val))
        c2.metric("예상 소모 칼로리", f"{calories} kcal")

    result = st.session_state["last_result"]
    st.divider()

    map_col, info_col = st.columns([1.8, 1])
    with map_col:
        route_map = build_map(result, extra_pois=st.session_state.get("route_pois") or [])
        st.markdown(
            '<div class="hangang-folium-marker"></div>',
            unsafe_allow_html=True,
        )
        mobile_mode = st.toggle("모바일 지도(축소)", value=True)
        st_folium(
            route_map,
            width=1100,
            height=380 if mobile_mode else 650,
            returned_objects=[],
        )

    with info_col:
        st.subheader("추천 결과")
        if result:
            actual_km = result["dist_m"] / 1000
            st.success(f"추천 루트: 약 {actual_km:.2f} km")

            if pace_val:
                st.write(f"⏱️ 예상 완주: 약 {int(round(actual_km * pace_val))}분")

            st.divider()
            st.subheader("🧭 주변 편의시설 검색 (지도 핀)")
            poi_types = st.multiselect(
                "검색할 시설",
                ["편의점", "화장실", "지하철", "카페", "물(음수대)"],
                default=["편의점", "화장실", "지하철"],
            )
            poi_radius = st.slider("검색 반경 (m)", 200, 2500, 800, 100)
            if st.button("🔎 주변 시설 검색", use_container_width=True):
                base_lat, base_lon = HANGANG_CENTER
                try:
                    if result.get("spots"):
                        base_lat, base_lon = result["spots"][0][1], result["spots"][0][2]
                except Exception:
                    pass
                with st.spinner("주변 시설을 찾는 중..."):
                    pois = overpass_search_pois(base_lat, base_lon, poi_radius, poi_types)
                st.session_state["route_pois"] = pois
                if pois:
                    st.success(f"{len(pois)}개 시설을 지도에 표시했습니다.")
                else:
                    st.info("검색 결과가 없거나, 잠시 후 다시 시도해 주세요.")

            st.divider()
            st.subheader("기록 저장")
            run_memo = st.text_input(
                "한 줄 메모 (선택)",
                placeholder="예: 컨디션 최상 / 바람이 시원했음",
                key="run_memo",
            )
            wlabel, wicon = wmo_label(weather.get("wcode"))
            st.caption(
                f"저장 시 날씨 자동 기록: {wicon} {wlabel} "
                f"/ {weather.get('temperature', '-')}°C "
                f"/ PM2.5 {weather.get('pm25', '-')} µg/m³"
            )

            col_save, col_fav = st.columns(2)
            with col_save:
                if st.button("✅ 기록 저장", type="primary"):
                    save_history(username, {
                        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "route_mode": route_mode,
                        "distance_km": round(actual_km, 2),
                        "spots": [s[0] for s in result["spots"]],
                        "pace": pace_to_string(pace_val),
                        "calories_kcal": estimate_calories(weight_kg, actual_km),
                        "memo": run_memo.strip(),
                        "condition": {
                            "level": condition_level,
                            "note": condition_note.strip(),
                            "departure_time": departure_time.strftime("%H:%M"),
                            "start_park": None if start_park == "자동" else start_park,
                            "waypoint_count": int(waypoint_count),
                        },
                        "weather_snapshot": {
                            "temperature": weather.get("temperature"),
                            "pm25": weather.get("pm25"),
                            "pm10": weather.get("pm10"),
                            "precipitation": weather.get("precipitation"),
                            "wcode": weather.get("wcode"),
                            "weather_label": wlabel,
                            "weather_icon": wicon,
                        },
                    })
                    st.session_state["saved_last"] = True
                    st.rerun()

            with col_fav:
                fav_name = st.text_input("즐겨찾기 이름", placeholder="예: 반포→잠실")
                if st.button("⭐ 즐겨찾기 저장"):
                    if fav_name.strip():
                        save_favorite(username, {
                            "name": fav_name.strip(),
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "route_mode": route_mode,
                            "distance_km": round(actual_km, 2),
                            "spots": [s[0] for s in result["spots"]],
                        })
                        st.success("즐겨찾기에 저장했습니다!")
                    else:
                        st.warning("이름을 입력해주세요.")

            if st.session_state["saved_last"]:
                st.success("기록이 저장되었습니다!")
        else:
            st.info("왼쪽에서 조건을 설정하고 '루트 생성'을 눌러보세요.")

    st.caption("저장한 러닝은 **📓 러닝 기록** 탭 달력에서 날짜별로 확인할 수 있습니다.")
    st.caption("공개 경로 서버 응답이 느릴 경우 결과가 다소 늦게 나올 수 있습니다.")


# ════════════════════════════════════════════════════════
# 탭 2: 7일 날씨 예보
# ════════════════════════════════════════════════════════
with tab_weather:
    st.subheader("🌤️ 한강 기준 7일 러닝 날씨 예보")
    with st.spinner("날씨 예보 불러오는 중..."):
        forecast = get_7day_forecast()

    if not forecast:
        st.error("날씨 예보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        best_days = []
        cols = st.columns(7)
        for i, (date, tmax, tmin, prec, wcode) in enumerate(forecast):
            label, icon = wmo_label(wcode)
            good = is_good_running_day(tmax, tmin, prec, wcode)
            if good:
                best_days.append(date)
            day_dt = datetime.strptime(date, "%Y-%m-%d")
            day_label = day_dt.strftime("%m/%d")
            weekday = ["월","화","수","목","금","토","일"][day_dt.weekday()]
            with cols[i]:
                border_color = "#1D9E75" if good else "#ccc"
                bg_color = "#E1F5EE" if good else "transparent"
                st.markdown(
                    f"<div style='border:2px solid {border_color};border-radius:10px;"
                    f"padding:8px 4px;text-align:center;background:{bg_color}'>"
                    f"<div style='font-size:11px;color:#555'>{day_label} ({weekday})</div>"
                    f"<div style='font-size:22px'>{icon}</div>"
                    f"<div style='font-size:11px'>{label}</div>"
                    f"<div style='font-size:12px;font-weight:600'>"
                    f"{int(tmax) if tmax else '-'}° / {int(tmin) if tmin else '-'}°</div>"
                    f"<div style='font-size:11px;color:#378ADD'>💧 {prec:.1f}mm</div>"
                    f"{'<div style=\"font-size:10px;color:#0F6E56;font-weight:600\">✓ 추천</div>' if good else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        if best_days:
            best_strs = [datetime.strptime(d, "%Y-%m-%d").strftime("%m/%d(%a)") for d in best_days[:3]]
            st.success(f"이번 주 러닝 추천 날: {', '.join(best_strs)}")
        else:
            st.warning("이번 주는 러닝하기 좋은 날씨가 많지 않습니다.")

        st.divider()
        dates_str = [datetime.strptime(d[0], "%Y-%m-%d").strftime("%m/%d") for d in forecast]

        fig_wt = go.Figure()
        fig_wt.add_trace(go.Scatter(
            x=dates_str, y=[d[1] for d in forecast],
            mode="lines+markers", name="최고 기온",
            line=dict(color="#D85A30", width=2),
        ))
        fig_wt.add_trace(go.Scatter(
            x=dates_str, y=[d[2] for d in forecast],
            mode="lines+markers", name="최저 기온",
            line=dict(color="#378ADD", width=2),
        ))
        fig_wt.add_hrect(
            y0=-5, y1=32, fillcolor="#E1F5EE", opacity=0.15,
            annotation_text="러닝 적정 기온", annotation_position="top left",
        )
        fig_wt.update_layout(
            title="7일 기온 추이", yaxis_title="기온 (°C)",
            plot_bgcolor="white", paper_bgcolor="white", height=300,
        )
        st.plotly_chart(fig_wt, use_container_width=True)

        fig_pr = go.Figure(go.Bar(
            x=dates_str, y=[d[3] for d in forecast],
            marker_color=["#D85A30" if (d[3] or 0) > 2 else "#85B7EB" for d in forecast],
            text=[f"{d[3]:.1f}mm" for d in forecast], textposition="outside",
        ))
        fig_pr.update_layout(
            title="일별 강수량", yaxis_title="강수 (mm)",
            plot_bgcolor="white", paper_bgcolor="white", height=260,
        )
        st.plotly_chart(fig_pr, use_container_width=True)


# ════════════════════════════════════════════════════════
# 탭 3: 러닝 기록 (달력 + 날짜별 기록)
# ════════════════════════════════════════════════════════
with tab_journal:
    st.session_state.setdefault("cal_y", datetime.now().year)
    st.session_state.setdefault("cal_m", datetime.now().month)
    st.session_state.setdefault("cal_selected", datetime.now().date().isoformat())

    history_j = load_history(username)
    by_date = group_history_by_date(history_j)

    cy, cm = int(st.session_state["cal_y"]), int(st.session_state["cal_m"])
    try:
        sel_d = datetime.strptime(st.session_state["cal_selected"], "%Y-%m-%d").date()
    except Exception:
        sel_d = datetime.now().date()
        st.session_state["cal_selected"] = sel_d.isoformat()

    month_total = 0.0
    month_runs = 0
    for dk, runs in by_date.items():
        try:
            y, m, _ = int(dk[:4]), int(dk[5:7]), int(dk[8:10])
            if y == cy and m == cm:
                month_total += sum(r.get("distance_km", 0) for r in runs)
                month_runs += len(runs)
        except Exception:
            pass

    st.markdown(
        """
        <div class="rj-hero">
            <h2>📓 러닝 저널</h2>
            <p>달력에서 날짜를 눌러 그날의 기록을 보고, 과거 날짜에도 수동으로 러닝을 남길 수 있어요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("이번 달 (달력)", f"{month_total:.1f} km")
    with m2:
        st.metric("이번 달 러닝 횟수", f"{month_runs}회")
    with m3:
        st.metric("저장된 기록", f"{len(history_j)}건")
    with m4:
        streak_now, _ = calc_streak(history_j)
        st.metric("연속 러닝", f"{streak_now}일")

    st.markdown('<div class="rj-cal-wrap">', unsafe_allow_html=True)
    nav_l, nav_c, nav_r = st.columns([1, 4, 1])
    with nav_l:
        if st.button("◀ 이전 달", key="cal_prev", use_container_width=True):
            if cm == 1:
                st.session_state["cal_y"] = cy - 1
                st.session_state["cal_m"] = 12
            else:
                st.session_state["cal_m"] = cm - 1
            st.rerun()
    with nav_c:
        st.markdown(
            f"<div style='text-align:center;font-weight:700;font-size:1.15rem;"
            f"color:#0f172a;padding:0.35rem 0;'>{cy}년 {cm}월</div>",
            unsafe_allow_html=True,
        )
    with nav_r:
        if st.button("다음 달 ▶", key="cal_next", use_container_width=True):
            if cm == 12:
                st.session_state["cal_y"] = cy + 1
                st.session_state["cal_m"] = 1
            else:
                st.session_state["cal_m"] = cm + 1
            st.rerun()

    weekday_labels = ["일", "월", "화", "수", "목", "금", "토"]
    hcols = st.columns(7)
    for i, wn in enumerate(weekday_labels):
        with hcols[i]:
            st.markdown(
                f"<div class='rj-day-head'>{wn}</div>",
                unsafe_allow_html=True,
            )

    cal_obj = calendar.Calendar(firstweekday=6)
    weeks = cal_obj.monthdatescalendar(cy, cm)

    for week in weeks:
        cols = st.columns(7)
        for i, d in enumerate(week):
            with cols[i]:
                if d.month != cm:
                    st.markdown(
                        "<div style='min-height:3.2rem'></div>",
                        unsafe_allow_html=True,
                    )
                    continue
                day_key = d.isoformat()
                day_runs = by_date.get(day_key, [])
                km_d = sum(r.get("distance_km", 0) for r in day_runs)
                is_today = d == datetime.now().date()
                is_sel = day_key == st.session_state["cal_selected"]
                btn_label = f"{d.day}"
                if km_d > 0:
                    btn_label = f"{d.day}\n·{km_d:.1f}km"
                help_txt = (
                    f"{len(day_runs)}회 · {km_d:.1f} km"
                    if day_runs
                    else "기록 없음"
                )
                if st.button(
                    btn_label,
                    key=f"pick_{day_key}",
                    use_container_width=True,
                    type="primary" if is_sel else "secondary",
                    help=help_txt,
                ):
                    st.session_state["cal_selected"] = day_key
                    st.rerun()
                if is_today:
                    st.caption("오늘")

    st.markdown("</div>", unsafe_allow_html=True)

    sel_iso = st.session_state["cal_selected"]
    try:
        sel_dt = datetime.strptime(sel_iso, "%Y-%m-%d")
        wdx = ["월", "화", "수", "목", "금", "토", "일"][sel_dt.weekday()]
        sel_title = sel_dt.strftime(f"%Y년 %m월 %d일 ({wdx})")
    except Exception:
        sel_title = sel_iso

    st.markdown(f"### 📌 {sel_title}")

    runs_day = sorted(
        by_date.get(sel_iso, []),
        key=lambda x: x.get("saved_at", ""),
        reverse=True,
    )

    if runs_day:
        for item in runs_day:
            snap = item.get("weather_snapshot") or {}
            spots = item.get("spots") or []
            spots_txt = " → ".join(spots) if spots else "—"
            w_badge = ""
            if snap:
                w_badge = (
                    f"{snap.get('weather_icon', '')} {snap.get('weather_label', '')} "
                    f"{snap.get('temperature', '-')}°C"
                )
            memo_safe = html.escape(str(item.get("memo", "")))
            with st.container():
                st.markdown(
                    f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;"
                    f"padding:0.9rem 1rem;margin-bottom:0.65rem;"
                    f"box-shadow:0 4px 14px rgba(15,23,42,0.06);'>"
                    f"<div style='font-size:0.8rem;color:#64748b;margin-bottom:0.35rem;'>"
                    f"{html.escape(str(item.get('saved_at', '')))}</div>"
                    f"<div style='font-weight:700;font-size:1.05rem;color:#0f172a;'>"
                    f"{html.escape(str(item.get('route_mode', '-')))} · "
                    f"{html.escape(str(item.get('distance_km', '-')))} km · "
                    f"{html.escape(str(item.get('pace', '-')))} · "
                    f"{html.escape(str(item.get('calories_kcal', '-')))} kcal</div>"
                    f"<div style='margin-top:0.35rem;color:#334155;font-size:0.9rem;'>"
                    f"📍 {html.escape(spots_txt)}</div>"
                    + (
                        f"<div style='margin-top:0.25rem;font-size:0.85rem;'>"
                        f"{html.escape(w_badge)}</div>"
                        if w_badge
                        else ""
                    )
                    + (
                        f"<div style='margin-top:0.45rem;padding:0.45rem 0.6rem;"
                        f"background:#f0fdfa;border-radius:8px;font-size:0.88rem;'>"
                        f"💬 {memo_safe}</div>"
                        if item.get("memo")
                        else ""
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
                b1, b2 = st.columns([1, 1])
                with b1:
                    if st.button(
                        "📤 공유 카드 만들기",
                        key=f"share_{username}_{item.get('saved_at','')}",
                        use_container_width=True,
                    ):
                        token = upsert_share(username, item)
                        st.session_state["last_share_token"] = token
                        if token:
                            st.toast("공유 카드가 생성되었습니다.", icon="✅")
                        else:
                            st.error("공유 카드 생성에 실패했습니다.")
                with b2:
                    friends = load_friends(username)
                    can_send = bool(friends)
                    send_to = st.selectbox(
                        "친구에게 보내기",
                        ["선택 안 함"] + friends,
                        key=f"send_to_{username}_{item.get('saved_at','')}",
                        disabled=not can_send,
                        label_visibility="collapsed",
                    )
                    if st.button(
                        "🤝 친구에게 공유",
                        key=f"send_{username}_{item.get('saved_at','')}",
                        use_container_width=True,
                        disabled=(not can_send or send_to == "선택 안 함"),
                    ):
                        token = upsert_share(username, item)
                        if token:
                            push_inbox(
                                send_to,
                                {
                                    "type": "share",
                                    "from": username,
                                    "to": send_to,
                                    "sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "token": token,
                                },
                            )
                            st.success(f"{send_to}님에게 공유를 보냈습니다. (코드: {token})")
                        else:
                            st.error("공유 생성에 실패했습니다.")
    else:
        st.info("선택한 날짜에 저장된 러닝이 없어요. 아래에서 새 기록을 추가해 보세요.")

    st.divider()
    st.subheader("📤 공유 카드 보기")
    st.caption("공유 코드를 입력하면, 러닝 기록 공유 카드를 바로 볼 수 있어요.")
    share_code = st.text_input(
        "공유 코드",
        value=(st.session_state.get("last_share_token") or ""),
        placeholder="예: a1b2c3d4e5f6",
    )
    if share_code.strip():
        shares = load_shares()
        shared = shares.get(share_code.strip())
        if not shared:
            st.error("해당 공유 코드를 찾을 수 없습니다.")
        else:
            render_share_card(
                shared.get("owner", "unknown"),
                shared.get("run") or {},
                shared.get("token", share_code.strip()),
            )

    with st.expander("✏️ 이 날짜에 러닝 기록 추가 (수동)", expanded=not runs_day):
        st.caption("실제로 달린 날·거리를 남기거나, 루트 탭 저장 전 기록을 보완할 때 사용하세요.")
        with st.form("manual_run_entry", clear_on_submit=True):
            c_date, c_time = st.columns(2)
            with c_date:
                picked = st.date_input(
                    "날짜",
                    value=sel_d,
                    key="manual_run_date",
                )
            with c_time:
                run_time = st.time_input(
                    "시각",
                    value=dt_time(12, 0),
                )
            dist_f = st.number_input("거리 (km)", 0.1, 100.0, 5.0, 0.1)
            mode_f = st.radio("형태", ["편도", "왕복"], horizontal=True)
            pace_f = st.text_input("페이스 (선택)", placeholder="예: 5:30/km")
            weight_f = st.number_input("체중 (kcal 계산)", 30.0, 150.0, 65.0, 0.5)
            memo_f = st.text_input("메모 (선택)")
            submitted = st.form_submit_button("기록 추가", type="primary")

        if submitted:
            raw_pace = pace_f.strip()
            p_str = "-"
            pace_ok = True
            if raw_pace:
                pm = pace_to_minutes(raw_pace)
                if pm is None:
                    st.error("페이스 형식을 확인해 주세요. (예: 5:30 또는 5:30/km)")
                    pace_ok = False
                else:
                    p_str = pace_to_string(pm)
            if pace_ok:
                saved_at = f"{picked.isoformat()} {run_time.hour:02d}:{run_time.minute:02d}:00"
                save_history(
                    username,
                    {
                        "saved_at": saved_at,
                        "route_mode": mode_f,
                        "distance_km": round(float(dist_f), 2),
                        "spots": [],
                        "pace": p_str,
                        "calories_kcal": estimate_calories(weight_f, float(dist_f)),
                        "memo": memo_f.strip(),
                        "weather_snapshot": {},
                        "manual_entry": True,
                    },
                )
                st.session_state["cal_selected"] = picked.isoformat()
                st.session_state["cal_y"] = picked.year
                st.session_state["cal_m"] = picked.month
                st.success("기록을 추가했습니다!")
                st.rerun()


# ════════════════════════════════════════════════════════
# 탭 4: 러닝 메이트(친구추가 & 공유함)
# ════════════════════════════════════════════════════════
with tab_mates:
    st.subheader("🤝 러닝 메이트")
    st.caption("친구(러닝 메이트)를 추가하고, 친구가 보낸 공유 코드를 확인할 수 있어요.")

    c_add, c_list = st.columns([1, 1.2])
    with c_add:
        st.markdown("### 친구 추가")
        fid = st.text_input("친구 아이디", placeholder="예: runner123", key="mate_add_id")
        if st.button("➕ 친구 추가", type="primary", use_container_width=True):
            ok, msg = add_friend(username, fid)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    with c_list:
        st.markdown("### 내 러닝 메이트")
        friends = load_friends(username)
        if not friends:
            st.info("아직 추가한 친구가 없어요.")
        else:
            for f in friends[:50]:
                st.markdown(f"- **{html.escape(str(f))}**")

    st.divider()
    st.markdown("### 📥 받은 공유")
    inbox = load_inbox(username)
    if not inbox:
        st.caption("아직 받은 공유가 없습니다.")
    else:
        for idx, msg in enumerate(inbox[:20]):
            if msg.get("type") != "share":
                continue
            token = msg.get("token", "")
            frm = msg.get("from", "")
            sent_at = msg.get("sent_at", "")
            st.markdown(
                f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;"
                f"padding:0.85rem 1rem;margin-bottom:0.6rem;"
                f"box-shadow:0 4px 14px rgba(15,23,42,0.06);'>"
                f"<div style='font-size:0.8rem;color:#64748b;margin-bottom:0.25rem;'>"
                f"{html.escape(str(sent_at))}</div>"
                f"<div style='font-weight:800;color:#0f172a;'>"
                f"📤 {html.escape(str(frm))}님이 러닝을 공유했습니다</div>"
                f"<div style='margin-top:0.35rem;'>공유 코드: "
                f"<span style='font-weight:900;letter-spacing:0.06em'>{html.escape(str(token))}</span></div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button("카드 열기", key=f"inbox_open_{idx}", use_container_width=True):
                st.session_state["last_share_token"] = token
                st.toast("공유 코드가 입력되었습니다. (📓 러닝 기록 탭에서 카드 확인)", icon="✅")


# ════════════════════════════════════════════════════════
# 탭 4: 나의 통계
# ════════════════════════════════════════════════════════
with tab_stats:
    st.subheader(f"📊 {username}님의 러닝 통계")
    history = load_history(username)
    chart_data = build_chart_data(history)

    # 스트릭
    current_streak, best_streak = calc_streak(history)
    sk1, sk2 = st.columns(2)
    with sk1:
        streak_emoji = "🔥" * min(current_streak, 5) if current_streak > 0 else "💤"
        st.metric("현재 연속 러닝", f"{current_streak}일 {streak_emoji}")
    with sk2:
        st.metric("최고 연속 기록", f"{best_streak}일 🏆")

    if current_streak >= 7:
        st.success("🎉 7일 연속 달성! 정말 대단해요!")
    elif current_streak >= 3:
        st.info(f"💪 {current_streak}일 연속 중! 계속 이어가세요!")

    st.divider()

    # 월간 목표
    goal_data = load_goal(username)
    goal_km = goal_data.get("monthly_km", 50.0)
    gc1, gc2 = st.columns([2, 1])
    with gc1:
        new_goal = st.number_input("이번 달 목표 거리 (km)", 10.0, 500.0, float(goal_km), 5.0)
        if st.button("목표 저장"):
            save_goal(username, new_goal)
            st.success(f"월간 목표 {new_goal:.0f} km 저장!")
            goal_km = new_goal
    with gc2:
        month_dist = this_month_dist(history)
        pct = min(month_dist / goal_km * 100, 100) if goal_km > 0 else 0
        st.metric("이번 달 달린 거리", f"{month_dist:.1f} km", delta=f"목표의 {pct:.0f}%")
    st.progress(max(0.0, min(pct / 100, 1.0)))
    if pct >= 100:
        st.success(f"🎉 이번 달 목표 {goal_km:.0f} km 달성!")
    else:
        st.caption(f"목표까지 {max(goal_km - month_dist, 0):.1f} km 남았습니다.")

    st.divider()

    if not chart_data:
        st.info("아직 저장된 기록이 없습니다. 루트 추천 탭에서 기록을 저장해보세요!")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("총 러닝 횟수", f"{chart_data['run_count']} 회")
        s2.metric("총 누적 거리", f"{chart_data['total_dist']:.1f} km")
        s3.metric("총 소모 칼로리", f"{chart_data['total_cal']:,} kcal")

        if len(chart_data["pace_vals"]) >= 2:
            fig_p = go.Figure(go.Scatter(
                x=chart_data["pace_dates"], y=chart_data["pace_vals"],
                mode="lines+markers", line=dict(color="#1D9E75", width=2),
                marker=dict(size=7),
                text=[pace_to_string(p) for p in chart_data["pace_vals"]],
                hovertemplate="%{x}<br>페이스: %{text}<extra></extra>",
            ))
            fig_p.update_layout(
                title="페이스 추이 (낮을수록 빠름)",
                yaxis_title="페이스 (분/km)", yaxis=dict(autorange="reversed"),
                plot_bgcolor="white", paper_bgcolor="white", height=280,
            )
            st.plotly_chart(fig_p, use_container_width=True)

        st.caption("날짜별 상세 기록은 **📓 러닝 기록** 탭에서 달력으로 확인할 수 있어요.")


# ════════════════════════════════════════════════════════
# 탭 5: 즐겨찾기
# ════════════════════════════════════════════════════════
with tab_favs:
    st.subheader("⭐ 즐겨찾기 루트")
    favs = load_favorites(username)
    if not favs:
        st.info("즐겨찾기한 루트가 없습니다. 루트 추천 탭에서 저장해보세요!")
    else:
        for i, fav in enumerate(favs):
            col_info, col_del = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**⭐ {fav['name']}**  \n"
                    f"{fav['route_mode']} / {fav['distance_km']} km  \n"
                    f"{' → '.join(fav['spots'])}  \n"
                    f"<small>{fav['saved_at']}</small>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("삭제", key=f"del_fav_{i}"):
                    delete_favorite(username, i)
                    st.rerun()
            st.divider()
