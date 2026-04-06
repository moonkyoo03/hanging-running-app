import json
import math
import os
import random
from datetime import datetime

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="한강 러닝 루트 추천 v2", layout="wide")

HANGANG_SPOTS = [
    ("여의도한강공원", 37.5271, 126.9326),
    ("반포한강공원", 37.5096, 126.9945),
    ("뚝섬한강공원", 37.5293, 127.0720),
    ("잠실한강공원", 37.5188, 127.0875),
    ("망원한강공원", 37.5555, 126.8976),
    ("이촌한강공원", 37.5226, 126.9722),
    ("난지한강공원", 37.5667, 126.8765),
]

HANGANG_CENTER = (37.53, 126.98)
OSRM_URL = "https://router.project-osrm.org/route/v1/foot"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REQUEST_TIMEOUT_ROUTE = 5
REQUEST_TIMEOUT_INFO = 6
HISTORY_FILE = "run_history.json"

INDOOR_ALTERNATIVES = [
    "실내 트레드밀 30분 + 가벼운 스트레칭",
    "홈트 유산소 20분 + 하체 보강 10분",
    "실내 자전거 40분",
    "가벼운 코어 운동 + 걷기 대체",
]

# -----------------------------
# 유틸 함수
# -----------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def pace_to_string(minutes_per_km):
    if minutes_per_km is None or minutes_per_km <= 0:
        return "-"
    total_seconds = int(round(minutes_per_km * 60))
    mm = total_seconds // 60
    ss = total_seconds % 60
    return f"{mm}:{ss:02d}/km"


def estimate_calories(weight_kg, distance_km):
    if weight_kg <= 0 or distance_km <= 0:
        return 0
    return round(weight_kg * distance_km)


def suggest_distance(level, weather_advice):
    base = {
        "초급": (3, 5),
        "중급": (5, 8),
        "고급": (8, 12),
    }[level]

    low, high = base
    if weather_advice.get("recommend") is False:
        high = max(low, high - 2)
    return round(random.uniform(low, high), 1)


def build_map(result=None):
    m = folium.Map(
        location=[HANGANG_CENTER[0], HANGANG_CENTER[1]],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    if result:
        latlon_line = [(lat, lon) for lon, lat in result["line"]]
        folium.PolyLine(
            latlon_line,
            color="red",
            weight=6,
            opacity=0.9,
        ).add_to(m)

        for idx, (name, lat, lon) in enumerate(result["spots"]):
            color = "green" if idx == 0 else "blue"
            folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color=color,
                fill=True,
                fill_opacity=0.9,
                popup=name,
            ).add_to(m)
    else:
        for name, lat, lon in HANGANG_SPOTS:
            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color="gray",
                fill=True,
                fill_opacity=0.6,
                popup=name,
            ).add_to(m)

    return m


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_history(entry):
    history = load_history()
    history.insert(0, entry)
    history = history[:20]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# -----------------------------
# 외부 API 함수
# -----------------------------
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


def get_today_running_advice():
    lat, lon = HANGANG_CENTER
    advice = {
        "temperature": None,
        "pm10": None,
        "pm25": None,
        "precipitation": None,
        "recommend": None,
        "message": "날씨/대기질 정보를 가져오지 못했습니다.",
    }

    try:
        weather_res = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,precipitation,is_day",
            },
            timeout=REQUEST_TIMEOUT_INFO,
        )
        weather_res.raise_for_status()
        weather = weather_res.json().get("current", {})

        air_res = requests.get(
            AIR_QUALITY_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "pm10,pm2_5",
            },
            timeout=REQUEST_TIMEOUT_INFO,
        )
        air_res.raise_for_status()
        air = air_res.json().get("current", {})

        temperature = weather.get("temperature_2m")
        precipitation = weather.get("precipitation", 0)
        pm10 = air.get("pm10")
        pm25 = air.get("pm2_5")

        advice.update(
            {
                "temperature": temperature,
                "pm10": pm10,
                "pm25": pm25,
                "precipitation": precipitation,
            }
        )

        is_bad = False
        reasons = []

        if temperature is not None and (temperature < -5 or temperature > 32):
            is_bad = True
            reasons.append("기온이 극단적")
        if precipitation is not None and precipitation > 0.5:
            is_bad = True
            reasons.append("비")
        if pm10 is not None and pm10 > 80:
            is_bad = True
            reasons.append("미세먼지 높음")
        if pm25 is not None and pm25 > 35:
            is_bad = True
            reasons.append("초미세먼지 높음")

        if is_bad:
            advice["recommend"] = False
            advice["message"] = "오늘은 러닝 비추천 (" + ", ".join(reasons) + ")"
        else:
            advice["recommend"] = True
            advice["message"] = "오늘은 러닝 추천 👍"
    except Exception:
        pass

    return advice


