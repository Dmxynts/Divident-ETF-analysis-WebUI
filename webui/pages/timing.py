"""
综合择时页面 — 优化布局
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, chart_card
from config import CFG

dash.register_page(__name__, path="/timing", name="综合择时")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
INDEX_OPTIONS = list(set(etf.index_code for etf in CFG.etfs))
DEFAULT_ETF = CFG.etfs[0].code
DEFAULT_INDEX = CFG.etfs[0].index_code


def layout():
    return html.Div([
        html.Div([
            html.H3("综合择时系统", className="fw-bold mb-1"),
            html.P("融合股债利差 + 宏观状态 + 波动率 + 动量信号的综合仓位建议",
                   className="text-muted mb-0"),
        ], className="mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="timing-etf",
                                     options=ETF_OPTIONS, value=DEFAULT_ETF,
                                     clearable=False),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("参考指数", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="timing-index",
                                     options=[{"label": idx, "value": idx} for idx in INDEX_OPTIONS],
                                     value=DEFAULT_INDEX, clearable=False),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("　", className="fw-semibold small mb-1"),
                        dbc.Button(
                            [html.I(className="bi bi-play-fill me-1"), "一键综合评估"],
                            id="timing-run", color="primary", size="lg",
                            className="w-100",
                        ),
                    ], md=4),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="timing-loading", type="circle", color="#4a7cf7", children=[
            html.Div(id="timing-output"),
        ]),
    ])


def _build_indicator_cards(signal):
    """构建4个核心指标卡片"""
    score = signal.composite_score
    score_color = "success" if score >= 0.5 else "primary" if score >= 0 else "warning" if score >= -0.5 else "danger"
    action_color = {
        "满仓/加仓": "success", "增持": "primary",
        "持有": "info", "减仓": "warning", "清仓/轻仓": "danger",
    }.get(signal.action, "secondary")

    return dbc.Row([
        dbc.Col(stat_card(f"{score:+.3f}", "综合评分", score_color, "speedometer2"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{signal.position:.0%}", "建议仓位", "success", "pie-chart"), md=3, className="mb-3"),
        dbc.Col(stat_card(signal.action, "操作建议", action_color, "arrow-up-circle"), md=3, className="mb-3"),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.I(className="bi bi-info-circle me-2", style={"color": "var(--accent-blue)"}),
                html.Small(signal.explanation, className="text-muted"),
            ], className="d-flex align-items-center"),
        ], className="shadow-sm h-100", style={"borderRadius": "var(--glass-radius, 14px)"}), md=3, className="mb-3"),
    ])


def _build_score_figures(signal):
    """构建实心圆环评分和维度得分图"""
    score = signal.composite_score
    normalized = max(0, min(1, (score + 1) / 2))
    bar_color = "#22b455" if score >= 0.5 else "#4a7cf7" if score >= 0 else "#e8920a" if score >= -0.5 else "#e74c3c"

    gauge_fig = go.Figure()
    gauge_fig.add_trace(go.Pie(
        values=[normalized, 1 - normalized],
        hole=0.72,
        marker=dict(colors=[bar_color, "rgba(0,0,0,0.05)"]),
        textinfo="none",
        hoverinfo="none",
        showlegend=False,
        sort=False,
        direction="clockwise",
        rotation=90,
    ))
    gauge_fig.update_layout(
        template="plotly_white",
        height=220,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(text=f"{score:+.3f}", x=0.5, y=0.48,
                 font=dict(size=28, color=bar_color),
                 showarrow=False, xref="paper", yref="paper"),
            dict(text="综合评分", x=0.5, y=0.38,
                 font=dict(size=12, color="rgba(0,0,0,0.4)"),
                 showarrow=False, xref="paper", yref="paper"),
        ],
    )

    details = signal.details
    detail_labels = {
        "spread_score": "股债利差", "macro_score": "宏观状态",
        "vol_score": "波动率", "momentum_score": "动量",
        "vol_level": "波动率水平", "vol_trend": "波动率趋势",
        "vol_forecast": "波动率预测", "vol_event": "波动率事件",
    }
    labels = [detail_labels.get(k, k) for k in details.keys()]
    values = list(details.values())
    bar_colors = ["#22b455" if v >= 0 else "#e74c3c" for v in values]

    score_fig = go.Figure()
    score_fig.add_trace(go.Bar(
        y=labels, x=values, orientation="h",
        marker_color=bar_colors,
        text=[f"{v:+.3f}" for v in values],
        textposition="outside",
        textfont={"size": 12, "color": "rgba(0,0,0,0.6)"},
        hovertemplate="%{y}: %{x:+.3f}<extra></extra>",
    ))
    score_fig.update_layout(
        title=dict(text="各维度得分", font=dict(size=16, color="rgba(0,0,0,0.7)")),
        template="plotly_white",
        height=max(300, len(labels) * 42 + 60),
        margin=dict(l=130, r=60, t=50, b=20),
        xaxis=dict(range=[-1, 1], zeroline=True,
                   zerolinecolor="rgba(0,0,0,0.08)",
                   tickfont={"size": 10}),
        yaxis=dict(tickfont={"size": 12}),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "rgba(0,0,0,0.65)"},
        hovermode="y",
    )

    return gauge_fig, score_fig


def _build_bottom_row(signal, allocation, budget_card):
    """构建底部三栏：ETF配置 + 检查清单 + 风险预算"""
    alloc_items = []
    for a in allocation:
        w = a.get("权重", 0)
        if w > 0:
            etf_name = a.get("ETF", "")
            etf_code = a.get("代码", "")
            pct = f"{w:.0%}"
            alloc_items.append(html.Div([
                html.Div([
                    html.Span(etf_name, className="fw-semibold small"),
                    html.Span(etf_code,
                             className="text-muted small ms-2"),
                ]),
                html.Div([
                    dbc.Progress(value=w * 100, color="primary",
                                 className="flex-grow-1 me-2",
                                 style={"height": "8px"}),
                    html.Span(pct, className="fw-bold small",
                             style={"minWidth": "40px", "textAlign": "right"}),
                ], className="d-flex align-items-center mt-1"),
            ], className="mb-2")),
    alloc_section = dbc.Card([
        dbc.CardHeader([
            html.I(className="bi bi-briefcase-fill me-2"),
            "ETF 配置建议",
        ]),
        dbc.CardBody(
            alloc_items if alloc_items else [
                html.Span("暂无配置建议", className="text-muted small")
            ]
        ),
    ], className="h-100")

    if signal.position >= 0.7:
        checklist_lines = [
            ("重仓持有", "当前适合重仓持有红利ETF"),
            ("逢跌加仓", "若遇恐慌下跌（波动率骤升），可适当加仓"),
            ("关注利差", "关注国债收益率变化，利差收窄需警惕"),
        ]
    elif signal.position >= 0.4:
        checklist_lines = [
            ("中性持有", "正常持有，保持中性仓位"),
            ("关注数据", "关注PMI、M1-M2剪刀差变化"),
            ("小步加仓", "若有显著回调，可小步加仓"),
        ]
    else:
        checklist_lines = [
            ("降低仓位", "建议降低红利ETF仓位"),
            ("防御配置", "转向短债/货币基金等防御资产"),
            ("等待信号", "等待利差或宏观信号好转再入场"),
        ]

    checklist_items = []
    for i, (title, desc) in enumerate(checklist_lines, 1):
        checklist_items.append(html.Div([
            html.Div([
                html.Span(str(i), className="fw-bold",
                         style={
                             "width": "26px", "height": "26px",
                             "borderRadius": "50%",
                             "background": "rgba(74,124,247,0.12)",
                             "color": "var(--accent-blue)",
                             "display": "inline-flex",
                             "alignItems": "center",
                             "justifyContent": "center",
                             "fontSize": "0.8rem",
                         }),
                html.Span(title, className="fw-semibold ms-2 small"),
            ]),
            html.P(desc, className="text-muted small mt-1 mb-0",
                  style={"paddingLeft": "34px"}),
        ], className="mb-2"))
        if i < len(checklist_lines):
            checklist_items.append(html.Hr(className="my-2 opacity-50"))

    checklist_section = dbc.Card([
        dbc.CardHeader([
            html.I(className="bi bi-check2-square me-2"),
            "操作检查清单",
        ]),
        dbc.CardBody(checklist_items),
    ], className="h-100")

    budget_section = dbc.Card([
        dbc.CardHeader([
            html.I(className="bi bi-shield-exclamation me-2"),
            "风险预算",
        ]),
        dbc.CardBody(budget_card, className="p-3"),
    ], className="h-100")

    return dbc.Row([
        dbc.Col(alloc_section, md=4, className="mb-3"),
        dbc.Col(checklist_section, md=4, className="mb-3"),
        dbc.Col(budget_section, md=4, className="mb-3"),
    ])


@callback(
    Output("timing-output", "children"),
    Input("timing-run", "n_clicks"),
    State("timing-etf", "value"),
    State("timing-index", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, etf_code, index_code):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("timing", index_code=index_code, etf_code=etf_code)
    except Exception as e:
        return error_alert(e)

    signal = result.get("signal")
    allocation = result.get("allocation", [])

    if not signal:
        return dbc.Alert("综合择时信号获取失败", color="danger")

    budget_content = html.Div([
        html.Span("暂无数据", className="text-muted small"),
    ])
    budget = result.get("budget", {})
    if budget:
        pos_limit = budget.get("建议持仓上限", 0)
        pos_ratio = budget.get("持仓上限占比", 0)
        risk_budget_val = budget.get("风险预算(日)", 0)
        adj_factor = budget.get("调整明细", {}).get("综合调整系数", 1)
        budget_content = html.Div([
            html.Div([
                html.Span("建议持仓上限", className="text-muted small d-block"),
                html.Span(f"{pos_limit:,.0f} 元", className="fw-bold h5 d-block"),
                dbc.Progress(value=pos_ratio * 100,
                           color="primary" if pos_ratio > 0.5 else "success",
                           style={"height": "6px"}, className="mt-1"),
                html.Span(f"{pos_ratio:.0%} 总资金", className="text-muted small"),
            ], className="mb-3"),
            html.Div([
                html.Span("日风险预算", className="text-muted small d-block"),
                html.Span(f"{risk_budget_val:,.0f} 元", className="fw-bold h5 d-block"),
            ], className="mb-2"),
            html.Div([
                html.Span("综合调整系数", className="text-muted small d-block"),
                html.Span(f"{adj_factor:.2f}", className="fw-bold h5 d-block"),
            ]),
        ])

    indicator_cards = _build_indicator_cards(signal)
    gauge_fig, score_fig = _build_score_figures(signal)
    bottom_row = _build_bottom_row(signal, allocation, budget_content)

    return html.Div([
        section_header("当前信号", "speedometer2", "综合评分、建议仓位与操作信号"),
        indicator_cards,
        html.Hr(className="my-2"),

        section_header("多维度分析", "bar-chart", "仪表盘综合评分与各维度得分分解"),
        dbc.Row([
            dbc.Col(chart_card(gauge_fig, "综合评分"), md=4, className="mb-3"),
            dbc.Col(chart_card(score_fig, "各维度得分"), md=8, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("配置建议", "briefcase", "ETF配置建议、操作清单与风险预算"),
        bottom_row,
    ])
