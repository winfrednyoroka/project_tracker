import base64
import io
import os
from typing import Optional, Tuple
import pandas as pd
import requests
import streamlit as st
from .schema import ensure_schema, COLUMNS


LOCAL_PATH = "data/tasks.csv"


# -------------------------------------------------
# Local file helpers
# -------------------------------------------------
def _ensure_data_dir():
    os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)


def _read_local_csv() -> Tuple[pd.DataFrame, str]:
    _ensure_data_dir()
    if not os.path.exists(LOCAL_PATH):
        empty = pd.DataFrame(columns=COLUMNS)
        empty.to_csv(LOCAL_PATH, index=False)

    df = pd.read_csv(LOCAL_PATH)
    df = ensure_schema(df)
    mtime = str(os.path.getmtime(LOCAL_PATH))
    return df, mtime


def _write_local_csv(df: pd.DataFrame):
    _ensure_data_dir()
    tmp_path = LOCAL_PATH + ".tmp"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, LOCAL_PATH)


# -------------------------------------------------
# Secrets handling (safe for local dev)
# -------------------------------------------------
def _get_secrets():
    """
    Return GitHub secrets if present.
    If running locally without secrets.toml, return None.
    """
    required = ["GITHUB_TOKEN", "GITHUB_REPO", "GITHUB_BRANCH", "GITHUB_FILE_PATH"]

    try:
        keys = st.secrets.keys()
    except FileNotFoundError:
        return None  # local mode

    if not all(k in keys for k in required):
        return None

    return {
        k: st.secrets[k] for k in required
    } | {
        "GITHUB_COMMIT_AUTHOR_NAME": st.secrets.get(
            "GITHUB_COMMIT_AUTHOR_NAME", "Streamlit Bot"
        ),
        "GITHUB_COMMIT_AUTHOR_EMAIL": st.secrets.get(
            "GITHUB_COMMIT_AUTHOR_EMAIL", "actions@users.noreply.github.com"
        ),
    }


# -------------------------------------------------
# GitHub helpers
# -------------------------------------------------
def _github_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }


def _read_github_csv(secrets) -> Tuple[pd.DataFrame, str]:
    owner_repo = secrets["GITHUB_REPO"]
    path = secrets["GITHUB_FILE_PATH"]
    branch = secrets["GITHUB_BRANCH"]

    # Safe multi-line f-string to avoid syntax breaks
    url = (
        f"https://api.github.com/repos/{owner_repo}/contents/"
        f"{path}?ref={branch}"
    )

    r = requests.get(
        url, headers=_github_headers(secrets["GITHUB_TOKEN"]), timeout=20
    )

    if r.status_code == 404:
        # File does not exist yet → create it
        empty = pd.DataFrame(columns=COLUMNS)
        _write_github_csv(empty, secrets, sha=None, message="Initialize tasks.csv")
        return empty, "init"

    r.raise_for_status()

    data = r.json()
    content_b64 = data["content"]
    sha = data["sha"]

    csv_bytes = base64.b64decode(content_b64)
    df = pd.read_csv(io.BytesIO(csv_bytes))
    df = ensure_schema(df)

    return df, sha


def _write_github_csv(
    df: pd.DataFrame,
    secrets,
    sha: Optional[str],
    message: str = "Update tasks.csv",
):
    owner_repo = secrets["GITHUB_REPO"]
    path = secrets["GITHUB_FILE_PATH"]
    branch = secrets["GITHUB_BRANCH"]

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)

    encoded = base64.b64encode(csv_buffer.getvalue().encode()).decode()

    payload = {
        "message": message,
        "content": encoded,
        "branch": branch,
        "committer": {
            "name": secrets["GITHUB_COMMIT_AUTHOR_NAME"],
            "email": secrets["GITHUB_COMMIT_AUTHOR_EMAIL"],
        },
    }

    # Only include sha when file already exists
    if sha and sha != "init":
        payload["sha"] = sha

    url = f"https://api.github.com/repos/{owner_repo}/contents/{path}"

    r = requests.put(
        url,
        json=payload,
        headers=_github_headers(secrets["GITHUB_TOKEN"]),
        timeout=30,
    )
    r.raise_for_status()

    return r.json()["content"]["sha"]


# -------------------------------------------------
# Public API used by the app
# -------------------------------------------------
def is_github_mode() -> bool:
    return _get_secrets() is not None


@st.cache_data(show_spinner=False)
def load_df_cached(cache_key: str) -> pd.DataFrame:
    secrets = _get_secrets()
    if secrets:
        df, _sha = _read_github_csv(secrets)
        return df
    df, _ = _read_local_csv()
    return df


def get_cache_key() -> str:
    """
    Key for cache invalidation:
    - GitHub: uses SHA of file
    - Local: uses mtime
    """
    secrets = _get_secrets()

    if secrets:
        try:
            _, sha = _read_github_csv(secrets)
            return f"github:{sha}"
        except Exception:
            return "github:error"

    # Local
    if os.path.exists(LOCAL_PATH):
        return f"local:{os.path.getmtime(LOCAL_PATH)}"

    return "local:empty"


def load_df() -> Tuple[pd.DataFrame, str]:
    """
    Load without caching — only used for admin saving.
    """
    secrets = _get_secrets()

    if secrets:
        df, sha = _read_github_csv(secrets)
        return df, sha

    df, mtime = _read_local_csv()
    return df, mtime


def save_df(df: pd.DataFrame, source_version: str, commit_message: str = "Update tasks"):
    """
    Save dataframe.  
    If GitHub secrets available → commit to GitHub.  
    Otherwise → save locally.
    """
    secrets = _get_secrets()

    if secrets:
        # check concurrency
        current_df, current_sha = _read_github_csv(secrets)

        if (
            source_version
            and current_sha
            and source_version not in ("init", "error")
            and source_version != current_sha
        ):
            raise RuntimeError("The file was changed remotely. Please reload and try again.")

        new_sha = _write_github_csv(
            df,
            secrets,
            sha=None if source_version == "init" else source_version,
            message=commit_message,
        )
        return new_sha

    # Local mode
    _write_local_csv(df)
    return str(os.path.getmtime(LOCAL_PATH))