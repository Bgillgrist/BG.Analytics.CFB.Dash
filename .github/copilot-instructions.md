## Purpose
Short, actionable rules to help an AI coding assistant be productive in this Streamlit dashboard repo.

## How to run locally
- Install dependencies from `requirements.txt`.
- Run the app: `streamlit run app/app.py` (project root).
- DB connection: set `NEON_DATABASE_URL` either in Streamlit `secrets.toml` or as an environment variable.

## Big-picture architecture
- Single-process Streamlit app serving multiple pages under `app/pages/`.
- Entry point: `app/app.py` — registers pages using `st.Page(...)` and runs `st.navigation(...)`.
- UI assets: `app/assets/` (logo, images). Logo is read and embedded as base64 in the sidebar.
- Data layer: `app/utils/db.py` provides `get_engine()` and `read_df(sql, params=None)`. Use these helpers for DB access.

## Key files and patterns
- `app/app.py`: page registration, top-level styling via `st.markdown(..., unsafe_allow_html=True)`, and sidebar composition.
- `app/pages/*.py`: individual Streamlit pages. Follow existing patterns — each page defines UI, uses `st.session_state` for stepper controls, and returns figures via helper `build_fig()`.
- `app/utils/db.py`: use `read_df(sql, params)` to run queries; it caches results (`@st.cache_data`). Do not bypass the helper unless necessary.
- `app/utils/queries.py`: intended place for SQL strings; currently empty — place shared SQL snippets here.

## Coding conventions specific to this repo
- Use `st.session_state` keys deterministically (examples: `game_idx`, `post_step`) to avoid duplicate widgets across reruns.
- Use `st.cache_resource` for long-lived resources (DB engine) and `st.cache_data` for query results (see `db.py`).
- Plotting: pages build Plotly figures via `build_fig()` helpers and render them with `st.plotly_chart(fig, use_container_width=True, key=...)` — include stable `key` values.
- Styling: the project frequently injects CSS via `st.markdown(..., unsafe_allow_html=True)`; preserve this approach when modifying layout.

## DB & secrets
- Secret name: `NEON_DATABASE_URL`. Code checks Streamlit secrets first, then environment variable. Missing value raises a RuntimeError.
- Use parameterized SQL with `read_df(sql, params)` to avoid SQL injection and keep `params` mapping.

## Tests, CI, and developer workflows
- There are no tests or CI configs in the repo. Keep changes small and manually verify by running `streamlit run app/app.py`.
- For DB-related changes, provide a small local fallback or mock when possible; the app will error if `NEON_DATABASE_URL` is missing.

## What to avoid / be careful about
- Don't change the global `st.navigation(...)` pattern or page registration style without updating `app/app.py` accordingly.
- Avoid removing `@st.cache_resource` / `@st.cache_data` decorators — they are used to reduce DB calls and resource reinitialization on reruns.
- When updating pages, keep widget keys and `st.session_state` names stable to prevent duplicate widgets or lost state.

## Useful examples from the codebase
- Run command: `streamlit run app/app.py` (root).  
- DB helper usage: `df = read_df(sql, params={'team': team})` (see `app/utils/db.py`).  
- Page pattern: `build_fig()` returns a Plotly `go.Figure` and the page calls `st.plotly_chart(fig, use_container_width=True, key="posterior_story_chart")`.

## When to ask the repo owner
- If you need schema details or production DB access, ask for `NEON_DATABASE_URL` or a sanitized read-only replica.
- If you plan to change navigation or add a new top-level page group, confirm intended sidebar layout.

Feedback: If any section is unclear or you want more examples (SQL patterns, specific page workflows), tell me which area to expand.
