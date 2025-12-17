
import io
import re
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
    /* Minimal dark tweaks (extend as needed) */
    html, body, [class*="css"]  {
        background-color: #0B1221 !important;
        color: #e6edf3 !important;
    }
    .stTextArea textarea { background-color: #0f172a !important; color: #e6edf3 !important; }
    .stSelectbox div[data-baseweb="select"] { background-color: #0f172a !important; color: #e6edf3 !important; }
    </style>
    """
    if st.session_state.get("night_mode", False):
        st.markdown(dark_css, unsafe_allow_html=True)

# -----------------------------
# Minimal global polish
# -----------------------------
def apply_global_polish():
    """Minimal CSS for section headers."""
    global_css = """
    <style>
    .section-title { font-size: 1.1rem; font-weight: 600; margin: 0.25rem 0 0.5rem 0; }
    .muted { color: #64748b; }
    </style>
    """
    st.markdown(global_css, unsafe_allow_html=True)

# -----------------------------
# Rotating brief (optional, minimal)
# -----------------------------
def render_rotating_brief():
    """Simple static brief line."""
    color = "#e6edf3" if st.session_state.get("night_mode", False) else "#374151"
    st.markdown(
        f'<div class="muted" style="color:{color};">Select a license to view its full text instantly.</div>',
        unsafe_allow_html=True,
    )

# -----------------------------
# Utilities
# -----------------------------
def tokenize(text: str):
    return re.findall(r"\w+", (text or "").lower())

def word_match_score(query: str, target: str) -> float:
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    if not q_tokens:
        return 0.0
    found = sum(1 for w in q_tokens if w in t_tokens)
    return round((found / len(q_tokens)) * 100.0, 2)

def contains_any(query: str, target: str) -> bool:
    q_tokens = set(tokenize(query))
    t_tokens = set(tokenize(target))
    return any(w in t_tokens for w in q_tokens)

def highlight_text(text: str, query: str) -> str:
    if not text or not query:
        return text or ""
    def repl(m):
        return f"`{m.group(0)}`"
    highlighted = text
    for word in sorted(set(tokenize(query)), key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        highlighted = pattern.sub(repl, highlighted)
    return highlighted

def to_raw_url(maybe_github_url: str) -> str:
    if not maybe_github_url:
        return maybe_github_url
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

def run_text_search(df: pd.DataFrame, query: str) -> pd.Series | None:
    """
    Returns the FIRST matching license row (Series) for a text query, or None.
    (We no longer present a results table.)
    """
    if not query.strip():
        return None
    mask = df["License Text"].apply(lambda x: contains_any(query, x))
    subset = df[mask].copy()
    if subset.empty:
        return None
    subset["Match %"] = subset["License Text"].apply(lambda x: word_match_score(query, x))
    # pick best match
    best = subset.sort_values(by=["Match %", "License Name"], ascending=[False, True]).iloc[0]
    return best

# -----------------------------
# Session state defaults
# -----------------------------
if "view" not in st.session_state:
    st.session_state.view = "home"
if "selected_license" not in st.session_state:
    st.session_state.selected_license = None
if "data_source" not in st.session_state:
    st.session_state.data_source = ""
if "df" not in st.session_state:
    st.session_state.df = None
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "night_mode" not in st.session_state:
    st.session_state.night_mode = False

# Widget keys (persist values)
TEXT_QUERY_KEY = "license_text_query"
NAME_SELECT_KEY = "license_select_value"
if TEXT_QUERY_KEY not in st.session_state:
    st.session_state[TEXT_QUERY_KEY] = ""
if NAME_SELECT_KEY not in st.session_state:
    st.session_state[NAME_SELECT_KEY] = "-- select --"

# -----------------------------
# Sidebar: Data source
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

# Auto-load default if needed
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
# Top bar
# -----------------------------
apply_global_polish()
top_cols = st.columns([6, 1])
with top_cols[0]:
    st.title("License Search")
    render_rotating_brief()
with top_cols[1]:
    theme_clicked = st.button("🌙" if not st.session_state.night_mode else "☀️", key="theme_toggle")
    if theme_clicked:
        st.session_state.night_mode = not st.session_state.night_mode
        st.rerun()
apply_theme()  # apply after top bar

# -----------------------------
# Search UI (left: text search, right: license selector)
# -----------------------------
left, right = st.columns(2)

# --- Left: Text Search (no results table; just stores query, offers open best match) ---
with left:
    st.markdown('<div class="section-title">Search within License Text</div>', unsafe_allow_html=True)
    text_query = st.text_input(
        "",
        placeholder="e.g., warranty, redistribution, exceptions",
        label_visibility="collapsed",
        key=TEXT_QUERY_KEY
    )
    open_best_btn = st.button("Open best match from Text Search", key="open_best_from_text")
    if open_best_btn:
        best = run_text_search(df, st.session_state[TEXT_QUERY_KEY])
        if best is None:
            st.warning("No matches found. Try different keywords.")
        else:
            st.session_state.selected_license = best["License Name"]
            st.session_state.view = "details"
            st.session_state.last_query = st.session_state[TEXT_QUERY_KEY]
            st.rerun()

# --- Right: License select (instant open on selection) ---
with right:
    st.markdown('<div class="section-title">License Select</div>', unsafe_allow_html=True)
    lic_names = ["-- select --"] + sorted(df["License Name"].unique())
    selected_index = lic_names.index(st.session_state[NAME_SELECT_KEY]) if st.session_state[NAME_SELECT_KEY] in lic_names else 0

    selected_value = st.selectbox(
        "",
        lic_names,
        index=selected_index,
        label_visibility="collapsed",
        key=NAME_SELECT_KEY,
        on_change=lambda: (
            st.session_state.update({
                "selected_license": None if st.session_state[NAME_SELECT_KEY] == "-- select --" else st.session_state[NAME_SELECT_KEY],
                "view": "details" if st.session_state[NAME_SELECT_KEY] != "-- select --" else "home"
            })
        )
    )

# -----------------------------
# Details view: selected license (opens immediately on selection)
# -----------------------------
if st.session_state.view == "details" and st.session_state.selected_license:
    sel = df[df["License Name"] == st.session_state.selected_license].head(1)
    if sel.empty:
        st.error("Selected license not found.")
    else:
        row = sel.iloc[0]
        st.markdown(f"## 📄 {row['License Name']}")
        st.caption(f"License Family: {row['License Family']}")

        recent_query = st.session_state.get("last_query", "").strip()

        if recent_query:
            st.markdown("**Highlighted text (matches marked):**")
            st.markdown(
                highlight_text(row["License Text"], recent_query),
                unsafe_allow_html=True
            )
            st.divider()

        st.markdown("**Full License Text:**")
        st.text_area(label="", value=row["License Text"], height=400, key="full_license_text")

        # Minimal navigation (optional): a single Home button
        c1, c2 = st.columns([1, 1])
        home_clicked = c1.button("🏠 Home", key="home_btn")
        clear_clicked = c2.button("🧹 Clear selection", key="clear_btn")
        if home_clicked:
            st.session_state.view = "home"
            st.session_state.selected_license = None
            st.session_state[NAME_SELECT_KEY] = "-- select --"
            st.session_state[TEXT_QUERY_KEY] = ""
            st.session_state.last_query = ""
            st.rerun()
        if clear_clicked:
            st.session_state.selected_license = None
            st.session_state.view = "home"
            st.session_state[NAME_SELECT_KEY] = "-- select --"
            st.rerun()

# -----------------------------
# Home view: nothing to show (no results table anymore)
# -----------------------------
if st.session_state.view == "home":
   

