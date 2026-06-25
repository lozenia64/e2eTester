"""Plotly 기반 사용량 통계 차트 빌더.

서버에서 Plotly figure JSON을 생성하고, 프론트엔드는 Plotly.js로 렌더링한다.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from app.core.models import SystemUsageStat, UsageStats, UserUsageStat

FONT_FAMILY = "Pretendard Variable, Pretendard, Noto Sans KR, sans-serif"
COLORWAY = [
    "#4f46e5",
    "#6366f1",
    "#818cf8",
    "#a5b4fc",
    "#7c3aed",
    "#0284c7",
    "#0ea5e9",
    "#059669",
]
GREEN = "#16a34a"
RED = "#dc2626"
INDIGO = "#4f46e5"
GRID = "#f3f4f6"
AXIS = "#9ca3af"
TEXT = "#374151"


def _base_layout(*, height: int = 280) -> dict[str, Any]:
    return dict(
        font=dict(family=FONT_FAMILY, size=12, color=TEXT),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=12, t=12, b=12),
        height=height,
        hoverlabel=dict(
            bgcolor="#111827",
            bordercolor="#1f2937",
            font=dict(size=12, family=FONT_FAMILY, color="#f9fafb"),
        ),
        colorway=COLORWAY,
    )


def _empty_figure(message: str = "표시할 데이터가 없습니다.") -> dict[str, Any]:
    fig = go.Figure()
    fig.update_layout(
        **_base_layout(),
        annotations=[
            dict(
                text=message,
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=14, color="#9ca3af", family=FONT_FAMILY),
            )
        ],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig.to_plotly_json()


def _axis_style(*, showgrid: bool = True) -> dict[str, Any]:
    return dict(
        showgrid=showgrid,
        gridcolor=GRID,
        gridwidth=1,
        zeroline=False,
        tickfont=dict(size=11, color=AXIS, family=FONT_FAMILY),
        linecolor="#e5e7eb",
        linewidth=1,
    )


def _system_runs_chart(by_system: list[SystemUsageStat]) -> dict[str, Any]:
    rows = [s for s in by_system if s.runs > 0]
    if not rows:
        return _empty_figure()

    labels = [s.system_name for s in rows]
    values = [s.runs for s in rows]
    colors = [COLORWAY[i % len(COLORWAY)] for i in range(len(rows))]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.58,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="percent",
                textposition="outside",
                textfont=dict(size=11, color=TEXT, family=FONT_FAMILY),
                hovertemplate="<b>%{label}</b><br>Run %{value}건<br>%{percent}<extra></extra>",
                pull=[0.02] * len(rows),
            )
        ]
    )
    fig.update_layout(
        **_base_layout(),
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            font=dict(size=11, color=TEXT, family=FONT_FAMILY),
            bgcolor="rgba(0,0,0,0)",
        ),
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    return fig.to_plotly_json()


def _user_runs_chart(by_user: list[UserUsageStat]) -> dict[str, Any]:
    rows = sorted(
        [u for u in by_user if u.total_runs > 0],
        key=lambda u: u.total_runs,
        reverse=True,
    )[:10]
    if not rows:
        return _empty_figure()

    labels = [u.user_name or "(시스템)" for u in rows]
    values = [u.total_runs for u in rows]

    fig = go.Figure(
        data=[
            go.Bar(
                y=labels,
                x=values,
                orientation="h",
                marker=dict(
                    color=values,
                    colorscale=[[0, "#c7d2fe"], [1, INDIGO]],
                    cornerradius=6,
                    line=dict(width=0),
                ),
                hovertemplate="<b>%{y}</b><br>Run %{x}건<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_base_layout(),
        bargap=0.28,
        xaxis=dict(title="", **_axis_style()),
        yaxis=dict(autorange="reversed", **_axis_style(showgrid=False)),
        showlegend=False,
    )
    return fig.to_plotly_json()


def _system_savings_chart(by_system: list[SystemUsageStat]) -> dict[str, Any]:
    rows = [s for s in by_system if (s.manual_seconds_saved or 0) > 0]
    if not rows:
        return _empty_figure()

    labels = [s.system_name for s in rows]
    minutes = [round((s.manual_seconds_saved or 0) / 60, 1) for s in rows]

    fig = go.Figure(
        data=[
            go.Bar(
                y=labels,
                x=minutes,
                orientation="h",
                marker=dict(
                    color=minutes,
                    colorscale=[[0, "#bbf7d0"], [1, GREEN]],
                    cornerradius=6,
                    line=dict(width=0),
                ),
                hovertemplate="<b>%{y}</b><br>절감 %{x}분<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_base_layout(),
        bargap=0.28,
        xaxis=dict(title="분", titlefont=dict(size=11, color=AXIS), **_axis_style()),
        yaxis=dict(autorange="reversed", **_axis_style(showgrid=False)),
        showlegend=False,
    )
    return fig.to_plotly_json()


def _module_pass_fail_chart(by_system: list[SystemUsageStat]) -> dict[str, Any]:
    rows = [s for s in by_system if s.modules_passed > 0 or s.modules_failed > 0]
    if not rows:
        return _empty_figure()

    labels = [s.system_name for s in rows]
    passed = [s.modules_passed for s in rows]
    failed = [s.modules_failed for s in rows]

    fig = go.Figure(
        data=[
            go.Bar(
                name="통과",
                x=labels,
                y=passed,
                marker=dict(color=GREEN, cornerradius=4, line=dict(width=0)),
                hovertemplate="<b>%{x}</b><br>통과 %{y}건<extra></extra>",
            ),
            go.Bar(
                name="실패",
                x=labels,
                y=failed,
                marker=dict(color=RED, cornerradius=4, line=dict(width=0)),
                hovertemplate="<b>%{x}</b><br>실패 %{y}건<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        **_base_layout(),
        barmode="stack",
        bargap=0.32,
        xaxis=dict(**_axis_style(showgrid=False)),
        yaxis=dict(**_axis_style()),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color=TEXT, family=FONT_FAMILY),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig.to_plotly_json()


def build_usage_charts(stats: UsageStats) -> dict[str, Any]:
    return {
        "chart-system-runs": _system_runs_chart(stats.by_system),
        "chart-user-runs": _user_runs_chart(stats.by_user),
        "chart-system-savings": _system_savings_chart(stats.by_system),
        "chart-module-pass-fail": _module_pass_fail_chart(stats.by_system),
    }
