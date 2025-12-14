import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

def _get_db_url() -> str:
    # Streamlit Cloud: use st.secrets
    if "NEON_DATABASE_URL" in st.secrets:
        return st.secrets["NEON_DATABASE_URL"]

    # Local dev: use env var
    db_url = os.getenv("NEON_DATABASE_URL")
    if db_url:
        return db_url

    raise RuntimeError(
        "Missing NEON_DATABASE_URL. Set it in Streamlit secrets (cloud) or in your local environment/.env."
    )

@st.cache_resource
def get_engine():
    db_url = _get_db_url()
    # pool_pre_ping helps handle dropped connections gracefully
    return create_engine(db_url, pool_pre_ping=True)

@st.cache_data(ttl=300)
def read_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)