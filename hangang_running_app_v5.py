import json
import math
import os
import random
from datetime import datetime, timedelta
from collections import defaultdict

import folium
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

# ──────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────
st.set_page_config(page_title="한강 러닝 루트 추천 v5", layout="wide")

HANGANG_SPOTS = [
    ("여의도한강공원", 37.5271, 126.9326),
    ("반포한강공원", 37.5096, 126.9945),
    ("뚝섬한강공원", 37.5293, 127.0720),
    ("잠실한강공원", 37.5188, 127.0875),
    ("망원한강공원", 37.5555, 126.8976),
    ("이촌한강공원", 37.5226, 126.9722),
    ("난지한강공원", 37.5667, 126.8765),
]

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
REQUEST_TIMEOUT_ROUTE = 5
REQUEST_TIMEOUT_INFO = 8
HISTORY_FILE = "run_history.json"
FAVORITES_FILE = "run_favorites.json"
GOAL_FILE = "run_goal.json"

INDOOR_ALTERNATIVES = [
    "실내 트레드밀 30분 + 가벼운 스트레칭",
    "홈트 유산소 20분 + 하체 보강 10분",
    "실내 자전거 40분",
    "가벼운 코어 운동 + 걷기 대체",
]

DIFFICULTY_COLOR = {"쉬움": "🟢", "보통": "🟡", "어려움": "🔴"}

WMO_ICON = {
    0: ("맑음", "☀️"), 1: ("대체로 맑음", "🌤️"), 2: ("구름 조금", "⛅"),
    3: ("흐림", "☁️"), 45: ("안개", "🌫️"), 48: ("안개", "🌫️"),
    51: ("이슬비", "🌦️"), 53: ("이슬비", "🌦️"), 55: ("이슬비", "🌦️"),
    61: ("비", "🌧️"), 63: ("비", "🌧️"), 65: ("강한 비", "🌧️"),
    71: ("눈", "❄️"), 73: ("눈", "❄️"), 75: ("강한 눈", "❄️"),
    80: ("소나기", "🌦️"), 81: ("소나기", "🌦️"), 95: ("뇌우", "⛈️"),
}

# ──────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
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


def suggest_distance(level, weather_advice):
    base = {"초급": (3, 5), "중급": (5, 8), "고급": (8, 12)}[level]
    low, high = base
    if weather_advice.get("recommend") is False:
        high = max(low, high - 2)
    return round(random.uniform(low, high), 1)


def wmo_label(code):
    if code is None:
        return ("알 수 없음", "❓")
    return WMO_ICON.get(int(code), ("흐림", "☁️"))


def weather_category(temperature, pm25, wcode):
    """날씨 조건을 간단한 카테고리로 분류"""
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
# 지도
# ──────────────────────────────────────────────────────────
def build_map(result=None, show_facilities=False):
    m = folium.Map(location=list(HANGANG_CENTER), zoom_start=12, tiles="CartoDB positron")
    if result:
        latlon_line = [(lat, lon) for lon, lat in result["line"]]
        folium.PolyLine(latlon_line, color="red", weight=6, opacity=0.9).add_to(m)
        for idx, (name, lat, lon) in enumerate(result["spots"]):
            folium.CircleMarker(
                location=[lat, lon], radius=6,
                color="green" if idx == 0 else "blue",
                fill=True, fill_opacity=0.9, popup=name,
            ).add_to(m)
    else:
        for name, lat, lon in HANGANG_SPOTS:
            if show_facilities and name in PARK_FACILITIES:
                info = PARK_FACILITIES[name]
                popup_html = (
                    f"<b>{name}</b><br>"
                    f"난이도: {DIFFICULTY_COLOR.get(info['difficulty'],'')} {info['difficulty']}<br>"
                    f"노면: {info['surface']}<br>"
                    f"시설: {', '.join(info['facilities'])}<br>"
                    f"<i>{info['tip']}</i>"
                )
                folium.CircleMarker(
                    location=[lat, lon], radius=7,
                    color="#1D9E75", fill=True, fill_opacity=0.85,
                    popup=folium.Popup(popup_html, max_width=220),
                ).add_to(m)
            else:
                folium.CircleMarker(
                    location=[lat, lon], radius=4,
                    color="gray", fill=True, fill_opacity=0.6, popup=name,
                ).add_to(m)
    return m


