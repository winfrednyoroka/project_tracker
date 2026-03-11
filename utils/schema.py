from dataclasses import dataclass
from typing import List
import pandas as pd
import uuid

STATUS_OPTIONS: List[str] = ["Not Started", "In Progress", "Blocked", "At Risk", "Done"]

COLUMNS = [
    "ID", "Module", "Task", "Owner", "Start", "Finish",
    "Progress", "Status", "DependsOn", "Notes", "LastUpdated"
]

DATE_COLS = ["Start", "Finish", "LastUpdated"]

def new_id() -> str:
    return uuid.uuid4().hex[:8]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    # Add missing columns
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Normalize types
    for col in ["Module", "Task", "Owner", "Status", "DependsOn", "Notes"]:
        df[col] = df[col].astype("string").fillna("")

    # ID
    if "ID" in df.columns:
        df["ID"] = df["ID"].astype("string")
        mask_empty = df["ID"].isna() | (df["ID"] == "")
        if mask_empty.any():
            df.loc[mask_empty, "ID"] = [new_id() for _ in range(mask_empty.sum())]

    # Progress
    df["Progress"] = pd.to_numeric(df["Progress"], errors="coerce").fillna(0).clip(0, 100).astype(int)

    # Status
    df["Status"] = df["Status"].where(df["Status"].isin(STATUS_OPTIONS), "Not Started")

    # Dates
    for d in DATE_COLS:
        df[d] = pd.to_datetime(df[d], errors="coerce")

    # Ensure Start <= Finish when both set
    mask = df["Start"].notna() & df["Finish"].notna() & (df["Finish"] < df["Start"])
    df.loc[mask, "Finish"] = df.loc[mask, "Start"]

    # LastUpdated default
    now = pd.Timestamp.utcnow()
    df["LastUpdated"] = df["LastUpdated"].fillna(now)
    return df[COLUMNS]