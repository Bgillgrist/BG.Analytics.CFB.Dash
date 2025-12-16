import streamlit as st
import base64
from pathlib import Path

st.set_page_config(page_title="BG.Analytics CFB", layout="wide")

# --- Load logo as base64 so HTML can render it reliably ---
logo_file = Path(__file__).parent / "assets" / "logo_color.PNG"   # app/assets/logo_color.PNG
logo_bytes = logo_file.read_bytes()
logo_b64 = base64.b64encode(logo_bytes).decode("utf-8")

# --- This is all the header bar CSS styling ---
st.markdown(f"""
<style>
.brand-bar {{
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 90px;
  background: #0C2C56;
  color: white;
  display: flex;
  align-items: center;
  padding: 0 24px;
  z-index: 100000;
  box-sizing: border-box;
}}
.brand-home {{
  display: flex;
  align-items: center;
  cursor: pointer;
  width: 100%;
}}
.brand-logo {{
  height: 120px;
  width: auto;
}}
.brand-title {{
  margin: 0 auto;
  transform: translateX(-60px);
  font-size: 2.5rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  white-space: nowrap;
}}
[data-testid="stAppViewContainer"] {{
  padding-top: 90px;
}}
</style>

<div class="brand-bar">
  <div class="brand-home" onclick="window.location.href='/'">
    <img src="data:image/png;base64,{logo_b64}" class="brand-logo" />
    <div class="brand-title">College Football Dashboard</div>
  </div>
</div>
""", unsafe_allow_html=True)

pages = {
    "Single Team": [
        st.Page("pages/single_team_projections.py", title="Projections"),
        st.Page("pages/single_team_report_card.py", title="Report Card"),
    ],
}

pg = st.navigation(pages, position="top")
pg.run()