# ──────────────────────────────────────────────────────────
# JSON I/O
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


def load_history():
    return _load_json(HISTORY_FILE, [])


def save_history(entry):
    h = load_history()
    h.insert(0, entry)
    _save_json(HISTORY_FILE, h[:50])


def load_favorites():
    return _load_json(FAVORITES_FILE, [])


def save_favorite(entry):
    f = load_favorites()
    f.insert(0, entry)
    _save_json(FAVORITES_FILE, f[:10])


def delete_favorite(idx):
    f = load_favorites()
    if 0 <= idx < len(f):
        f.pop(idx)
    _save_json(FAVORITES_FILE, f)


def load_goal():
    return _load_json(GOAL_FILE, {"monthly_km": 50.0})


def save_goal(goal_km):
    _save_json(GOAL_FILE, {"monthly_km": goal_km})


# ──────────────────────────────────────────────────────────
# 외부 API
# ──────────────────────────────────────────────────────────
def get_today_running_advice():
    lat, lon = HANGANG_CENTER
    advice = {
        "temperature": None, "pm10": None, "pm25": None,
        "precipitation": None, "recommend": None, "wcode": None,
        "message": "날씨/대기질 정보를 가져오지 못했습니다.",
    }
    try:
        wr = requests.get(WEATHER_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation,weathercode",
        }, timeout=REQUEST_TIMEOUT_INFO)
        wr.raise_for_status()
        weather = wr.json().get("current", {})

        ar = requests.get(AIR_QUALITY_URL, params={
            "latitude": lat, "longitude": lon, "current": "pm10,pm2_5",
        }, timeout=REQUEST_TIMEOUT_INFO)
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
        advice["message"] = ("오늘은 러닝 비추천 (" + ", ".join(reasons) + ")" if bad
                              else "오늘은 러닝 추천 👍")
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
        }, timeout=REQUEST_TIMEOUT_INFO)
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
            timeout=REQUEST_TIMEOUT_ROUTE,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None, None
        route = data["routes"][0]
        return route["distance"], route["geometry"]["coordinates"]
    except Exception:
        return None, None


def generate_random_route(target_km, route_mode, tolerance_ratio=0.08, max_try=20):
    target_m = target_km * 1000.0
    best, best_diff = None, float("inf")
    for _ in range(max_try):
        point_count = random.choice([2, 3] if route_mode == "왕복" else [2, 3, 4])
        spots = random.sample(HANGANG_SPOTS, point_count)
        route_points = [(s[1], s[2]) for s in spots]
        if route_mode == "왕복":
            route_points.append((spots[0][1], spots[0][2]))
        rough_km = sum(
            haversine_km(route_points[i][0], route_points[i][1],
                         route_points[i+1][0], route_points[i+1][1])
            for i in range(len(route_points) - 1)
        )
        if rough_km < target_km * 0.5 or rough_km > target_km * 1.7:
            continue
        dist_m, line = osrm_route(route_points)
        if dist_m is None:
            continue
        diff = abs(dist_m - target_m)
        if diff < best_diff:
            best_diff = diff
            best = {"dist_m": dist_m, "line": line, "spots": spots}
        if diff <= target_m * tolerance_ratio:
            break
    return best


# ──────────────────────────────────────────────────────────
# 심박수 Zone
# ──────────────────────────────────────────────────────────
def calc_hr_zones(age, resting_hr):
    max_hr = 220 - age
    hrr = max_hr - resting_hr
    zone_defs = [
        ("Zone 1", 0.50, 0.60, "가벼운 유산소 / 회복"),
        ("Zone 2", 0.60, 0.70, "기초 유산소 / 지방 연소"),
        ("Zone 3", 0.70, 0.80, "유산소 / 지구력 향상"),
        ("Zone 4", 0.80, 0.90, "젖산 역치 / 스피드 훈련"),
        ("Zone 5", 0.90, 1.00, "최대 노력 / 인터벌"),
    ]
    return max_hr, [(n, int(resting_hr+hrr*lo), int(resting_hr+hrr*hi), d)
                    for n, lo, hi, d in zone_defs]


