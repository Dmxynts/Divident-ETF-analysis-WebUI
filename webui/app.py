"""
红利ETF量化分析系统 - WebUI 入口
玻璃拟态风格 · 基于 Dash + dash-bootstrap-components
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

import plotly.io as pio
import plotly.graph_objects as go
import dash
from dash import Dash, html, dcc, Input, Output
import dash_bootstrap_components as dbc
from webui.state import state as app_state

# -----------------------------------------------------------
# Plotly 模板 — 透明背景适配亮色玻璃拟态
# -----------------------------------------------------------
# 保留 plotly_white 的配色，去除实色背景，使图表在
# 毛玻璃容器上透出渐变底纹，所有显式使用 template="plotly_white" 的图表自动生效
_glass_patch = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(0,0,0,0.70)", size=12),
        title=dict(font=dict(color="rgba(0,0,0,0.88)", size=16)),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0.06)",
            zerolinecolor="rgba(0,0,0,0.10)",
            linecolor="rgba(0,0,0,0.08)",
            tickfont=dict(color="rgba(0,0,0,0.45)"),
        ),
        yaxis=dict(
            gridcolor="rgba(0,0,0,0.06)",
            zerolinecolor="rgba(0,0,0,0.10)",
            linecolor="rgba(0,0,0,0.08)",
            tickfont=dict(color="rgba(0,0,0,0.45)"),
        ),
        legend=dict(
            font=dict(color="rgba(0,0,0,0.70)"),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="rgba(255,255,255,0.92)",
            font=dict(color="rgba(0,0,0,0.88)", size=12),
            bordercolor="rgba(0,0,0,0.08)",
        ),
        colorway=pio.templates["plotly_white"]
        .layout.colorway
        or [
            "#636efa",
            "#EF553B",
            "#00cc96",
            "#ab63fa",
            "#FFA15A",
            "#19d3f3",
            "#FF6692",
            "#B6E880",
            "#FF97FF",
            "#FECB52",
        ],
    )
)
pio.templates["plotly_white"] = _glass_patch

# -----------------------------------------------------------
# Dash App 初始化
# -----------------------------------------------------------
_pages_dir = Path(__file__).parent / "pages"

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=str(_pages_dir),
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        dbc.icons.FONT_AWESOME,
    ],
    suppress_callback_exceptions=True,
    title="红利ETF量化分析系统",
    update_title="加载中...",
)

# -----------------------------------------------------------
# 侧边栏导航
# -----------------------------------------------------------
NAV_ITEMS = [
    ("/", "house-fill", "总览"),
    ("/spread", "graph-up-arrow", "股债利差择时"),
    ("/macro", "globe2", "宏观状态识别"),
    ("/volatility", "activity", "波动率分析"),
    ("/risk", "shield-exclamation", "风险管理"),
    ("/grid", "grid-3x3-gap-fill", "网格交易优化"),
    ("/factor", "pie-chart-fill", "因子归因"),
    ("/timing", "clock-history", "综合择时"),
]

sidebar = html.Div(
    [
        html.Div(
            [
                html.H5("红利ETF", className="fw-bold mb-0", style={"color": "#1a73e8"}),
                html.Span("量化分析系统", className="text-muted small"),
            ],
            className="text-center py-3",
        ),
        html.Hr(className="my-2"),
        dbc.Nav(
            [
                dbc.NavLink(
                    [html.I(className=f"bi bi-{icon} me-2"), label],
                    href=href,
                    active="exact",
                    className="nav-link-custom",
                )
                for href, icon, label in NAV_ITEMS
            ],
            vertical=True,
            pills=True,
            className="px-2",
        ),
        html.Hr(className="my-2"),
        dbc.Button(
            [html.I(className="bi bi-arrow-clockwise me-2"), "更新数据"],
            id="sidebar-update-btn",
            color="primary",
            size="sm",
            className="w-75 mx-auto d-block",
            n_clicks=0,
        ),
        html.Div(id="sidebar-update-status", className="text-center small", style={"minHeight": "20px"}),
        html.Hr(className="my-2"),
        html.Div(
            [
                html.Small("数据来源: AKShare", className="text-muted d-block"),
                html.Small("仅供研究参考，不构成投资建议",
                          className="text-muted d-block"),
            ],
            className="text-center px-2 small",
        ),
    ],
    className="sidebar d-flex flex-column h-100 py-2",
)

# -----------------------------------------------------------
# 主布局
# -----------------------------------------------------------
app.layout = dbc.Container(
    [
        dbc.Row(
            [
                dbc.Col(sidebar, width=2, className="vh-100 overflow-auto p-0"),
                dbc.Col(
                    html.Div(dash.page_container, className="p-4"),
                    width=10,
                    className="vh-100 overflow-auto",
                ),
            ],
            className="g-0",
        ),
    ],
    fluid=True,
    className="vh-100 p-0",
)

# -----------------------------------------------------------
# 入口
# -----------------------------------------------------------

@app.callback(
    Output("sidebar-update-status", "children"),
    Input("sidebar-update-btn", "n_clicks"),
    prevent_initial_call=True,
)
def update_data(n_clicks):
    """清除缓存，下次访问页面时自动拉取最新数据"""
    try:
        app_state.system.fetcher.clear_cache()
        app_state.clear_cache()
        return html.Span("✓ 缓存已清除，数据将在下次加载时更新",
                        className="text-success small",
                        style={"animation": "fadeOut 3s forwards"})
    except Exception as e:
        return html.Span(f"✗ {e}", className="text-danger small")


if __name__ == "__main__":
    import webbrowser
    import os
    # debug=True 时 Werkzeug 重载器会重启进程，只让主进程打开一次浏览器
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open("http://127.0.0.1:8051")
    app.run(debug=True, host="127.0.0.1", port=8051)
