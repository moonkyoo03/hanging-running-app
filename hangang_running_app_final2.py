import hashlib
import json
import math
import os
import random
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

import folium
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────
st.set_page_config(page_title="한강 러닝 루트 추천", layout="wide")

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
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
# JSON I/O (유저별)
# ──────────────────────────────────────────────────────────
def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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


def generate_random_route(target_km, route_mode, tolerance_ratio=0.08, max_try=30):
    """공원 + 시설/랜드마크를 모두 활용한 다양한 루트 생성"""
    target_m = target_km * 1000.0
    best, best_diff = None, float("inf")

    for attempt in range(max_try):
        # 매 시도마다 시드 변경으로 다양성 확보
        random.seed(st.session_state.get("seed", 0) + attempt * 37 + int(target_km * 100))

        # 경유 지점 수 랜덤 (2~6개)
        point_count = random.randint(2, min(6, len(HANGANG_SPOTS)))

        # 출발은 반드시 공원 중에서 선택
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
def build_map(result=None):
    m = folium.Map(location=list(HANGANG_CENTER), zoom_start=12, tiles="CartoDB positron")
    if result:
        latlon_line = [(lat, lon) for lon, lat in result["line"]]
        folium.PolyLine(latlon_line, color="red", weight=6, opacity=0.9).add_to(m)
    return m


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
for k, v in [("user", None), ("seed", 0), ("last_result", None),
             ("saved_last", False), ("show_register", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════
# 로그인 화면
# ══════════════════════════════════════════════════════════
if not st.session_state["user"]:
    st.title("🏃 한강 러닝 루트 추천")
    st.write("로그인 후 이용할 수 있습니다.")

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
                        st.success(msg + " 로그인해주세요.")
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
tab_route, tab_weather, tab_stats, tab_favs = st.tabs([
    "🗺️ 루트 추천", "🌤️ 7일 예보", "📊 나의 통계", "⭐ 즐겨찾기"
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

        base = {"초급": (3, 5), "중급": (5, 8), "고급": (8, 12)}[user_level]
        suggest = round(random.uniform(*base), 1)
        st.caption(f"오늘의 추천 거리: 약 {suggest} km")

        if weather.get("recommend") is False:
            st.info("실외 러닝이 부담스러우면 실내 대안을 고려해보세요.")
            st.write("• " + random.choice(INDOOR_ALTERNATIVES))

        if st.button("🎲 루트 생성", type="primary"):
            with st.spinner("다양한 루트 조합 중..."):
                st.session_state["seed"] += 1
                st.session_state["last_result"] = generate_random_route(
                    target_km=target_km,
                    route_mode=route_mode,
                    tolerance_ratio=tolerance_pct / 100.0,
                    max_try=30,
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
        route_map = build_map(result)
        st_folium(route_map, width=1100, height=650)

    with info_col:
        st.subheader("추천 결과")
        if result:
            actual_km = result["dist_m"] / 1000
            st.success(f"추천 루트: 약 {actual_km:.2f} km")

            if pace_val:
                st.write(f"⏱️ 예상 완주: 약 {int(round(actual_km * pace_val))}분")

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

    st.divider()
    st.subheader("최근 저장 기록")
    history = load_history(username)
    if history:
        for item in history[:5]:
            snap = item.get("weather_snapshot", {})
            weather_str = (
                f" | {snap.get('weather_icon','')} {snap.get('weather_label','')} "
                f"{snap.get('temperature','-')}°C"
            ) if snap else ""
            memo_str = f"  \n💬 {item['memo']}" if item.get("memo") else ""
            st.markdown(
                f"**{item['saved_at']}** — {item['route_mode']} {item['distance_km']} km "
                f"/ {item['pace']} / {item['calories_kcal']} kcal{weather_str}  \n"
                f"{' → '.join(item['spots'])}{memo_str}"
            )
    else:
        st.caption("아직 저장된 기록이 없습니다.")
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
# 탭 3: 나의 통계
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

        # 날짜별 기록 (expander)
        st.divider()
        st.subheader("📅 날짜별 러닝 기록")

        date_groups = OrderedDict()
        for item in history:
            try:
                date_key = item["saved_at"][:10]
                if date_key not in date_groups:
                    date_groups[date_key] = []
                date_groups[date_key].append(item)
            except Exception:
                pass

        for date_key, runs in date_groups.items():
            try:
                dt = datetime.strptime(date_key, "%Y-%m-%d")
                weekday = ["월","화","수","목","금","토","일"][dt.weekday()]
                date_label = dt.strftime(f"%Y년 %m월 %d일 ({weekday})")
            except Exception:
                date_label = date_key

            total_day_km = sum(r.get("distance_km", 0) for r in runs)
            total_day_cal = sum(r.get("calories_kcal", 0) for r in runs)
            snap0 = runs[0].get("weather_snapshot", {})
            weather_badge = (
                f"{snap0.get('weather_icon','')} {snap0.get('temperature','-')}°C"
                if snap0 else ""
            )

            label = (
                f"**{date_label}**  —  "
                f"총 {total_day_km:.1f} km · {total_day_cal} kcal"
                + (f"  {weather_badge}" if weather_badge else "")
                + f"  ({len(runs)}회)"
            )

            with st.expander(label):
                for idx, item in enumerate(runs):
                    if idx > 0:
                        st.markdown("---")
                    snap = item.get("weather_snapshot", {})

                    col_a, col_b, col_c, col_d = st.columns(4)
                    col_a.metric("거리", f"{item.get('distance_km', '-')} km")
                    col_b.metric("페이스", item.get("pace", "-"))
                    col_c.metric("칼로리", f"{item.get('calories_kcal', '-')} kcal")
                    col_d.metric("형태", item.get("route_mode", "-"))

                    spots = item.get("spots", [])
                    if spots:
                        st.write("📍 경로: " + " → ".join(spots))

                    if snap:
                        st.write(
                            f"🌡️ 날씨: {snap.get('weather_icon','')} "
                            f"{snap.get('weather_label','')}  "
                            f"{snap.get('temperature','-')}°C  /  "
                            f"PM2.5 {snap.get('pm25','-')} µg/m³"
                        )

                    if item.get("memo"):
                        st.info(f"💬 {item['memo']}")

                    st.caption(f"저장 시각: {item.get('saved_at', '-')}")


# ════════════════════════════════════════════════════════
# 탭 4: 즐겨찾기
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
