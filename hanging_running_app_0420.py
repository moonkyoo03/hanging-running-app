"""
Streamlit entrypoint.

Run:
  streamlit run hangang_running_app_0420.py
"""

import traceback

import streamlit as st

try:
    # `running_cal_0420.py` contains the full app (UI + logic).
    # Importing it will execute the Streamlit app at module import time.
    import running_cal_0420  # noqa: F401
except Exception:
    st.error("앱 실행 중 오류가 발생했습니다. 아래 로그를 확인해주세요.")
    st.code(traceback.format_exc())
    st.stop()


