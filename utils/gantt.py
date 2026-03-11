import plotly.express as px
import pandas as pd

STATUS_COLOR_MAP = {
    "Not Started": "#9aa0a6",
    "In Progress": "#1e88e5",
    "Blocked": "#d32f2f",
    "At Risk": "#f57c00",
    "Done": "#2e7d32",
}

def make_gantt(df: pd.DataFrame, color_by: str = "Status"):
    if df.empty:
        return None

    gdf = df.copy()
    gdf = gdf[gdf["Start"].notna() & gdf["Finish"].notna()]
    if gdf.empty:
        return None

    # Order by module and start
    gdf = gdf.sort_values(by=["Module", "Start", "Finish", "Task"], ascending=[True, True, True, True])
    y_labels = gdf.apply(lambda r: f"[{r['Module']}] {r['Task']}", axis=1)

    if color_by == "Progress":
        color = "Progress"
        color_discrete_map = None
    else:
        color = "Status"
        color_discrete_map = STATUS_COLOR_MAP

    fig = px.timeline(
        gdf,
        x_start="Start",
        x_end="Finish",
        y=y_labels,
        color=color,
        color_discrete_map=color_discrete_map,
        hover_data={"Owner": True, "DependsOn": True, "Notes": True, "Progress": True, "Status": True},
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        margin=dict(l=20, r=20, t=30, b=20),
        hoverlabel=dict(bgcolor="white"),
        legend_title_text=color,
        xaxis_title="Date",
        yaxis_title="Tasks",
    )
    return fig