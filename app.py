
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
    .stApp {
        background-color: var(--bg) !important;
        color: var(--text) !important;
    }
    h1, h2, h3, h4, h5, h6,
    .stMarkdown, .stText, .stCaption {
        color: var(--text) !important;
    }
    .st-emotion-cache-1r6slb0,
    .st-emotion-cache-1jicfl2,
    .st-emotion-cache-1v0mbdj,
    .stTextArea textarea,
    .stDataFrame {
        background-color: var(--panel) !important;
        color: var(--text) !important;
        border-color: var(--border) !important;
    }
    mark {
        background: #ffd54f !important; /* high-contrast amber */
        color: #000 !important;
        padding: 0 2px;
        border-radius: 2px;
    }
    .theme-toggle button {
        width: 42px;
        height: 42px;
        border-radius: 50%;
        font-size: 20px;
        line-height: 20px;
        padding: 0;
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
    /* Left/right headers (no backgrounds) */
    .section-header {
        font-size: 1.15rem;          /* slightly larger */
        font-weight: 600;
        letter-spacing: 0.2px;
        margin-bottom: 6px;
    }
    /* Small gap utility */
    .gap-6 { margin-top: 6px; }
    </style>
    """
    st.markdown(global_css, unsafe_allow_html=True)

# -----------------------------
# Rotating brief (without page reload)
# -----------------------------
def render_rotating_brief():
    """
    Render a short line under the title that changes every 5 seconds
    using JavaScript inside st.html (no page reload).
    """
    messages = [
        "Find licenses by name or text and view full, highlighted content.",
        "Quickly open any license and navigate back easily with top/bottom controls.",
        "Toggle night mode for comfortable reading."
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
        if (el) {{
          el.textContent = msgs[i % msgs.length];
        }}
      }}
      update();                // initial
      setInterval(() => {{     // rotate every 5s
        i += 1;
        update();
      }}, 5000);
    </script>
    """
    # IMPORTANT: st.html supports unsafe_allow_javascript but not 'height'
    st.html(html, unsafe_allow_javascript=True)

# -----------------------------
# Utilities
# -----------------------------
def tokenize(text: str):
    """Split text into lowercase word tokens."""
    return re.findall(r"\w+", (text or "").lower())

def word_match_score(query: str, target: str) -> float:
    """Simple percentage match of unique query words found in target."""
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    if not q_tokens:
        return 0.0
    found = sum(1 for w in q_tokens if w in t_tokens)
    return round((found / len(q_tokens)) * 100.0, 2)

def contains_any(query: str, target: str) -> bool:
    """Return True if any query word is found in target text."""
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    return any(w in t_tokens for w in q_tokens)

def highlight_text(text: str, query: str) -> str:
    """Highlight query words in text using <mark>…</mark> (case-insensitive)."""
    if not text or not query:
        return text or ""
    def repl(match):
        return f"<mark>{match.group(0)}</mark>"
    highlighted = text
    for word in sorted(set(tokenize(query)), key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        highlighted = pattern.sub(repl, highlighted)
    return highlighted

def to_raw_url(maybe_github_url: str) -> str:
    """Convert GitHub blob URL to raw.githubusercontent URL if needed."""
    if not maybe_github_url:
        return maybe_github_url
    if "github.com" in maybe_github_url and "/blob/" in maybe_github_url:
        parts = maybe_github_url.split("github.com/")[-1]
        owner_repo, _, branch_and_path = parts.partition("/blob/")
        branch, _, path = branch_and_path.partition("/")
        raw = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{path}"
        return raw
    return maybe_github_url

@st.cache_data(show_spinner=False)
def load_excel(source: str) -> pd.DataFrame:
    """
    Load Excel from a local path or a GitHub raw URL.
    Requires:
      - .xlsx -> engine='openpyxl'
      - .xls  -> engine='xlrd'
    """
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
        suffix = source.lower().strip()
        engine = "openpyxl" if suffix.endswith(".xlsx") else "xlrd"
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
    if not query.strip():
        return pd.DataFrame()
    mask = df["License Name"].apply(lambda x: contains_any(query, x))
    subset = df[mask].copy()
    subset["Match %"] = subset["License Name"].apply(lambda x: word_match_score(query, x))
    subset = subset.sort_values(by=["Match %", "License Name"], ascending=[False, True]).reset_index(drop=True)
    return subset

def run_text_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip():
        return pd.DataFrame()
    mask = df["License Text"].apply(lambda x: contains_any(query, x))
    subset = df[mask].copy()
    subset["Match %"] = subset["License Text"].apply(lambda x: word_match_score(query, x))
    subset = subset.sort_values(by=["Match %", "License Name"], ascending=[False, True]).reset_index(drop=True)
    return subset

# -----------------------------
# Session state keys
# -----------------------------
if "view" not in st.session_state:
    st.session_state.view = "home"      # home | details
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

# -----------------------------
# Helpers for navigation/buttons
# -----------------------------
def go_home(clear_results: bool = True):
    """Reset the app to a clean home state."""
    st.session_state.view = "home"
    st.session_state.selected_license = None
    if clear_results:
        st.session_state.last_results = None
        st.session_state.last_query = ""
        st.session_state.last_query_type = ""
    st.rerun()

def clear_results_and_back():
    """Clear search results and go to home."""
    go_home(clear_results=True)

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
    )
    load_btn = st.button("Load Excel")

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
    # Left-aligned title
    st.title("License Search")
    # Rotating brief just under the title (no page reload)
    render_rotating_brief()

with top_cols[1]:
    with st.container():
        st.markdown('<div class="theme-toggle">', unsafe_allow_html=True)
        if st.button("🌙" if not st.session_state.night_mode else "☀️", key="theme_toggle"):
            st.session_state.night_mode = not st.session_state.night_mode
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# Apply dark theme (if enabled) after drawing top bar
apply_theme()

# -----------------------------
# Search UI (left: text search, right: license selector)
# -----------------------------
left, right = st.columns(2)

with left:
    # LEFT header: plain text, larger size, no background
    st.markdown('<div class="section-header">Search within License Text</div>', unsafe_allow_html=True)
    text_query = st.text_input("", placeholder="e.g., warranty, redistribution, exceptions", label_visibility="collapsed")
    text_search_btn = st.button("License Text Search")

with right:
    # RIGHT header: plain text, larger size, no background
    st.markdown('<div class="section-header">License Search</div>', unsafe_allow_html=True)
    lic_names = ["-- select --"] + sorted(df["License Name"].unique())
    selected_name = st.selectbox("", lic_names, index=0, label_visibility="collapsed")
    # Open immediately when selected
    if selected_name and selected_name != "-- select --":
        st.session_state.selected_license = selected_name
        st.session_state.view = "details"
    # Explicit search-by-name button (treat selection as query)
    name_query = "" if selected_name == "-- select --" else selected_name
    name_search_btn = st.button("License Name Search")

# -----------------------------
# Home view: results list
# -----------------------------
if st.session_state.view == "home":
    if name_search_btn:
        results = run_name_search(df, name_query)
        st.session_state.last_results = results
        st.session_state.last_query = name_query
        st.session_state.last_query_type = "name"

    if text_search_btn:
        results = run_text_search(df, text_query)
        st.session_state.last_results = results
        st.session_state.last_query = text_query
        st.session_state.last_query_type = "text"

    results = st.session_state.last_results
    if results is not None and len(results) > 0:
        # Top controls: Back + Clear + Home
        ctop1, ctop2, ctop3 = st.columns([1, 1, 1])
        with ctop1:
            st.button("⬅️ Back to search results", key="back_top", on_click=lambda: go_home(clear_results=False))
        with ctop2:
            st.button("🧹 Clear search results", key="clear_top", on_click=clear_results_and_back)
        with ctop3:
            st.button("🏠 Home", key="home_top", on_click=lambda: go_home(clear_results=True))

        st.markdown(f"### Results ({len(results)})")
        csv_bytes = results[["License Name", "License Family", "Match %"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download results (CSV)", data=csv_bytes, file_name="license_search_results.csv", mime="text/csv")

        st.dataframe(results[["License Name", "License Family", "Match %"]], use_container_width=True)

        st.divider()
        st.markdown("#### Open a license")
        for i, row in results.iterrows():
            c1, c2, c3, c4 = st.columns([6, 3, 2, 2])
            c1.write(f"**{row['License Name']}**")
            c2.write(f"Family: {row['License Family']}")
            c3.write(f"Match: {row['Match %']}%")
            if c4.button("View", key=f"view_{i}"):
                st.session_state.selected_license = row["License Name"]
                st.session_state.view = "details"
                st.rerun()

        # Bottom controls: Back + Clear + Home
        st.divider()
        cbtm1, cbtm2, cbtm3 = st.columns([1, 1, 1])
        with cbtm1:
            st.button("⬅️ Back to search results", key="back_bottom", on_click=lambda: go_home(clear_results=False))
        with cbtm2:
            st.button("🧹 Clear search results", key="clear_bottom", on_click=clear_results_and_back)
        with cbtm3:
            st.button("🏠 Home", key="home_bottom", on_click=lambda: go_home(clear_results=True))

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

        # Top controls: Back + Clear + Home
        dtop1, dtop2, dtop3 = st.columns([1, 1, 1])
        with dtop1:
            if st.button("⬅️ Back to search results", key="detail_back_top"):
                go_home(clear_results=False)
        with dtop2:
            if st.button("🧹 Clear search results", key="detail_clear_top"):
                clear_results_and_back()
        with dtop3:
            if st.button("🏠 Home", key="detail_home_top"):
                go_home(clear_results=True)

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
        st.text_area(label="", value=row["License Text"], height=400)

        # Bottom controls: Back + Clear + Home
        dbtm1, dbtm2, dbtm3 = st.columns([1, 1, 1])
        with dbtm1:
            if st.button("⬅️ Back to search results", key="detail_back_bottom"):
                go_home(clear_results=False)
        with dbtm2:
            if st.button("🧹 Clear search results", key="detail_clear_bottom"):
                clear_results_and_back()
        with dbtm3:
            if st.button("🏠 Home", key="detail_home_bottom"):

