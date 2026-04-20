"""
Streamlit entrypoint.

Run:
  streamlit run hangang_running_app_0420.py
"""

try:
    # Streamlit은 상호작용 때마다 스크립트를 rerun합니다.
    # 단순 import는 모듈 캐시 때문에 rerun 시 앱 코드가 실행되지 않아
    # "하얀 화면"이 될 수 있어, 매번 모듈을 실행합니다.
    import runpy

    runpy.run_module("running_cal_0420", run_name="__main__")
except Exception:
    import traceback

    import streamlit as st

    st.error("앱 실행 중 오류가 발생했습니다. 아래 로그를 확인해주세요.")
    st.code(traceback.format_exc())
    st.stop()