# -----------------------------
# 루트 생성
# -----------------------------
def generate_random_route(target_km, route_mode, tolerance_ratio=0.08, max_try=20):
    target_m = target_km * 1000.0
    best = None
    best_diff = float("inf")

    for _ in range(max_try):
        point_count = random.choice([2, 3] if route_mode == "왕복" else [2, 3, 4])
        spots = random.sample(HANGANG_SPOTS, point_count)

        if route_mode == "왕복":
            route_points = [(s[1], s[2]) for s in spots] + [(spots[0][1], spots[0][2])]
        else:
            route_points = [(s[1], s[2]) for s in spots]

        rough_km = 0.0
        for i in range(len(route_points) - 1):
            rough_km += haversine_km(
                route_points[i][0], route_points[i][1],
                route_points[i + 1][0], route_points[i + 1][1],
            )

        if rough_km < target_km * 0.5 or rough_km > target_km * 1.7:
            continue

        dist_m, line = osrm_route(route_points)
        if dist_m is None or line is None:
            continue

        diff = abs(dist_m - target_m)
        if diff < best_diff:
            best_diff = diff
            best = {
                "dist_m": dist_m,
                "line": line,
                "spots": spots,
            }

        if diff <= target_m * tolerance_ratio:
            break

    return best


# -----------------------------
# 세션 상태
# -----------------------------
if "seed" not in st.session_state:
    st.session_state.seed = 0
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "saved_last" not in st.session_state:
    st.session_state.saved_last = False

# -----------------------------
# 화면 UI
# -----------------------------
st.title("🏃 한강 러닝 루트 추천 v2")
st.write("루트 추천, 페이스 계산, 칼로리 계산, 기록 저장까지 한 번에 확인해보세요.")

weather_advice = get_today_running_advice()

if weather_advice["recommend"] is True:
    st.success(weather_advice["message"])
elif weather_advice["recommend"] is False:
    st.warning(weather_advice["message"])
else:
    st.info(weather_advice["message"])

metric1, metric2, metric3, metric4 = st.columns(4)
with metric1:
    if weather_advice["temperature"] is not None:
        st.metric("현재 기온", f"{weather_advice['temperature']:.1f}°C")
with metric2:
    if weather_advice["pm10"] is not None:
        st.metric("PM10", f"{weather_advice['pm10']:.0f} µg/m³")
with metric3:
    if weather_advice["pm25"] is not None:
        st.metric("PM2.5", f"{weather_advice['pm25']:.0f} µg/m³")
with metric4:
    if weather_advice["precipitation"] is not None:
        st.metric("강수", f"{weather_advice['precipitation']:.1f} mm")

left, right = st.columns([1.2, 1])

with left:
    st.subheader("루트 추천")
    target_km = st.number_input("거리 (km)", min_value=2.0, max_value=30.0, value=8.0, step=0.5)
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
                target_km=target_km,
                route_mode=route_mode,
                tolerance_ratio=tolerance_percent / 100.0,
                max_try=20,
            )
            st.session_state.saved_last = False

with right:
    st.subheader("운동 계산기")
    weight_kg = st.number_input("체중 (kg)", min_value=30.0, max_value=150.0, value=65.0, step=0.5)
    target_time_min = st.number_input("목표 시간 (분)", min_value=10, max_value=300, value=48, step=1)

    pace_value = target_time_min / target_km if target_km > 0 else None
    calories = estimate_calories(weight_kg, target_km)

    calc1, calc2 = st.columns(2)
    with calc1:
        st.metric("예상 페이스", pace_to_string(pace_value))
    with calc2:
        st.metric("예상 소모 칼로리", f"{calories} kcal")

result = st.session_state.last_result

st.divider()

map_col, info_col = st.columns([1.8, 1])
with map_col:
    if result:
        route_map = build_map(result)
    else:
        route_map = build_map()
    st_folium(route_map, width=1100, height=650)

with info_col:
    st.subheader("추천 결과")
    if result:
        actual_km = result["dist_m"] / 1000
        st.success(f"추천 루트 거리: 약 {actual_km:.2f} km")
        st.write("경유 지점")
        for idx, spot in enumerate(result["spots"], start=1):
            st.write(f"{idx}. {spot[0]}")

        expected_minutes = actual_km * pace_value if pace_value else None
        if expected_minutes:
            st.write(f"예상 완주 시간: 약 {int(round(expected_minutes))}분")

        if st.button("이번 결과 저장"):
            entry = {
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "route_mode": route_mode,
                "distance_km": round(actual_km, 2),
                "spots": [s[0] for s in result["spots"]],
                "pace": pace_to_string(pace_value),
                "calories_kcal": estimate_calories(weight_kg, actual_km),
            }
            save_history(entry)
            st.session_state.saved_last = True

        if st.session_state.saved_last:
            st.caption("최근 추천 결과를 저장했습니다.")
    else:
        st.info("왼쪽에서 조건을 설정한 뒤 '루트 생성'을 눌러보세요.")

st.divider()
st.subheader("최근 저장 기록")
history = load_history()
if history:
    for item in history[:5]:
        st.markdown(
            f"**{item['saved_at']}**  "+
            f"- {item['route_mode']} / {item['distance_km']} km / {item['pace']} / {item['calories_kcal']} kcal  "+
            f"- {' → '.join(item['spots'])}"
        )
else:
    st.caption("아직 저장된 기록이 없습니다.")

st.caption("공개 경로 서버 응답이 느릴 경우 결과가 다소 늦게 나올 수 있습니다.")
