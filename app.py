
import io
import re
import json
from urllib.parse import urlparse
from urllib.request import urlopen

import pandas as pd
import streamlit as st

# -----------------------------
# App Config
# -----------------------------
st.set_page_config(page_title="License Search", layout="wide")

# -----------------------------
# Night mode style helper
# -----------------------------
def apply_theme():
    """Apply light/dark CSS based on st.session_state.night_mode."""
    dark_css = """
    <style>
    :root {
        --bg: #0e1117;
        --panel: #161a22;
        --text: #e6edf3;
        --muted: #9aa4b2;
        --accent: #3b82f6;
        --border: #30363d;
    }
    .stApp { background-color: var(--bg) !important; color: var(--text) !important; }
    h1, h2, h3, h4, h5, h6, .stMarkdown, .stText, .stCaption { color: var(--text) !important; }
    .st-emotion-cache-1r6slb0, .st-emotion-cache-1jicfl2, .st-emotion-cache-1v0mbdj,
    .stTextArea textarea, .stDataFrame {
        background-color: var(--panel) !important; color: var(--text) !important; border-color: var(--border) !important;
    }
    mark {
        background: #ffd54f !important; /* high-contrast amber */
        color: #000 !important;
        padding: 0 2px; border-radius: 2px;
    }
    .theme-toggle button {
        width: 42px; height: 42px; border-radius: 50%; font-size: 20px; line-height: 20px; padding: 0;
        border: 1px solid var(--border) !important;
    }
    </style>
    """
    if st.session_state.get("night_mode", False):
        st.markdown(dark_css, unsafe_allow_html=True)

# -----------------------------
# Minimal global polish (no button overrides)
# -----------------------------
def apply_global_polish():
    """Minimal CSS for section headers."""
    global_css = """
    <style>
    .section-header {
        font-size: 1.15rem; font-weight: 600; letter-spacing: 0.2px; margin-bottom: 6px;
    }
    </style>
    """
    st.markdown(global_css, unsafe_allow_html=True)

# -----------------------------
# Rotating brief (without page reload)
# -----------------------------
def render_rotating_brief():
    """A short line under the title changing every 5 seconds via JS (no page reload)."""
    messages = [
        "Find licenses by name or text and view full, highlighted content.",
        "Quickly open any license and navigate back easily with top/bottom controls.",
        "Toggle night mode for comfortable reading.",
    ]
    color = "#e6edf3" if st.session_state.get("night_mode", False) else "#374151"
    html = f"""
    <div id="brief" style="font-size:0.95rem;color:{color};opacity:0.9;">
      <span id="briefText"></span>
    </div>
    <script>
      const msgs = {json.dumps(messages)};
      let i = 0;
      function update() {{
        const el = document.getElementById('briefText');
        if (el) el.textContent = msgs[i % msgs.length];
      }}
      update();
      setInterval(() => {{ i += 1; update(); }}, 5000);
    </script>
    """
    st.html(html, unsafe_allow_javascript=True)

# -----------------------------
# Utilities
# -----------------------------
def tokenize(text: str):
    return re.findall(r"\w+", (text or "").lower())

def word_match_score(query: str, target: str) -> float:
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    if not q_tokens: return 0.0
    found = sum(1 for w in q_tokens if w in t_tokens)
    return round((found / len(q_tokens)) * 100.0, 2)

def contains_any(query: str, target: str) -> bool:
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    return any(w in t_tokens for w in q_tokens)

