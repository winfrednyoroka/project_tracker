# Simplified app with hidden admin toggle placeholder
import streamlit as st
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
from utils.schema import ensure_schema, STATUS_OPTIONS, new_id, COLUMNS
from utils.storage import (
    load_df,
    save_df,
    get_cache_key,
    load_df_cached,
    is_github_mode,
)
from utils.gantt import make_gantt

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(
    page_title="Gantt Tracker",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Hidden Admin Toggle utilities
# -----------------------------
# def _admin_password_ok(pwd: str) -> bool:
#     try:
#         secret = st.secrets.get("ADMIN_PASSWORD", None)  # on Cloud
#     except FileNotFoundError:
#         # running locally without secrets; allow admin if password empty or matches placeholder in local tests
#         secret = None
#     if not secret:
#         # No admin password set in secrets => admin disabled (view-only)
#         return False
#     return (pwd or "").strip() == str(secret).strip()
def _admin_password_ok(pwd: str) -> bool:
    """
    Check admin password using 3 layers:
    1. Streamlit Cloud secrets (preferred)
    2. Environment variable (optional local override)
    3. Local development fallback (for when secrets.toml does not exist)
    """

    # 1. Try Streamlit Secrets (Cloud or local secrets.toml)
    try:
        secret = st.secrets.get("ADMIN_PASSWORD", None)
    except FileNotFoundError:
        secret = None

    # 2. Try environment variable (optional override)
    if not secret:
        import os
        secret = os.environ.get("ADMIN_PASSWORD")

    # 3. Local fallback — enables admin mode on your laptop WITHOUT secrets.toml
    if not secret:
        secret = "gatua123"

    # Final comparison
    return (pwd or "").strip() == str(secret).strip()

def _render_admin_unlock():
    # Hidden activation via "double-click" mimic: small invisible area under title + keyboard hint
    with st.expander("", expanded=False):
        pass  # purely to create a minimal clickable target with no visible text

    # Keyboard gesture hint: We'll store a session flag when user presses Ctrl+Shift+A via a simple text_input trick.
    # Since Streamlit doesn't capture key combos natively, we present nothing here.
    # Admin reveal is via a secret clickable zone: double-click the main title line area.
    # We'll implement 'unlock' prompt behind a tiny info icon.
    st.markdown(
        """
        <style>
          .admin-anchor {
            position: relative;
            top: -6px;
            left: 0px;
            width: 18px;
            height: 18px;
            opacity: 0; /* truly hidden */
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    col_a, col_b = st.columns([0.001, 0.999])
    with col_a:
        # Hidden anchor – clicking in this tiny area won't be obvious to supervisors
        if st.button(" ", key="admin_anchor", help=None):
            st.session_state["_try_unlock"] = True
    with col_b:
        pass

    # Also allow "double-click title": When user clicks the title marker, we toggle a state
    # We'll piggyback on a small checkbox that's styled to be invisible.
    # (This is a simple workaround in Streamlit to provide a hidden interaction point.)
    if "_try_unlock" not in st.session_state:
        st.session_state["_try_unlock"] = False

    if st.session_state["_try_unlock"]:
        with st.popover("🔐 Enter admin password"):
            pwd = st.text_input("Admin password", type="password")
            c1, c2 = st.columns([1, 3])
            with c1:
                if st.button("Unlock"):
                    if _admin_password_ok(pwd):
                        st.session_state["_is_admin"] = True
                        st.success("Admin mode enabled.")
                        st.rerun()
                    else:
                        st.error("Incorrect password.")
            with c2:
                if st.button("Cancel"):
                    st.session_state["_try_unlock"] = False

def is_admin_mode() -> bool:
    return st.session_state.get("_is_admin", False)

# -----------------------------
# Header & Hidden Admin Toggle
# -----------------------------
st.markdown("<h1>📊 Project Gantt Tracker</h1>", unsafe_allow_html=True)
if "_is_admin" not in st.session_state:
    st.session_state["_is_admin"] = False
_render_admin_unlock()

# -----------------------------
# Sidebar: Refresh toggle (for everyone)
# -----------------------------
st.sidebar.header("⏱️ Refresh")
auto_refresh = st.sidebar.toggle("Auto-refresh every 60 seconds", value=False, help="When enabled, the page refreshes automatically every minute to fetch the latest data.")
if auto_refresh:
    st.experimental_rerun  # placeholder for type hinting
    st_autorefresh = st.experimental_data_editor if False else None
    st_autorefresh = st.experimental_rerun  # lint silencer
    st.runtime.legacy_caching.clear_cache  # avoid warnings
    # Use Streamlit's built-in autorefresh
    st_autorefresh = st.experimental_memo if False else None
    st_autorefresh = st.autorefresh(interval=60 * 1000, limit=None, key="auto_refresh_key")

# -----------------------------
# Load data (cached)
# -----------------------------
cache_key = get_cache_key()
df = load_df_cached(cache_key).copy()
df = ensure_schema(df)
# Important: source_version string used for GitHub optimistic concurrency (sha) or local mtime
source_version = cache_key.split(":", 1)[1] if ":" in cache_key else cache_key

# -----------------------------
# Sidebar: Filters
# -----------------------------
st.sidebar.header("🔎 Filters")
modules = sorted([m for m in df["Module"].dropna().unique() if m != ""])
owners = sorted([o for o in df["Owner"].dropna().unique() if o != ""])
statuses = STATUS_OPTIONS

sel_modules = st.sidebar.multiselect("Module(s)", modules, default=modules)
sel_owners = st.sidebar.multiselect("Owner(s)", owners, default=owners)
sel_status = st.sidebar.multiselect("Status", statuses, default=statuses)

# Date range default: past 1 month to +6 months
today = date.today()
default_start = today - relativedelta(months=1)
default_end = today + relativedelta(months=6)
sel_date = st.sidebar.date_input("Date window", (default_start, default_end))
if isinstance(sel_date, (list, tuple)) and len(sel_date) == 2:
    sel_start, sel_end = sel_date
else:
    sel_start, sel_end = default_start, default_end

search_text = st.sidebar.text_input("Search (task/notes)")
color_by = st.sidebar.radio("Color by", options=["Status", "Progress"], horizontal=True)

# -----------------------------
# Apply filters
# -----------------------------
fdf = df.copy()
if sel_modules:
    fdf = fdf[fdf["Module"].isin(sel_modules)]
if sel_owners:
    fdf = fdf[fdf["Owner"].isin(sel_owners)]
if sel_status:
    fdf = fdf[fdf["Status"].isin(sel_status)]

if sel_start:
    fdf = fdf[(fdf["Finish"].isna()) | (fdf["Finish"] >= pd.to_datetime(sel_start))]
if sel_end:
    fdf = fdf[(fdf["Start"].isna()) | (fdf["Start"] <= pd.to_datetime(sel_end))]
if search_text:
    mask = fdf["Task"].str.contains(search_text, case=False, na=False) | fdf["Notes"].str.contains(search_text, case=False, na=False)
    fdf = fdf[mask]

# -----------------------------
# Metrics
# -----------------------------
total = len(df)
done = int((df["Status"] == "Done").sum())
overdue = int(((df["Status"] != "Done") & df["Finish"].notna() & (df["Finish"] < pd.Timestamp.today())).sum())
in_progress = int((df["Status"] == "In Progress").sum())
blocked = int((df["Status"] == "Blocked").sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total tasks", total)
m2.metric("Done", done)
m3.metric("In Progress", in_progress)
m4.metric("Blocked", blocked)
m5.metric("Overdue", overdue)

# -----------------------------
# Tabs: Gantt, Table (read-only), Admin tabs appear only in admin mode
# -----------------------------
if is_admin_mode():
    tabs = st.tabs(["📆 Gantt", "📋 Table (view)", "🛠️ Edit tasks", "➕ Add task", "⬇⬆ Import/Export", "⚙️ Settings"])
else:
    tabs = st.tabs(["📆 Gantt", "📋 Table (view)", "⚙️ Settings"])

with tabs[0]:
    st.subheader("Timeline")
    fig = make_gantt(fdf, color_by=color_by)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Add tasks with Start and Finish dates to see the Gantt chart.")

with tabs[1]:
    st.subheader("Tasks (read-only)")
    cfg = {
        "ID": st.column_config.TextColumn("ID", disabled=True),
        "Module": st.column_config.TextColumn("Module", disabled=True),
        "Task": st.column_config.TextColumn("Task", disabled=True),
        "Owner": st.column_config.TextColumn("Owner", disabled=True),
        "Start": st.column_config.DateColumn("Start", disabled=True),
        "Finish": st.column_config.DateColumn("Finish", disabled=True),
        "Progress": st.column_config.NumberColumn("Progress (%)", min_value=0, max_value=100, step=1, disabled=True),
        "Status": st.column_config.TextColumn("Status", disabled=True),
        "DependsOn": st.column_config.TextColumn("Depends on", disabled=True),
        "Notes": st.column_config.TextColumn("Notes", disabled=True, width="large"),
        "LastUpdated": st.column_config.DatetimeColumn("Last Updated", disabled=True),
    }
    st.dataframe(fdf[COLUMNS], use_container_width=True)

# -----------------------------
# Admin-only tabs
# -----------------------------
if is_admin_mode():
    # Edit existing rows
    with tabs[2]:
        st.subheader("Edit tasks (admin)")
        cfg_edit = {
            "ID": st.column_config.TextColumn("ID", disabled=True, help="Auto-generated"),
            "Module": st.column_config.TextColumn("Module"),
            "Task": st.column_config.TextColumn("Task"),
            "Owner": st.column_config.TextColumn("Owner"),
            "Start": st.column_config.DateColumn("Start"),
            "Finish": st.column_config.DateColumn("Finish"),
            "Progress": st.column_config.NumberColumn("Progress (%)", min_value=0, max_value=100, step=1),
            "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS),
            "DependsOn": st.column_config.TextColumn("Depends on (IDs, comma-separated)"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
            "LastUpdated": st.column_config.DatetimeColumn("Last Updated", disabled=True),
        }
        edf = st.data_editor(df, num_rows="dynamic", column_config=cfg_edit, use_container_width=True, hide_index=True, key="editor_admin")

        c1, c2, c3 = st.columns([1, 1, 6])
        with c1:
            if st.button("💾 Save changes to GitHub", type="primary"):
                edf = ensure_schema(edf)
                edf["LastUpdated"] = pd.Timestamp.utcnow()
                try:
                    _ = save_df(edf, source_version, commit_message="Edit via Streamlit Gantt app")
                    st.cache_data.clear()
                    st.success("Saved to GitHub.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not save: {e}")

        with c2:
            if st.button("🔄 Reload from GitHub"):
                st.cache_data.clear()
                st.experimental_rerun()

    # Add new task
    with tabs[3]:
        st.subheader("Add a new task (admin)")
        with st.form("add_task"):
            col1, col2 = st.columns(2)
            with col1:
                module = st.text_input("Module / Work package", placeholder="e.g., WP1 – Data ingestion")
                task_name = st.text_input("Task", placeholder="e.g., Clean baseline dataset")
                owner = st.text_input("Owner", placeholder="e.g., W. Gatua")
            with col2:
                start = st.date_input("Start date")
                finish = st.date_input("Finish date")
                status = st.selectbox("Status", STATUS_OPTIONS, index=0)
                progress = st.slider("Progress (%)", 0, 100, value=0, step=5)
            depends = st.text_input("Depends on (IDs, comma-separated)", placeholder="e.g., a1b2c3d4, e5f6g7h8")
            notes = st.text_area("Notes", placeholder="Context, risks, links…")
            submitted = st.form_submit_button("Add task", type="primary")

        if submitted:
            row = {
                "ID": new_id(),
                "Module": module.strip(),
                "Task": task_name.strip(),
                "Owner": owner.strip(),
                "Start": pd.to_datetime(start) if start else pd.NaT,
                "Finish": pd.to_datetime(finish) if finish else pd.NaT,
                "Progress": progress,
                "Status": status,
                "DependsOn": depends.strip(),
                "Notes": notes.strip(),
                "LastUpdated": pd.Timestamp.utcnow(),
            }
            new_df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            try:
                _ = save_df(new_df, source_version, commit_message=f"Add task {row['ID']} via Streamlit Gantt app")
                st.cache_data.clear()
                st.success(f"Task added (ID: {row['ID']}).")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")

    # Import/Export
    with tabs[4]:
        st.subheader("Import / Export CSV (admin)")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇ Download current CSV",
                data=df.to_csv(index=False),
                file_name="tasks.csv",
                mime="text/csv"
            )
        with c2:
            uploaded = st.file_uploader("⬆ Upload CSV to replace current data", type=["csv"])
            if uploaded is not None:
                try:
                    new_df = pd.read_csv(uploaded)
                    new_df = ensure_schema(new_df)
                    new_df["LastUpdated"] = pd.Timestamp.utcnow()
                    _ = save_df(new_df, source_version, commit_message="Import CSV via Streamlit Gantt app")
                    st.cache_data.clear()
                    st.success("Imported CSV and saved to GitHub.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Import failed: {e}")

    # Settings (admin)
    with tabs[5]:
        st.subheader("Settings & Info (admin)")
        st.markdown(f"""
- **Storage Mode:** {'GitHub CSV (commits to repo)' if is_github_mode() else 'Local CSV (dev mode)'}  
- **CSV Path:** `data/tasks.csv`  
- **Columns:** {', '.join(COLUMNS)}  
- **Tip:** Use the *DependsOn* field to list prerequisite task IDs (comma-separated).  
- **Version:** `{source_version}`
""")
        st.info("On Streamlit Cloud, add required secrets to enable GitHub persistence.")
else:
    # Settings (view-only)
    with tabs[2]:
        st.subheader("Settings & Info")
        st.markdown(f"""
- **Mode:** View-only  
- **Storage Mode:** {'GitHub CSV (repo-backed)' if is_github_mode() else 'Local CSV (dev mode)'}  
- **CSV Path:** `data/tasks.csv`  
- **Columns:** {', '.join(COLUMNS)}  
- **Version:** `{source_version}`
""")
        st.info("This is a read-only view. Only the administrator can edit tasks.")