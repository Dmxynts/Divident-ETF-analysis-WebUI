"""
风险管理页面
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card
from config import CFG

dash.register_page(__name__, path="/risk", name="风险管理")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
DEFAULT_ETF = CFG.etfs[0].code


def layout():
    return html.Div([
        html.H3("风险管理分析", className="fw-bold mb-1"),
        html.P("VaR/ES/CVaR · 极值理论(EVT) · 动态止损 · 回撤监控 · 情景压力测试",
              className="text-muted mb-4",
              style={"color": "var(--text-secondary) !important"}),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="risk-etf", options=ETF_OPTIONS, value=DEFAULT_ETF, clearable=False),
                    ], md=3),
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="risk-years", min=3, max=15, step=1, value=10,
                                   marks={3: "3年", 5: "5年", 10: "10年", 15: "15年"}),
                    ], md=3),
                    dbc.Col([
                        html.Label("持仓金额(元)", className="fw-semibold small mb-1"),
                        dcc.Input(id="risk-holding", type="number", value=1_000_000,
                                  className="form-control", step=100_000),
                    ], md=3),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button([html.I(className="bi bi-play-fill me-1"), "运行分析"],
                                   id="risk-run", color="primary", size="lg", className="w-100"),
                    ], md=3),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="risk-loading", type="circle", children=[
            html.Div(id="risk-output"),
        ]),
    ])


@callback(
    Output("risk-output", "children"),
    Input("risk-run", "n_clicks"),
    State("risk-etf", "value"),
    State("risk-years", "value"),
    State("risk-holding", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, etf_code, years, holding):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("risk", etf_code=etf_code, years=years, holding=holding or 1_000_000)
    except Exception as e:
        return error_alert(e)

    risk_report = result.get("risk_report", {})
    dist = result.get("distribution", {})
    evt = result.get("evt", {})
    returns = result.get("returns")

    holding_val = holding or 1_000_000

    # ========== VaR/ES 核心指标卡片 ==========
    var_cards = []
    for conf_label in ("95%", "99%"):
        var_h = risk_report.get(f"VaR(历史法,{conf_label})", "")
        var_cf = risk_report.get(f"VaR(CF修正,{conf_label})", "")
        es = risk_report.get(f"CVaR/ES({conf_label})", "")
        loss = risk_report.get(f"日最大预期损失({conf_label})", "")

        def _pct(v):
            try:
                return float(v.strip("%")) / 100 if isinstance(v, str) else 0
            except (ValueError, AttributeError):
                return 0

        var_cards.extend([
            stat_card(f"{_pct(var_h):.2%}", f"VaR 历史法 ({conf_label})", "danger", "shield"),
            stat_card(f"{_pct(var_cf):.2%}", f"VaR CF修正 ({conf_label})", "warning", "shield-check"),
            stat_card(f"{_pct(es):.2%}", f"CVaR/ES ({conf_label})", "danger", "exclamation-triangle"),
            stat_card(loss.replace(" 元", ""), f"日最大预期损失 ({conf_label})", "secondary", "cash", " 元"),
        ])

    var_cards_row = dbc.Row(
        [dbc.Col(c, md=3, className="mb-3") for c in var_cards]
    )

    # ========== 分布特征卡片 ==========
    dist_cards = []
    for k, v in dist.items():
        color = "primary" if k in ("偏度", "峰度") else "info"
        dist_cards.append(stat_card(v, k, color, "bar-chart"))
    dist_row = dbc.Row(
        [dbc.Col(c, lg=3, md=6, className="mb-3") for c in dist_cards]
    ) if dist_cards else html.Div()

    # ========== EVT 结果 ==========
    evt_rows = []
    if evt:
        for k, v in evt.items():
            v_str = f"{v:.2%}" if isinstance(v, float) else str(v)
            color = "danger" if "肥尾" in str(v) else "success" if "正态" in str(v) else "warning"
            evt_rows.append(html.Tr([
                html.Td(k, className="small text-muted"),
                html.Td(html.Span(v_str, className=f"badge bg-{color}")),
            ]))
    evt_section = html.Div()
    if evt_rows:
        evt_section = table_card("极值理论 (EVT)", info_table(["指标", "数值"], evt_rows), "lightning")

    # ========== 回撤指标卡片 ==========
    dd_info = result.get("dd_info", {})
    sl_info = result.get("sl_info", {})

    dd_color = "danger" if abs(dd_info.get("当前回撤", 0)) > 0.05 else "warning"
    status_color = {
        "创新高": "success", "小幅波动": "info", "正常回撤": "primary",
        "中等回撤": "warning", "深度回撤": "danger", "极端回撤": "danger",
    }.get(dd_info.get("状态", ""), "secondary")

    dd_row = dbc.Row([
        dbc.Col(stat_card(f"{dd_info.get('当前回撤', 0):.2%}", "当前回撤", dd_color, "arrow-down"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{dd_info.get('历史最大回撤', 0):.2%}", "历史最大回撤", "danger", "exclamation-triangle"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{sl_info.get('建议止损线(%)', 0):.1f}%", "建议止损线", "warning", "shield-exclamation"), md=3, className="mb-3"),
        dbc.Col(stat_card(dd_info.get("状态", ""), "回撤状态", status_color, "flag"), md=3, className="mb-3"),
    ])

    # ========== 滚动 VaR 图 ==========
    var_fig = None
    try:
        window = 252
        rolling_var = returns.rolling(window).apply(lambda x: np.percentile(x, 5), raw=True)
        rolling_cvar = returns.rolling(window).apply(lambda x: x[x <= np.percentile(x, 5)].mean(), raw=True)
        var_fig = go.Figure()
        var_fig.add_trace(go.Scatter(
            x=returns.index, y=returns.cumsum(),
            mode="lines", name="累计收益", line=dict(color="gray", width=1),
        ))
        var_fig.add_trace(go.Scatter(
            x=rolling_var.index, y=rolling_var,
            mode="lines", name="滚动 VaR(95%)", line=dict(color="#e74c3c", width=2),
        ))
        var_fig.add_trace(go.Scatter(
            x=rolling_cvar.index, y=rolling_cvar,
            mode="lines", name="滚动 CVaR(95%)", line=dict(color="#c0392b", width=2, dash="dash"),
        ))
        var_fig.update_layout(
            title=dict(text="滚动风险指标 (252日窗口)", font=dict(size=14)),
            yaxis_title="收益率", template="plotly_white",
            hovermode="x unified", height=300,
            margin=dict(l=40, r=20, t=40, b=30),
            legend=dict(orientation="h", y=1.12),
            paper_bgcolor="rgba(0,0,0,0)",
        )
    except Exception:
        pass

    var_chart = html.Div()
    if var_fig:
        from webui.components import chart_card
        var_chart = chart_card(var_fig, "滚动风险指标 (252日窗口)")

    # ========== 压力测试 ==========
    stress_section = html.Div()
    scenarios = result.get("scenarios", {})
    if scenarios:
        stress_rows = []
        for name, detail in scenarios.items():
            loss_str = f"{detail.get('损失金额', 0):,.0f} 元"
            drop_str = f"{abs(detail.get('跌幅', 0)):.1%}"
            drop_color = "danger" if abs(detail.get('跌幅', 0)) > 0.05 else "warning"
            stress_rows.append(html.Tr([
                html.Td(name, className="small"),
                html.Td(html.Span(drop_str, className=f"badge bg-{drop_color}")),
                html.Td(loss_str, className="fw-semibold"),
            ]))
        stress_section = table_card("情景压力测试", info_table(["情景", "跌幅", "损失金额"], stress_rows), "cloud-lightning")

    # ========== 风险预算 ==========
    budget_section = html.Div()
    budget = result.get("budget", {})
    if budget:
        det = budget.get("调整明细", {})
        budget_rows = [
            html.Tr([html.Td("总资金", className="small text-muted"), html.Td(f"{budget.get('总资金', 0):,.0f} 元", className="fw-semibold")]),
            html.Tr([html.Td("建议持仓上限", className="small text-muted"),
                     html.Td(html.Span(f"{budget.get('建议持仓上限', 0):,.0f} 元", className="badge bg-success"))]),
            html.Tr([html.Td("持仓上限占比", className="small text-muted"), html.Td(f"{budget.get('持仓上限占比', 0):.0%}")]),
            html.Tr([html.Td("日风险预算", className="small text-muted"), html.Td(f"{budget.get('风险预算(日)', 0):,.0f} 元")]),
        ]
        if det:
            budget_rows.append(html.Tr([
                html.Td("综合调整系数", className="small text-muted"),
                html.Td(html.Span(f"{det.get('综合调整系数', 1):.2f}", className="badge bg-info")),
            ]))
        budget_section = table_card("风险预算分配", info_table(["项目", "数值"], budget_rows), "calculator")

    return html.Div([
        section_header("VaR / ES 风险价值", "shield-check", "不同置信度下的 VaR 和预期亏损"),
        var_cards_row,
        html.Hr(className="my-2"),

        section_header("收益率分布特征", "bar-chart", "偏度、峰度与分布形态"),
        dist_row,
        html.Hr(className="my-2"),

        section_header("动态回撤监控", "arrow-down-circle", "回撤深度、止损线与趋势预警"),
        dd_row,

        var_chart,
        html.Hr(className="my-2"),

        section_header("尾部风险与压力测试", "lightning", "EVT 极值理论 · 情景压力测试 · 风险预算"),
        dbc.Row([
            dbc.Col(evt_section, md=4, className="mb-3"),
            dbc.Col(stress_section, md=4, className="mb-3"),
            dbc.Col(budget_section, md=4, className="mb-3"),
        ]),
    ])