# ──────────────────────────────────────────────────────────
# [NEW] 스트릭 계산
# ──────────────────────────────────────────────────────────
def calc_streak(history):
    """연속 러닝 일수 및 최고 스트릭 계산"""
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

    sorted_dates = sorted(run_dates, reverse=True)
    today = datetime.now().date()

    # 현재 스트릭
    current_streak = 0
    check = today
    while check in run_dates:
        current_streak += 1
        check -= timedelta(days=1)

    # 어제까지 이어지는 경우도 체크
    if current_streak == 0:
        check = today - timedelta(days=1)
        while check in run_dates:
            current_streak += 1
            check -= timedelta(days=1)

    # 최고 스트릭
    best_streak = 1
    temp = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i-1] - sorted_dates[i]).days == 1:
            temp += 1
            best_streak = max(best_streak, temp)
        else:
            temp = 1

    return current_streak, best_streak


# ──────────────────────────────────────────────────────────
# [NEW] 날씨 조건별 페이스 분석
# ──────────────────────────────────────────────────────────
def analyze_weather_pace(history):
    """날씨 카테고리별 평균 페이스 집계"""
    category_paces = defaultdict(list)
    for h in history:
        p = pace_to_minutes(h.get("pace", ""))
        snap = h.get("weather_snapshot", {})
        if p and snap:
            cat = weather_category(
                snap.get("temperature"),
                snap.get("pm25"),
                snap.get("wcode"),
            )
            category_paces[cat].append(p)

    result = {}
    for cat, paces in category_paces.items():
        result[cat] = sum(paces) / len(paces)
    return result


# ──────────────────────────────────────────────────────────
# 통계
# ──────────────────────────────────────────────────────────
def build_stats(history):
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


def this_month_dist(history):
    now = datetime.now()
    return round(sum(
        h.get("distance_km", 0) for h in history
        if datetime.strptime(h["saved_at"], "%Y-%m-%d %H:%M:%S").year == now.year
        and datetime.strptime(h["saved_at"], "%Y-%m-%d %H:%M:%S").month == now.month
    ), 2)


