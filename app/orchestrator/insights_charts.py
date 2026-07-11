"""인사이트 화면용 Plotly figure JSON 빌더.

``stats_charts.py`` 와 같은 규약(서버가 figure JSON 생성 → 프론트가 Plotly.js 로 렌더)을 따르며,
공통 레이아웃/색/빈-figure 헬퍼를 재사용한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import plotly.graph_objects as go

from app.orchestrator.stats_charts import (
    AXIS,
    COLORWAY,
    FONT_FAMILY,
    GREEN,
    INDIGO,
    RED,
    TEXT,
    _axis_style,
    _axis_title,
    _base_layout,
    _empty_figure,
)

AMBER = "#fab219"


def _fmt_minutes(ms_values: list[int]) -> list[float]:
    return [round(v / 1000, 1) for v in ms_values]


def health_trend_chart(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """일별 통과율(좌축, 선) + 일별 평균소요(우축, 선) 2단 추이."""
    rows = [d for d in daily if d.get("pass_rate") is not None or d.get("avg_duration_ms")]
    if not rows:
        return _empty_figure()

    dates = [d["date"] for d in daily]
    pass_rates = [d["pass_rate"] for d in daily]
    durations = [
        round(d["avg_duration_ms"] / 1000, 1) if d.get("avg_duration_ms") else None for d in daily
    ]

    fig = go.Figure(
        data=[
            go.Scatter(
                name="통과율",
                x=dates,
                y=pass_rates,
                mode="lines+markers",
                line=dict(color=INDIGO, width=2.5, shape="spline"),
                marker=dict(size=5, color=INDIGO),
                connectgaps=True,
                hovertemplate="<b>%{x}</b><br>통과율 %{y}%<extra></extra>",
            ),
            go.Scatter(
                name="평균 소요",
                x=dates,
                y=durations,
                mode="lines+markers",
                yaxis="y2",
                line=dict(color=AMBER, width=2, dash="dot", shape="spline"),
                marker=dict(size=4, color=AMBER),
                connectgaps=True,
                hovertemplate="<b>%{x}</b><br>평균 소요 %{y}s<extra></extra>",
            ),
        ]
    )
    fig.update_layout(
        **_base_layout(height=300),
        xaxis=dict(**_axis_style(showgrid=False)),
        yaxis=dict(title="통과율 %", range=[0, 105], **_axis_style()),
        yaxis2=dict(
            title="소요(초)",
            overlaying="y",
            side="right",
            rangemode="tozero",
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=11, color=AXIS, family=FONT_FAMILY),
        ),
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


def calendar_heatmap_chart(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """일별 통과율 캘린더 히트맵(요일 × 주)."""
    dated = [d for d in daily if d.get("date")]
    if not dated:
        return _empty_figure()

    parsed = [(datetime.strptime(d["date"], "%Y-%m-%d").date(), d) for d in dated]
    first_date = parsed[0][0]
    first_monday = first_date - timedelta(days=first_date.weekday())
    week_count = ((parsed[-1][0] - first_monday).days // 7) + 1

    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    z: list[list[float | None]] = [[None] * week_count for _ in range(7)]
    text: list[list[str]] = [["" for _ in range(week_count)] for _ in range(7)]
    week_starts = [first_monday + timedelta(weeks=w) for w in range(week_count)]
    x_labels = [ws.strftime("%m/%d") for ws in week_starts]

    for day, entry in parsed:
        week = (day - first_monday).days // 7
        weekday = day.weekday()
        rate = entry.get("pass_rate")
        z[weekday][week] = rate
        if rate is None:
            text[weekday][week] = f"{day.strftime('%m/%d')}<br>미점검"
        else:
            text[weekday][week] = (
                f"{day.strftime('%m/%d')}<br>통과율 {rate}%<br>Run {entry.get('run_count', 0)}건"
            )

    fig = go.Figure(
        data=[
            go.Heatmap(
                z=z,
                x=x_labels,
                y=weekday_labels,
                text=text,
                hovertemplate="%{text}<extra></extra>",
                zmin=0,
                zmax=100,
                colorscale=[[0.0, RED], [0.8, AMBER], [1.0, GREEN]],
                xgap=3,
                ygap=3,
                showscale=True,
                colorbar=dict(
                    title="",
                    thickness=8,
                    len=0.8,
                    tickfont=dict(size=10, color=AXIS, family=FONT_FAMILY),
                ),
                hoverongaps=False,
            )
        ]
    )
    fig.update_layout(
        **_base_layout(height=200),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=10, color=AXIS)),
        yaxis=dict(
            autorange="reversed",
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=11, color=TEXT, family=FONT_FAMILY),
        ),
    )
    return fig.to_plotly_json()


def module_duration_sparkline(series: list[dict[str, Any]]) -> dict[str, Any]:
    """모듈 소요시간 추이 스파크라인(축·범례 최소화)."""
    if not series:
        return _empty_figure("소요 데이터 없음")

    x = [s["at"] for s in series]
    y = [round(s["duration_ms"] / 1000, 1) for s in series]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                line=dict(color=INDIGO, width=2, shape="spline"),
                marker=dict(size=4, color=INDIGO),
                fill="tozeroy",
                fillcolor="rgba(79,70,229,0.08)",
                hovertemplate="%{y}s<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_base_layout(height=140),
        xaxis=dict(visible=False),
        yaxis=dict(title="", rangemode="tozero", **_axis_style()),
        showlegend=False,
    )
    return fig.to_plotly_json()


def failure_category_donut(categories: list[dict[str, Any]]) -> dict[str, Any]:
    """실패 유형 분포 도넛."""
    rows = [c for c in categories if c.get("count", 0) > 0]
    if not rows:
        return _empty_figure("실패 이력 없음")

    labels = [c["label"] for c in rows]
    values = [c["count"] for c in rows]
    colors = [COLORWAY[i % len(COLORWAY)] for i in range(len(rows))]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="value",
                textfont=dict(size=11, color="#ffffff", family=FONT_FAMILY),
                hovertemplate="<b>%{label}</b><br>%{value}건 (%{percent})<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_base_layout(height=220),
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.02,
            font=dict(size=10, color=TEXT, family=FONT_FAMILY),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig.to_plotly_json()


def cumulative_step_duration_bar(cumulative: list[dict[str, Any]]) -> dict[str, Any]:
    """단계별(모듈) 평균 누적 소요 가로 막대 — 어느 단계가 시간을 잡아먹는지."""
    rows = [c for c in cumulative if (c.get("avg_duration_ms") or 0) > 0]
    if not rows:
        return _empty_figure("소요 데이터 없음")

    labels = [c["name"] for c in rows]
    seconds = _fmt_minutes([c["avg_duration_ms"] for c in rows])

    fig = go.Figure(
        data=[
            go.Bar(
                y=labels,
                x=seconds,
                orientation="h",
                marker=dict(
                    color=seconds,
                    colorscale=[[0, "#c7d2fe"], [1, INDIGO]],
                    cornerradius=6,
                    line=dict(width=0),
                ),
                hovertemplate="<b>%{y}</b><br>평균 %{x}s<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        **_base_layout(height=max(220, 44 * len(rows))),
        bargap=0.32,
        xaxis=dict(title=_axis_title("초"), **_axis_style()),
        yaxis=dict(autorange="reversed", **_axis_style(showgrid=False)),
        showlegend=False,
    )
    return fig.to_plotly_json()
