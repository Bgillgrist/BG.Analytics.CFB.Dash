import streamlit as st
import base64
from pathlib import Path

st.set_page_config(page_title="BG.Analytics CFB", layout="wide")

st.markdown("""
<style>
.top-bar {
    background-color: #0C2C56;
    color: white;
    padding: 14px 16px;
    text-align: center;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: 0.03em;
    margin-top: -2rem;
    box-shadow: 0 6px 14px rgba(0,0,0,0.25);

    border-radius: 12px;
}
</style>

<div class="top-bar">
    @BG.Analytics College Football Dashboard
</div>
""", unsafe_allow_html=True)

#Sidebar overall styling
st.markdown("""
<style>
/* Sidebar background */
[data-testid="stSidebar"] {
    background-color: #1e1e1e;
}

/* Sidebar text color */
[data-testid="stSidebar"] * {
    color: white;
}

/* Divider line color */
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.3);
}
</style>
""", unsafe_allow_html=True)

#Sidebar text size
st.markdown("""
<style>
/* Sidebar page links */
[data-testid="stSidebarNav"] span {
    font-size: 1.05rem;   /* try 1.1rem or 1.2rem */
}

/* Optional: make group headers bigger too */
[data-testid="stSidebarNav"] h2 {
    font-size: 1.1rem;
}
</style>
""", unsafe_allow_html=True)

#Page definition
pages = {
    "General": [
        st.Page("pages/home.py", title="Home"),
        st.Page("pages/metrics_explained.py", title="Metrics Explained"),
        st.Page("pages/about_me.py", title="About Me"),
    ],
    "Single Team": [
        st.Page("pages/single_team_projections.py", title="Projections"),
        st.Page("pages/single_team_report_card.py", title="Report Card"),
    ],
}

logo_path = Path(__file__).parent / "assets" / "logo_color.PNG"
logo_b64 = base64.b64encode(logo_path.read_bytes()).decode("utf-8")

#Text and imaging in the sidebar
with st.sidebar:
    st.divider()
    logo_path = Path(__file__).parent / "assets" / "logo_color.PNG"
    st.markdown(
        f"""
        <div style="text-align:center; margin-top:-60px;">
            <img src="data:image/png;base64,{logo_b64}" style="width:100%; max-width:220px;" />
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        "<div style='text-align:center; margin-top:-45px; font-size:1.2rem;'>"
        "Instagram: @BG.Analytics"
        "</div>",
        unsafe_allow_html=True
    )

pg = st.navigation(pages)  # sidebar buckets
pg.run()