def highlight_text(text: str, query: str) -> str:
    if not text or not query: return text or ""
    def repl(m): return f"<mark>{m.group(0)}</mark>"
    highlighted = text
    for word in sorted(set(tokenize(query)), key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        highlighted = pattern.sub(repl, highlighted)
    return highlighted

def to_raw_url(maybe_github_url: str) -> str:
    if not maybe_github_url: return maybe_github_url
    if "github.com" in maybe_github_url and "/blob/" in maybe_github_url:
        parts = maybe_github_url.split("github.com/")[-1]
        owner_repo, _, branch_and_path = parts.partition("/blob/")
        branch, _, path = branch_and_path.partition("/")
        return f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{path}"
    return maybe_github_url

@st.cache_data(show_spinner=False)
def load_excel(source: str) -> pd.DataFrame:
    if not source:
        raise ValueError("Please provide a valid Excel path or raw URL.")
    source = to_raw_url(source.strip())
    parsed = urlparse(source)
    is_url = parsed.scheme in ("http", "https")

    if is_url:
        with urlopen(source) as resp:
            data = resp.read()
        buf = io.BytesIO(data)
        try:
            df = pd.read_excel(buf, engine="openpyxl")
        except Exception:
            buf.seek(0)
            df = pd.read_excel(buf, engine="xlrd")
    else:
        engine = "openpyxl" if source.lower().endswith(".xlsx") else "xlrd"
        df = pd.read_excel(source, engine=engine)

    expected = ["License Name", "License Text", "License Family"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in Excel: {missing}. Expected {expected}")

    df["License Name"] = df["License Name"].astype(str).str.strip()
    df["License Text"] = df["License Text"].astype(str)
    df["License Family"] = df["License Family"].astype(str)
    df = df.dropna(subset=["License Name"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["License Name"], keep="first").reset_index(drop=True)
    return df

def run_name_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip(): return pd.DataFrame()
    mask = df["License Name"].apply(lambda x: contains_any(query, x))
    subset = df[mask].copy()
    subset["Match %"] = subset["License Name"].apply(lambda x: word_match_score(query, x))
    return subset.sort_values(by=["Match %", "License Name"], ascending=[False, True]).reset_index(drop=True)

def run_text_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip(): return pd.DataFrame()
    mask = df["License Text"].apply(lambda x: contains_any(query, x))
    subset = df[mask].copy()
    subset["Match %"] = subset["License Text"].apply(lambda x: word_match_score(query, x))
    return subset.sort_values(by=["Match %", "License Name"], ascending=[False, True]).reset_index(drop=True)

# -----------------------------
# Session state defaults
# -----------------------------
if "view" not in st.session_state:
    st.session_state.view = "home"
if "last_results" not in st.session_state:
    st.session_state.last_results = None
if "selected_license" not in st.session_state:
    st.session_state.selected_license = None
if "data_source" not in st.session_state:
    st.session_state.data_source = ""
if "df" not in st.session_state:
    st.session_state.df = None
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "last_query_type" not in st.session_state:
    st.session_state.last_query_type = ""
if "night_mode" not in st.session_state:
    st.session_state.night_mode = False

# Widget keys (to persist values across reruns)
TEXT_QUERY_KEY = "license_text_query"
NAME_SELECT_KEY = "license_select_value"

if TEXT_QUERY_KEY not in st.session_state:
    st.session_state[TEXT_QUERY_KEY] = ""
if NAME_SELECT_KEY not in st.session_state:
    st.session_state[NAME_SELECT_KEY] = "-- select --"

# -----------------------------
# Sidebar: Data source (hidden initially)
# -----------------------------
with st.sidebar.expander("📄 Data Source", expanded=False):
    st.write("Provide a local Excel path or a GitHub raw URL.")
    default_raw = "https://raw.githubusercontent.com/Bharathnelle335/License-Text-Finder/main/Licenses.xlsx"
    source_input = st.text_input(
        "Excel path or raw URL",
        value=st.session_state.data_source or default_raw,
        placeholder="e.g., ./Licenses.xlsx or a GitHub raw URL",
        key="data_source_input",
    )
    load_btn = st.button("Load Excel", key="load_excel_btn")

    if load_btn and source_input.strip():
        try:
            df = load_excel(source_input.strip())
            st.session_state.df = df
            st.session_state.data_source = source_input.strip()
            st.success(f"Loaded {len(df)} licenses.")
        except Exception as e:
            st.error(f"Failed to load Excel: {e}")

# If not loaded yet, try auto-load default
if st.session_state.df is None:
    try:
        df = load_excel("https://raw.githubusercontent.com/Bharathnelle335/License-Text-Finder/main/Licenses.xlsx")
        st.session_state.df = df
        st.session_state.data_source = "https://raw.githubusercontent.com/Bharathnelle335/License-Text-Finder/main/Licenses.xlsx"
    except Exception:
        st.info("👋 Open the sidebar, paste your Excel path/URL, and click **Load Excel** to begin.")
        st.stop()

df = st.session_state.df

# -----------------------------
# Top bar: Title (left) + Night mode (icon-only) + rotating brief
# -----------------------------
apply_global_polish()

top_cols = st.columns([6, 1])
with top_cols[0]:
    st.title("License Search")
    render_rotating_brief()

with top_cols[1]:
    with st.container():
        st.markdown('<div class="theme-toggle">', unsafe_allow_html=True)
        theme_clicked = st.button("🌙" if not st.session_state.night_mode else "☀️", key="theme_toggle")
        if theme_clicked:
            st.session_state.night_mode = not st.session_state.night_mode
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

apply_theme()  # apply after top bar

# -----------------------------
# Search UI (left: text search, right: license selector)
# -----------------------------
left, right = st.columns(2)

with left:
    st.markdown('<div class="section-header">Search within License Text</div>', unsafe_allow_html=True)
    text_query = st.text_input(
        "", placeholder="e.g., warranty, redistribution, exceptions",
        label_visibility="collapsed", key=TEXT_QUERY_KEY
    )
    text_search_clicked = st.button("License Text Search", key="text_search_btn")
    if text_search_clicked:
        st.session_state.last_results = run_text_search(df, st.session_state[TEXT_QUERY_KEY])
        st.session_state.last_query = st.session_state[TEXT_QUERY_KEY]
        st.session_state.last_query_type = "text"
        st.rerun()

with right:
    st.markdown('<div class="section-header">License Search</div>', unsafe_allow_html=True)
    lic_names = ["-- select --"] + sorted(df["License Name"].unique())
    # Selectbox bound to session_state key so value persists
    selected_name = st.selectbox(
        "", lic_names, index=lic_names.index(st.session_state[NAME_SELECT_KEY]) if st.session_state[NAME_SELECT_KEY] in lic_names else 0,
        label_visibility="collapsed", key=NAME_SELECT_KEY
    )
    # Open immediately when selected (and not placeholder)
    if st.session_state[NAME_SELECT_KEY] != "-- select --":
        st.session_state.selected_license = st.session_state[NAME_SELECT_KEY]
        st.session_state.view = "details"
        st.rerun()
    # Explicit search button (treat selection as query)
    name_search_clicked = st.button("License Name Search", key="name_search_btn")
    if name_search_clicked:
        q = st.session_state[NAME_SELECT_KEY] if st.session_state[NAME_SELECT_KEY] != "-- select --" else ""
        st.session_state.last_results = run_name_search(df, q)
        st.session_state.last_query = q
        st.session_state.last_query_type = "name"
        st.rerun()

# -----------------------------
# Helpers: Home / Clear
# -----------------------------
def set_home(clear_results: bool):
    st.session_state.view = "home"
    st.session_state.selected_license = None
    # Reset widget values too
    st.session_state[NAME_SELECT_KEY] = "-- select --"
    st.session_state[TEXT_QUERY_KEY] = ""
    if clear_results:
        st.session_state.last_results = None
        st.session_state.last_query = ""
        st.session_state.last_query_type = ""

# -----------------------------
# Home view: results list
# -----------------------------
if st.session_state.view == "home":
    results = st.session_state.last_results
    if results is not None and len(results) > 0:
        ctop1, ctop2, ctop3 = st.columns([1, 1, 1])

        back_top_clicked = ctop1.button("⬅️ Back to search results", key="back_top")
        if back_top_clicked:
            set_home(clear_results=False)
            st.rerun()

        clear_top_clicked = ctop2.button("🧹 Clear search results", key="clear_top")
        if clear_top_clicked:
            set_home(clear_results=True)
            st.rerun()

        home_top_clicked = ctop3.button("🏠 Home", key="home_top")
        if home_top_clicked:
            set_home(clear_results=True)
            st.rerun()

        st.markdown(f"### Results ({len(results)})")
        csv_bytes = results[["License Name", "License Family", "Match %"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download results (CSV)", data=csv_bytes, file_name="license_search_results.csv", mime="text/csv", key="dl_results_csv")

        st.dataframe(results[["License Name", "License Family", "Match %"]], use_container_width=True)

        st.divider()
        st.markdown("#### Open a license")
        for i, row in results.iterrows():
            c1, c2, c3, c4 = st.columns([6, 3, 2, 2])
            c1.write(f"**{row['License Name']}**")
            c2.write(f"Family: {row['License Family']}")
            c3.write(f"Match: {row['Match %']}%")
            view_clicked = c4.button("View", key=f"view_{i}")
            if view_clicked:
                st.session_state.selected_license = row["License Name"]
                st.session_state.view = "details"
                st.rerun()

        st.divider()
        cbtm1, cbtm2, cbtm3 = st.columns([1, 1, 1])

        back_bottom_clicked = cbtm1.button("⬅️ Back to search results", key="back_bottom")
        if back_bottom_clicked:
            set_home(clear_results=False)
            st.rerun()

        clear_bottom_clicked = cbtm2.button("🧹 Clear search results", key="clear_bottom")
        if clear_bottom_clicked:
            set_home(clear_results=True)
            st.rerun()

        home_bottom_clicked = cbtm3.button("🏠 Home", key="home_bottom")
        if home_bottom_clicked:
            set_home(clear_results=True)
            st.rerun()

    elif results is not None and len(results) == 0:
        st.warning("No matches found. Try different keywords.")

# -----------------------------
# Details view: selected license
# -----------------------------
if st.session_state.view == "details" and st.session_state.selected_license:
    sel = st.session_state.df[st.session_state.df["License Name"] == st.session_state.selected_license].head(1)
    if sel.empty:
        st.error("Selected license not found.")
    else:
        row = sel.iloc[0]

        dtop1, dtop2, dtop3 = st.columns([1, 1, 1])

        detail_back_top_clicked = dtop1.button("⬅️ Back to search results", key="detail_back_top")
        if detail_back_top_clicked:
            set_home(clear_results=False)
            st.rerun()

        detail_clear_top_clicked = dtop2.button("🧹 Clear search results", key="detail_clear_top")
        if detail_clear_top_clicked:
            set_home(clear_results=True)
            st.rerun()

        detail_home_top_clicked = dtop3.button("🏠 Home", key="detail_home_top")
        if detail_home_top_clicked:
            set_home(clear_results=True)
            st.rerun()

        st.markdown(f"## 📄 {row['License Name']}")
        st.caption(f"License Family: {row['License Family']}")

        recent_query = st.session_state.get("last_query", "")
        if str(recent_query).strip():
            st.markdown("**Highlighted text (matches marked):**", help="Matches are case-insensitive word hits.")
            st.markdown(
                highlight_text(row["License Text"], str(recent_query)),
                unsafe_allow_html=True
            )
            st.divider()

        st.markdown("**Full License Text:**")
        st.text_area(label="", value=row["License Text"], height=400, key="full_license_text")

        dbtm1, dbtm2, dbtm3 = st.columns([1, 1, 1])

        detail_back_bottom_clicked = dbtm1.button("⬅️ Back to search results", key="detail_back_bottom")
        if detail_back_bottom_clicked:
            set_home(clear_results=False)
            st.rerun()

        detail_clear_bottom_clicked = dbtm2.button("🧹 Clear search results", key="detail_clear_bottom")
        if detail_clear_bottom_clicked:
            set_home(clear_results=True)
            st.rerun()

        detail_home_bottom_clicked = dbtm3.button("🏠 Home", key="detail_home_bottom")
        if detail_home_bottom_clicked:
            set            set_home(clear_results=True)