# ──────────────────────────────────────────────────────────
# 세션 상태
# ──────────────────────────────────────────────────────────
for k, v in [("seed", 0), ("last_result", None), ("saved_last", False)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────────────────────────────────
# 헤더 + 현재 날씨
# ──────────────────────────────────────────────────────────
st.title("🏃 한강 러닝 루트 추천 v5")
st.write("루트 추천 · 날씨 예보 · 심박수 Zone · 러닝 통계")

weather_advice = get_today_running_advice()
if weather_advice["recommend"] is True:
    st.success(weather_advice["message"])
elif weather_advice["recommend"] is False:
    st.warning(weather_advice["message"])
else:
    st.info(weather_advice["message"])

m1, m2, m3, m4 = st.columns(4)
with m1:
    if weather_advice["temperature"] is not None:
        st.metric("현재 기온", f"{weather_advice['temperature']:.1f}°C")
with m2:
    if weather_advice["pm10"] is not None:
        st.metric("PM10", f"{weather_advice['pm10']:.0f} µg/m³")
with m3:
    if weather_advice["pm25"] is not None:
        st.metric("PM2.5", f"{weather_advice['pm25']:.0f} µg/m³")
with m4:
    if weather_advice["precipitation"] is not None:
        st.metric("강수", f"{weather_advice['precipitation']:.1f} mm")

# ──────────────────────────────────────────────────────────
# 탭
# ──────────────────────────────────────────────────────────
tab_route, tab_weather, tab_hr, tab_stats, tab_favs = st.tabs([
    "🗺️ 루트 추천",
    "🌤️ 7일 예보",
    "❤️ 심박수 Zone",
    "📊 나의 통계",
    "⭐ 즐겨찾기",
])

# ════════════════════════════════════════════════════════
# 탭 1: 루트 추천
# ════════════════════════════════════════════════════════
with tab_route:
    left, right = st.columns([1.2, 1])

    with left:
        st.subheader("루트 추천")
        target_km = st.number_input("거리 (km)", 2.0, 30.0, 8.0, 0.5, key="target_km")
        route_mode = st.radio("루트 형태", ["왕복", "편도"], horizontal=True)
        tolerance_percent = st.slider("거리 허용 오차 (%)", 3, 15, 8, 1)
        user_level = st.selectbox("러닝 레벨", ["초급", "중급", "고급"])
        today_suggestion = suggest_distance(user_level, weather_advice)
        st.caption(f"오늘의 추천 거리: 약 {today_suggestion} km")

        if weather_advice.get("recommend") is False:
            st.info("실외 러닝이 부담스러우면 아래 실내 대안을 참고해보세요.")
            st.write("• " + random.choice(INDOOR_ALTERNATIVES))

        if st.button("루트 생성", type="primary"):
            with st.spinner("루트를 계산 중입니다..."):
                st.session_state.seed += 1
                random.seed(st.session_state.seed + int(target_km * 100))
                st.session_state.last_result = generate_random_route(
                    target_km=target_km, route_mode=route_mode,
                    tolerance_ratio=tolerance_percent / 100.0, max_try=20,
                )
                st.session_state.saved_last = False

    with right:
        st.subheader("운동 계산기")
        weight_kg = st.number_input("체중 (kg)", 30.0, 150.0, 65.0, 0.5)
        target_time_min = st.number_input("목표 시간 (분)", 10, 300, 48, 1)
        pace_value = target_time_min / target_km if target_km > 0 else None
        calories = estimate_calories(weight_kg, target_km)
        c1, c2 = st.columns(2)
        c1.metric("예상 페이스", pace_to_string(pace_value))
        c2.metric("예상 소모 칼로리", f"{calories} kcal")

    result = st.session_state.last_result
    st.divider()
    map_col, info_col = st.columns([1.8, 1])

    with map_col:
        show_fac = st.checkbox("공원 시설 정보 표시", value=False)
        route_map = build_map(result, show_facilities=(show_fac and not result))
        st_folium(route_map, width=1100, height=650)

    with info_col:
        st.subheader("추천 결과")
        if result:
            actual_km = result["dist_m"] / 1000
            st.success(f"추천 루트 거리: 약 {actual_km:.2f} km")
            st.write("경유 지점")
            for idx, spot in enumerate(result["spots"], 1):
                name = spot[0]
                diff_icon = DIFFICULTY_COLOR.get(
                    PARK_FACILITIES.get(name, {}).get("difficulty", ""), "")
                st.write(f"{idx}. {name} {diff_icon}")

            if pace_value:
                exp_min = int(round(actual_km * pace_value))
                st.write(f"예상 완주 시간: 약 {exp_min}분")

            if result["spots"]:
                first_park = result["spots"][0][0]
                if first_park in PARK_FACILITIES:
                    with st.expander(f"📍 {first_park} 시설 정보"):
                        info = PARK_FACILITIES[first_park]
                        st.write(f"난이도: {DIFFICULTY_COLOR.get(info['difficulty'],'')} {info['difficulty']}")
                        st.write(f"노면: {info['surface']}")
                        st.write("시설: " + " / ".join(info["facilities"]))
                        st.info(f"💡 {info['tip']}")

            st.divider()
            # [NEW] 기록 저장 + 날씨 스냅샷 + 메모
            st.subheader("기록 저장")
            run_memo = st.text_input(
                "오늘의 한 줄 메모 (선택)",
                placeholder="예: 무릎 살짝 불편했음 / 컨디션 최상 / 바람이 시원했음",
                key="run_memo",
            )

            # 현재 날씨 스냅샷 미리보기
            wlabel, wicon = wmo_label(weather_advice.get("wcode"))
            st.caption(
                f"저장 시 날씨 자동 기록: {wicon} {wlabel} "
                f"/ {weather_advice.get('temperature', '-')}°C "
                f"/ PM2.5 {weather_advice.get('pm25', '-')} µg/m³"
            )

            col_save, col_fav = st.columns(2)
            with col_save:
                if st.button("✅ 기록 저장", type="primary"):
                    weather_snap = {
                        "temperature": weather_advice.get("temperature"),
                        "pm25": weather_advice.get("pm25"),
                        "pm10": weather_advice.get("pm10"),
                        "precipitation": weather_advice.get("precipitation"),
                        "wcode": weather_advice.get("wcode"),
                        "weather_label": wlabel,
                        "weather_icon": wicon,
                    }
                    save_history({
                        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "route_mode": route_mode,
                        "distance_km": round(actual_km, 2),
                        "spots": [s[0] for s in result["spots"]],
                        "pace": pace_to_string(pace_value),
                        "calories_kcal": estimate_calories(weight_kg, actual_km),
                        "memo": run_memo.strip(),
                        "weather_snapshot": weather_snap,
                    })
                    st.session_state.saved_last = True
                    st.rerun()

            with col_fav:
                fav_name = st.text_input("즐겨찾기 이름", placeholder="예: 반포→잠실")
                if st.button("⭐ 즐겨찾기 저장"):
                    if fav_name.strip():
                        save_favorite({
                            "name": fav_name.strip(),
                            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "route_mode": route_mode,
                            "distance_km": round(actual_km, 2),
                            "spots": [s[0] for s in result["spots"]],
                        })
                        st.success("즐겨찾기에 저장했습니다!")
                    else:
                        st.warning("이름을 입력해주세요.")

            if st.session_state.saved_last:
                st.success("기록이 저장되었습니다!")
        else:
            st.info("왼쪽에서 조건을 설정한 뒤 '루트 생성'을 눌러보세요.")

    # 최근 기록 (날씨 + 메모 포함)
    st.divider()
    st.subheader("최근 저장 기록")
    history = load_history()
    if history:
        for item in history[:5]:
            snap = item.get("weather_snapshot", {})
            weather_str = ""
            if snap:
                weather_str = (
                    f" | {snap.get('weather_icon','')} {snap.get('weather_label','')} "
                    f"{snap.get('temperature','-')}°C "
                    f"PM2.5 {snap.get('pm25','-')}µg/m³"
                )
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
        fig_wt.add_trace(go.Scatter(x=dates_str, y=[d[1] for d in forecast],
            mode="lines+markers", name="최고 기온", line=dict(color="#D85A30", width=2)))
        fig_wt.add_trace(go.Scatter(x=dates_str, y=[d[2] for d in forecast],
            mode="lines+markers", name="최저 기온", line=dict(color="#378ADD", width=2)))
        fig_wt.add_hrect(y0=-5, y1=32, fillcolor="#E1F5EE", opacity=0.15,
                          annotation_text="러닝 적정 기온", annotation_position="top left")
        fig_wt.update_layout(yaxis_title="기온 (°C)",
            plot_bgcolor="white", paper_bgcolor="white", height=300)
        st.plotly_chart(fig_wt, use_container_width=True)

        fig_pr = go.Figure(go.Bar(
            x=dates_str, y=[d[3] for d in forecast],
            marker_color=["#D85A30" if (d[3] or 0) > 2 else "#85B7EB" for d in forecast],
            text=[f"{d[3]:.1f}mm" for d in forecast], textposition="outside",
        ))
        fig_pr.update_layout(title="일별 강수량", yaxis_title="강수 (mm)",
            plot_bgcolor="white", paper_bgcolor="white", height=260)
        st.plotly_chart(fig_pr, use_container_width=True)


# ════════════════════════════════════════════════════════
# 탭 3: 심박수 Zone
# ════════════════════════════════════════════════════════
with tab_hr:
    st.subheader("❤️ 심박수 Zone 계산기")
    hc1, hc2 = st.columns(2)
    with hc1:
        age = st.number_input("나이", 10, 80, 30, 1)
    with hc2:
        resting_hr = st.number_input("안정 시 심박수 (bpm)", 40, 100, 60, 1)
    max_hr, zones = calc_hr_zones(age, resting_hr)
    st.metric("예상 최대 심박수", f"{max_hr} bpm")
    for zname, lo, hi, desc in zones:
        zc, rc, dc = st.columns([1, 1.5, 3])
        zc.markdown(f"**{zname}**")
        rc.markdown(f"`{lo} ~ {hi} bpm`")
        dc.markdown(desc)

    zone_colors = ["#9FE1CB", "#5DCAA5", "#FAC775", "#F0997B", "#D85A30"]
    fig_hr = go.Figure()
    for i, (zname, lo, hi, desc) in enumerate(zones):
        fig_hr.add_trace(go.Bar(
            name=zname, x=[hi-lo], base=[lo], orientation="h", y=[zname],
            marker_color=zone_colors[i], text=f"{lo}~{hi} bpm", textposition="inside",
            hovertemplate=f"{zname}: {lo}~{hi} bpm<br>{desc}<extra></extra>",
        ))
    fig_hr.update_layout(barmode="stack", title="심박수 Zone 분포",
        xaxis_title="심박수 (bpm)", showlegend=False,
        plot_bgcolor="white", paper_bgcolor="white", height=320)
    st.plotly_chart(fig_hr, use_container_width=True)
    st.info("💡 기초 체력: Zone 2(60~70%) 장거리 주 3~4회 + Zone 4(80~90%) 인터벌 주 1~2회")


# ════════════════════════════════════════════════════════
# 탭 4: 나의 통계
# ════════════════════════════════════════════════════════
with tab_stats:
    st.subheader("📊 나의 러닝 통계")
    history = load_history()
    stats = build_stats(history)

    # [NEW] 연속 러닝 스트릭
    current_streak, best_streak = calc_streak(history)
    sk1, sk2 = st.columns(2)
    with sk1:
        streak_emoji = "🔥" * min(current_streak, 5) if current_streak > 0 else "💤"
        st.metric("현재 연속 러닝", f"{current_streak}일 {streak_emoji}")
    with sk2:
        st.metric("최고 연속 기록", f"{best_streak}일 🏆")

    if current_streak >= 7:
        st.success("🎉 7일 연속 달성! 꾸준함이 최고의 훈련입니다!")
    elif current_streak >= 3:
        st.info(f"💪 {current_streak}일 연속 중! 계속 이어가세요!")

    st.divider()

    # 월간 목표
    goal_data = load_goal()
    goal_km = goal_data.get("monthly_km", 50.0)
    gc1, gc2 = st.columns([2, 1])
    with gc1:
        new_goal = st.number_input("이번 달 목표 거리 (km)", 10.0, 500.0, float(goal_km), 5.0)
        if st.button("목표 저장"):
            save_goal(new_goal)
            st.success(f"월간 목표 {new_goal:.0f} km 저장!")
            goal_km = new_goal
    with gc2:
        month_dist = this_month_dist(history)
        pct = min(month_dist / goal_km * 100, 100) if goal_km > 0 else 0
        st.metric("이번 달 달린 거리", f"{month_dist:.1f} km",
                  delta=f"목표의 {pct:.0f}%")
    st.progress(pct / 100)
    remaining = max(goal_km - month_dist, 0)
    if pct >= 100:
        st.success(f"🎉 이번 달 목표 {goal_km:.0f} km 달성!")
    else:
        st.caption(f"목표까지 {remaining:.1f} km 남았습니다.")

    st.divider()

    if not stats:
        st.info("아직 저장된 기록이 없습니다. '루트 추천' 탭에서 기록을 저장해보세요!")
    else:
        s1, s2, s3 = st.columns(3)
        s1.metric("총 러닝 횟수", f"{stats['run_count']} 회")
        s2.metric("총 누적 거리", f"{stats['total_dist']:.1f} km")
        s3.metric("총 소모 칼로리", f"{stats['total_cal']:,} kcal")

        if stats["week_labels"]:
            fig_w = go.Figure(go.Bar(
                x=stats["week_labels"], y=stats["week_vals"],
                marker_color="#378ADD",
                text=[f"{v:.1f}km" for v in stats["week_vals"]],
                textposition="outside",
            ))
            fig_w.update_layout(title="날짜별 러닝 거리",
                yaxis_title="거리 (km)", plot_bgcolor="white",
                paper_bgcolor="white", height=300)
            st.plotly_chart(fig_w, use_container_width=True)

        if len(stats["pace_vals"]) >= 2:
            fig_p = go.Figure(go.Scatter(
                x=stats["pace_dates"], y=stats["pace_vals"],
                mode="lines+markers", line=dict(color="#1D9E75", width=2),
                marker=dict(size=7),
                text=[pace_to_string(p) for p in stats["pace_vals"]],
                hovertemplate="%{x}<br>페이스: %{text}<extra></extra>",
            ))
            fig_p.update_layout(title="페이스 추이 (낮을수록 빠름)",
                yaxis_title="페이스 (분/km)", yaxis=dict(autorange="reversed"),
                plot_bgcolor="white", paper_bgcolor="white", height=280)
            st.plotly_chart(fig_p, use_container_width=True)

        # [NEW] 날씨 조건별 페이스 분석
        weather_pace = analyze_weather_pace(history)
        if weather_pace:
            st.divider()
            st.subheader("🌡️ 날씨 조건별 평균 페이스")
            st.caption("기록 저장 시 자동 수집된 날씨 데이터를 기반으로 분석합니다.")

            cat_order = ["맑음/쾌청", "더운 날", "추운 날", "비/눈", "미세먼지"]
            cat_colors = {
                "맑음/쾌청": "#5DCAA5",
                "더운 날": "#D85A30",
                "추운 날": "#378ADD",
                "비/눈": "#7F77DD",
                "미세먼지": "#888780",
            }
            cats = [c for c in cat_order if c in weather_pace]
            avg_paces = [weather_pace[c] for c in cats]

            if cats:
                best_cat = min(weather_pace, key=weather_pace.get)
                st.info(f"✨ {best_cat}에 가장 빠르게 달립니다! (평균 {pace_to_string(weather_pace[best_cat])})")

                fig_wp = go.Figure(go.Bar(
                    x=cats, y=avg_paces,
                    marker_color=[cat_colors.get(c, "#888") for c in cats],
                    text=[pace_to_string(p) for p in avg_paces],
                    textposition="outside",
                ))
                fig_wp.update_layout(
                    yaxis_title="평균 페이스 (분/km)",
                    yaxis=dict(autorange="reversed"),
                    plot_bgcolor="white", paper_bgcolor="white", height=300,
                )
                st.plotly_chart(fig_wp, use_container_width=True)
        else:
            st.caption("날씨 조건별 분석은 날씨 정보가 포함된 기록이 쌓이면 표시됩니다.")

        # 전체 기록 (날씨 + 메모 포함)
        st.divider()
        st.subheader("전체 기록 목록")
        for item in history:
            snap = item.get("weather_snapshot", {})
            weather_str = ""
            if snap:
                weather_str = (
                    f" | {snap.get('weather_icon','')} {snap.get('weather_label','')} "
                    f"{snap.get('temperature','-')}°C"
                )
            memo_str = f"  \n💬 {item['memo']}" if item.get("memo") else ""
            st.markdown(
                f"**{item['saved_at']}** — {item['route_mode']} {item['distance_km']} km "
                f"/ {item['pace']} / {item['calories_kcal']} kcal{weather_str}  \n"
                f"{' → '.join(item['spots'])}{memo_str}"
            )


# ════════════════════════════════════════════════════════
# 탭 5: 즐겨찾기
# ════════════════════════════════════════════════════════
with tab_favs:
    st.subheader("⭐ 즐겨찾기 루트")
    favs = load_favorites()
    if not favs:
        st.info("즐겨찾기한 루트가 없습니다. '루트 추천' 탭에서 루트를 저장해보세요!")
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
                if st.button("삭제", key=f"del_{i}"):
                    delete_favorite(i)
                    st.rerun()
            st.divider()
