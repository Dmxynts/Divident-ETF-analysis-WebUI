"""
股债利差择时页面
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card, chart_card
from config import CFG

dash.register_page(__name__, path="/spread", name="股债利差择时")

INDEX_OPTIONS = list(set(etf.index_code for etf in CFG.etfs))
DEFAULT_INDEX = CFG.etfs[0].index_code


def layout():
    return html.Div([
        html.H3("股债利差择时分析", className="fw-bold mb-1"),
        html.P("红利指数股息率 — 十年期国债收益率，滚动分位判断高估/低估",
               className="text-muted mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("指数", className="fw-semibold small mb-1"),
                        dcc.Dropdown(
                            id="spread-index",
                            options=[{"label": f"{idx}", "value": idx} for idx in INDEX_OPTIONS],
                            value=DEFAULT_INDEX,
                            clearable=False,
                        ),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("回溯窗口", className="fw-semibold small mb-1"),
                        dcc.Slider(
                            id="spread-years", min=5, max=20, step=1, value=10,
                            marks={5: "5年", 10: "10年", 15: "15年", 20: "20年"},
                        ),
                    ], md=4),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button(
                            [html.I(className="bi bi-play-fill me-1"), "运行分析"],
                            id="spread-run", color="primary", size="lg",
                            className="w-100",
                        ),
                    ], md=4),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="spread-loading", type="circle", children=[
            html.Div(id="spread-output"),
        ]),
    ])


def _build_strategy_explanation():
    """策略说明卡片"""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="bi bi-info-circle me-2"),
            "策略说明",
        ]),
        dbc.CardBody([
            html.P(
                "核心逻辑：当股息率相对于国债收益率的利差处于历史高位时，"
                "权益资产配置价值凸显，应提高仓位；反之应降低仓位。",
                className="small mb-2",
            ),
            html.P(
                "滚动百分位计算：以过去 N 年（默认10年）为窗口，计算当前利差"
                "在历史序列中所处的百分位位置。",
                className="small mb-2",
            ),
            html.Div([
                html.Span("满仓阈值", className="fw-semibold small me-2"),
                html.Span("利差分位 ≥ 80%", className="badge bg-success me-3"),
                html.Span("轻仓阈值", className="fw-semibold small me-2"),
                html.Span("利差分位 ≤ 20%", className="badge bg-danger me-3"),
                html.Span("回溯窗口", className="fw-semibold small me-2"),
                html.Span("10年", className="badge bg-primary"),
            ]),
        ]),
    ])


def _build_charts(merged, signal, bt, metrics):
    """构建所有图表，返回 (fig1, fig2, fig3, fig4_or_None, metrics_rows)"""

    # 图1: 股息率 vs 国债收益率
    fig1 = go.Figure()
    dy_col = "dividend_yield" if "dividend_yield" in merged.columns else "div_yield"
    by_col = "yield" if "yield" in merged.columns else "bond_yield"
    if dy_col in merged.columns and by_col in merged.columns:
        dy_vals = merged[dy_col] * 100 if merged[dy_col].max() < 1 else merged[dy_col]
        by_vals = merged[by_col] * 100 if merged[by_col].max() < 1 else merged[by_col]
        fig1.add_trace(go.Scatter(
            x=merged["date"], y=dy_vals, mode="lines",
            name="股息率", line=dict(color="#e74c3c", width=2),
            hovertemplate="%{y:.2f}%<extra>股息率</extra>",
        ))
        fig1.add_trace(go.Scatter(
            x=merged["date"], y=by_vals, mode="lines",
            name="十年期国债收益率", line=dict(color="#3498db", width=2),
            hovertemplate="%{y:.2f}%<extra>国债收益率</extra>",
        ))
    fig1.update_layout(
        title=dict(text="中证红利股息率 vs 十年期国债收益率", font=dict(size=14)),
        yaxis_title="收益率 (%)", hovermode="x unified",
        height=320, margin=dict(l=50, r=20, t=50, b=30),
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # 图2: 股债利差
    spread_max = signal["spread"].max() * 100
    spread_min = signal["spread"].min() * 100
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=signal["date"], y=signal["spread"] * 100,
        mode="lines", name="利差", line=dict(color="#2c3e50", width=2),
        fill="tozeroy", fillcolor="rgba(74,124,247,0.08)",
        hovertemplate="%{y:.2f}%<extra>利差</extra>",
    ))
    fig2.add_hrect(y0=0, y1=spread_max, fillcolor="red", opacity=0.04, line_width=0)
    fig2.add_hrect(y0=spread_min, y1=0, fillcolor="green", opacity=0.04, line_width=0)
    fig2.add_hline(y=0, line=dict(color="rgba(0,0,0,0.15)", width=1, dash="dash"))
    fig2.update_layout(
        title=dict(text="股债利差 (股息率 - 国债收益率)", font=dict(size=14)),
        yaxis_title="利差 (%)", hovermode="x unified",
        height=320, margin=dict(l=50, r=20, t=50, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # 图3: 仓位信号
    fig3 = go.Figure()
    fig3.add_hrect(y0=0, y1=0.3, fillcolor="rgba(231,76,60,0.06)", line_width=0,
                   annotation_text="轻仓区", annotation_position="top left",
                   annotation_font_size=11, annotation_font_color="rgba(231,76,60,0.5)")
    fig3.add_hrect(y0=0.3, y1=0.7, fillcolor="rgba(232,146,10,0.05)", line_width=0,
                   annotation_text="中性区", annotation_position="top left",
                   annotation_font_size=11, annotation_font_color="rgba(232,146,10,0.5)")
    fig3.add_hrect(y0=0.7, y1=1.1, fillcolor="rgba(34,180,85,0.05)", line_width=0,
                   annotation_text="重仓区", annotation_position="top left",
                   annotation_font_size=11, annotation_font_color="rgba(34,180,85,0.5)")
    fig3.add_hline(y=0.3, line=dict(color="rgba(231,76,60,0.35)", width=1, dash="dash"))
    fig3.add_hline(y=0.7, line=dict(color="rgba(34,180,85,0.35)", width=1, dash="dash"))
    fig3.add_trace(go.Scatter(
        x=signal["date"], y=signal["position"],
        mode="lines", name="策略仓位",
        line=dict(color="#2c3e50", width=2.5),
        hovertemplate="%{y:.0%}<extra>仓位</extra>",
    ))
    fig3.update_layout(
        title=dict(text="策略仓位信号", font=dict(size=14)),
        yaxis_title="仓位比例",
        yaxis=dict(range=[0, 1.1], tickformat=".0%",
                   tickvals=[0, 0.3, 0.5, 0.7, 1.0]),
        hovermode="x unified",
        height=320, margin=dict(l=50, r=20, t=50, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # 图4: 净值图
    fig4 = None
    if bt is not None and not bt.empty and "date" in bt.columns:
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=bt["date"], y=bt["strategy_nav"],
            mode="lines", name="策略净值",
            line=dict(color="#e74c3c", width=2),
            hovertemplate="%{y:.4f}<extra>策略</extra>",
        ))
        fig4.add_trace(go.Scatter(
            x=bt["date"], y=bt["index_nav"],
            mode="lines", name="基准净值",
            line=dict(color="#3498db", width=1.5, dash="dash"),
            hovertemplate="%{y:.4f}<extra>基准</extra>",
        ))
        fig4.update_layout(
            title=dict(text="策略 vs 基准净值", font=dict(size=14)),
            yaxis_title="净值",
            hovermode="x unified",
            height=320, margin=dict(l=50, r=20, t=50, b=30),
            legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    # 回测指标行
    metrics_rows = []
    highlight_keys = {"年化收益率", "年化波动率", "夏普比率", "最大回撤", "胜率"}
    for k, v in metrics.items():
        if k == "年化收益率":
            v_str = f"{float(v.strip('%'))/100:.2%}" if isinstance(v, str) else f"{v:.2%}"
        else:
            v_str = str(v)
        highlight = k in highlight_keys
        metrics_rows.append(html.Tr([
            html.Td(k, className="small" if not highlight else "fw-semibold"),
            html.Td(v_str, className="fw-bold" if highlight else ""),
        ]))

    return fig1, fig2, fig3, fig4, metrics_rows


@callback(
    Output("spread-output", "children"),
    Input("spread-run", "n_clicks"),
    State("spread-index", "value"),
    State("spread-years", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, index_code, years):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("spread", index_code=index_code, years=years)
    except Exception as e:
        return error_alert(e)

    signal = result["signal"]
    metrics = result["metrics"]
    bt = result["backtest"]
    div_df = result["div_df"]
    bond_df = result["bond_df"]

    latest = signal.iloc[-1]

    merged = signal.merge(div_df, on="date", how="left").merge(bond_df, on="date", how="left")

    # 核心指标卡片
    pct_color = "success" if latest["percentile"] > 0.5 else "warning"
    signal_cards = dbc.Row([
        dbc.Col(stat_card(f"{latest['spread']:.2%}", "当前利差", "primary", "graph-up-arrow"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{latest['percentile']:.1%}", "历史分位", pct_color, "percent"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{latest['position']:.0%}", "建议仓位", "success", "pie-chart"), md=3, className="mb-3"),
        dbc.Col(stat_card(latest["signal"], "操作信号", "warning", "flag"), md=3, className="mb-3"),
    ])

    fig1, fig2, fig3, fig4, metrics_rows = _build_charts(merged, signal, bt, metrics)
    metrics_table = info_table(["指标", "数值"], metrics_rows)

    # 策略说明 + 回测指标
    bottom_left = html.Div([
        _build_strategy_explanation(),
        table_card("回测指标", metrics_table, "bar-chart-line"),
    ])

    return html.Div([
        section_header("当前信号", "flag", "股债利差最新数值与操作信号"),
        signal_cards,
        html.Hr(className="my-2"),

        section_header("核心走势", "graph-up", "股息率、国债收益率与股债利差历史走势"),
        dbc.Row([
            dbc.Col(chart_card(fig1, "股息率 vs 国债收益率"), md=6, className="mb-3"),
            dbc.Col(chart_card(fig2, "股债利差"), md=6, className="mb-3"),
        ]),
        dbc.Row([
            dbc.Col(chart_card(fig3, "策略仓位信号"), md=12, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("策略回测", "bar-chart-line", "策略 vs 基准净值与绩效指标"),
        dbc.Row([
            dbc.Col(bottom_left, md=6, className="mb-3"),
            dbc.Col(chart_card(fig4, "策略 vs 基准净值") if fig4 else html.Div(), md=6, className="mb-3"),
        ]),
    ])
