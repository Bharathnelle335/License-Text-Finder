
# app.py
import io
import re
from urllib.parse import urlparse
from urllib.request import urlopen

import pandas as pd
import streamlit as st

# -----------------------------
# App Config
# -----------------------------
st.set_page_config(page_title="License Search UI", layout="wide")

# -----------------------------
# Utilities
# -----------------------------
def tokenize(text: str):
    """Split text into lowercase word tokens."""
    return re.findall(r"\w+", (text or "").lower())

def word_match_score(query: str, target: str) -> float:
    """
    Simple percentage match:
    (# unique query words found in target) / (total unique query words) * 100
    """
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
        # Use word boundary to avoid partials inside other words
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        highlighted = pattern.sub(repl, highlighted)
    return highlighted

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
    parsed = urlparse(source)
    is_url = parsed.scheme in ("http", "https")

    if is_url:
        with urlopen(source) as resp:
            data = resp.read()
        buf = io.BytesIO(data)
        # Try .xlsx first, fallback to .xls
        try:
            df = pd.read_excel(buf, engine="openpyxl")
        except Exception:
            buf.seek(0)
            df = pd.read_excel(buf, engine="xlrd")
    else:
        # Local file path
        suffix = source.lower().strip()
        engine = "openpyxl" if suffix.endswith(".xlsx") else "xlrd"
        df = pd.read_excel(source, engine=engine)

    # Normalize expected columns
    expected = ["License Name", "License Text", "License Family"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in Excel: {missing}. Expected {expected}")

    # Clean basic types and drop full-empty rows
    df["License Name"] = df["License Name"].astype(str).str.strip()
    df["License Text"] = df["License Text"].astype(str)
    df["License Family"] = df["License Family"].astype(str)
    df = df.dropna(subset=["License Name"]).reset_index(drop=True)

    # Optional: drop duplicate license names (keep first)
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
    st.session_state.data_source = ""   # Path or URL
if "df" not in st.session_state:
    st.session_state.df = None

# -----------------------------
# Sidebar: Data source
# -----------------------------
st.sidebar.header("📄 Data Source")
st.sidebar.write("Provide a local Excel path or a GitHub **raw** URL.")

default_hint = "e.g., ./licenses.xlsx or https://raw.githubusercontent.com/<org>/<repo>/<branch>/licenses.xlsx"
source_input = st.sidebar.text_input("Excel path or raw URL", value=st.session_state.data_source or "", placeholder=default_hint)
load_btn = st.sidebar.button("Load Excel")

if load_btn and source_input.strip():
    try:
        df = load_excel(source_input.strip())
        st.session_state.df = df
        st.session_state.data_source = source_input.strip()
        st.sidebar.success(f"Loaded {len(df)} licenses.")
    except Exception as e:
        st.sidebar.error(f"Failed to load Excel: {e}")

# If not loaded yet, show a small tip
if st.session_state.df is None:
    st.info("👋 Paste your Excel path/URL in the sidebar and click **Load Excel** to begin.")
    st.stop()

df = st.session_state.df

# -----------------------------
# Main UI
# -----------------------------
st.title("🔎 License Search UI")

# Dropdown to list all licenses
with st.expander("📚 Browse all licenses (dropdown)"):
    lic_names = sorted(df["License Name"].unique())
    choice = st.selectbox("Select a license:", ["-- Select --"] + lic_names, index=0)
    if choice and choice != "-- Select --":
        st.session_state.selected_license = choice
        st.session_state.view = "details"

# Search inputs
st.subheader("Search")
col1, col2 = st.columns(2)
with col1:
    name_query = st.text_input("🔤 Search by License Name", placeholder="e.g., GPL, MIT, .NETZ, Zveno")
    name_search_btn = st.button("License Name Search")
with col2:
    text_query = st.text_input("🧾 Search within License Text", placeholder="e.g., warranty, redistribution, exceptions")
    text_search_btn = st.button("License Text Search")

# Actions
if st.session_state.view == "home":
    if name_search_btn:
        results = run_name_search(df, name_query)
        st.session_state.last_results = results
    if text_search_btn:
        results = run_text_search(df, text_query)
        st.session_state.last_results = results

    # Show results (if any)
    results = st.session_state.last_results
    if results is not None and len(results) > 0:
        st.markdown(f"### Results ({len(results)})")
        # Download CSV
        csv_bytes = results[["License Name", "License Family", "Match %"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download results (CSV)", data=csv_bytes, file_name="license_search_results.csv", mime="text/csv")

        # Table with action buttons
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
                st.experimental_rerun()

    elif results is not None and len(results) == 0:
        st.warning("No matches found. Try different keywords.")

# Details view
if st.session_state.view == "details" and st.session_state.selected_license:
    sel = df[df["License Name"] == st.session_state.selected_license].head(1)
    if sel.empty:
        st.error("Selected license not found.")
    else:
        row = sel.iloc[0]
        st.markdown(f"## 📄 {row['License Name']}")
        st.caption(f"License Family: {row['License Family']}")

        # Show highlighted text if the recent query exists
        recent_query = text_query if text_search_btn else (name_query if name_search_btn else "")
        if recent_query.strip():
            st.markdown("**Highlighted text (matches marked):**", help="Matches are case-insensitive word hits.")
            st.markdown(
                highlight_text(row["License Text"], recent_query),
                unsafe_allow_html=True
            )
            st.divider()
        st.markdown("**Full License Text:**")
        st.text_area(
            label="",
            value=row["License Text"],
            height=400,
        )

        # Back button
        if st.button("⬅️ Back to search results"):
            st.session_state.view = "home"
            st.experimental_rerun()
``
