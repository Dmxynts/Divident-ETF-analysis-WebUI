"""
总览页面 - Dashboard 首页
"""
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from config import CFG
from webui.state import state as app_state, error_alert

dash.register_page(__name__, path="/", name="总览")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
DEFAULT_ETF = CFG.etfs[0].code

MODULES = [
    {"path": "/spread", "icon": "graph-up-arrow", "title": "股债利差择时",
     "desc": "红利股息率 vs 十年期国债收益率，滚动分位判断高估/低估"},
    {"path": "/macro", "icon": "globe2", "title": "宏观状态识别",
     "desc": "HMM 模型划分复苏/过热/滞胀/衰退四阶段"},
    {"path": "/volatility", "icon": "activity", "title": "波动率分析",
     "desc": "GARCH/EGARCH 建模 + 3-Sigma 极端事件检测"},
    {"path": "/risk", "icon": "shield-exclamation", "title": "风险管理",
     "desc": "VaR/ES、EVT极值理论、回撤监控、压力测试"},
    {"path": "/grid", "icon": "grid-3x3-gap-fill", "title": "网格交易优化",
     "desc": "卡尔曼滤波 + ATR 确定网格参数，含滑点模拟"},
    {"path": "/factor", "icon": "pie-chart-fill", "title": "因子归因",
     "desc": "时间序列多因子回归，拆解 ETF 收益来源"},
    {"path": "/timing", "icon": "clock-history", "title": "综合择时",
     "desc": "融合股债利差+宏观+波动率+动量的综合信号"},
]


def module_card(mod):
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.I(className=f"bi bi-{mod['icon']} me-2 fs-4",
                       style={"color": "#1a73e8"}),
                html.H5(mod["title"], className="card-title d-inline"),
            ]),
            html.P(mod["desc"], className="card-text text-muted small mt-2"),
            dbc.Button("进入", href=mod["path"], color="primary", size="sm"),
        ]),
        className="h-100 shadow-sm",
    )


def layout():
    return html.Div([
        dbc.Row([
            dbc.Col([
                html.H2("红利ETF量化分析系统", className="fw-bold"),
                html.P("基于金融工程方法的 A股红利ETF 研究与交易决策支持系统",
                       className="text-muted lead"),
            ]),
        ], className="mb-4"),

        # ETF 价格走势图
        dbc.Card([
            dbc.CardHeader([
                html.I(className="bi bi-graph-up me-2"),
                "ETF 价格走势",
            ]),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("选择 ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="home-etf", options=ETF_OPTIONS, value=DEFAULT_ETF, clearable=False),
                    ], md=3, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="home-years", min=1, max=10, step=1, value=5,
                                   marks={1: "1年", 3: "3年", 5: "5年", 10: "10年"}),
                    ], md=6),
                ]),
                dcc.Loading(id="home-chart-loading", type="circle", children=[
                    html.Div(id="home-chart"),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        # 模块入口
        html.H5("分析模块", className="mb-3"),
        dbc.Row(
            [
                dbc.Col(module_card(mod), md=4, sm=6, className="mb-3")
                for mod in MODULES
            ],
        ),
    ])


@callback(
    Output("home-chart", "children"),
    Input("home-etf", "value"),
    Input("home-years", "value"),
)
def update_chart(etf_code, years):
    if not etf_code:
        return html.Div()

    try:
        start_date = (__import__("datetime").datetime.now() - __import__("datetime").timedelta(days=365 * years)).strftime("%Y%m%d")
        df = app_state.system.fetcher.get_etf_daily(etf_code, start_date)
    except Exception as e:
        return error_alert(e)

    if df is None or df.empty:
        return html.Div(html.Small("暂无数据", className="text-muted"))

    # 最新一日数据
    last = df.iloc[-1]
    last_date = str(last["date"])[:10]
    last_close = last["close"]
    prev_close = df.iloc[-2]["close"] if len(df) > 1 else last_close
    change_pct = (last_close - prev_close) / prev_close * 100
    arrow = "▲" if change_pct >= 0 else "▼"
    clr = "#22b455" if change_pct >= 0 else "#e74c3c"

    has_hl = "high" in df.columns and "low" in df.columns
    fig = go.Figure()

    if has_hl:
        fig.add_trace(go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"],
            name="K线", increasing_line_color="#22b455", decreasing_line_color="#e74c3c",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["close"], mode="lines",
            name="收盘价", line=dict(color="#4a7cf7", width=2),
        ))

    # 成交量
    if "volume" in df.columns:
        fig.add_trace(go.Bar(
            x=df["date"], y=df["volume"],
            name="成交量", marker_color="rgba(74,124,247,0.15)",
            yaxis="y2", opacity=0.5,
        ))

    fig.update_layout(
        title=dict(
            text=(f"{etf_code}  &nbsp; "
                  f"<span style='color:{clr};font-size:26px'>{last_close:.3f}</span>"
                  f"<span style='color:{clr};font-size:16px'> {arrow} {abs(change_pct):.2f}%</span>"
                  f"<span style='color:gray;font-size:14px'> &nbsp; {last_date}</span>"),
            font=dict(size=16), y=0.92,
        ),
        xaxis_title="日期", yaxis_title="价格",
        template="plotly_white", hovermode="x unified",
        height=520,
        margin=dict(l=40, r=30, t=75, b=30),
        legend=dict(orientation="h", y=1.02),
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(rangeslider=dict(visible=False)),
    )

    if "volume" in df.columns:
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", showgrid=False, visible=False),
        )

    return dcc.Graph(figure=fig, className="rounded", style={"height": "540px"})
