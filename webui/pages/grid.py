"""
网格交易优化页面
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card, chart_card
from config import CFG

dash.register_page(__name__, path="/grid", name="网格交易优化")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
DEFAULT_ETF = CFG.etfs[0].code


def layout():
    return html.Div([
        html.H3("网格交易参数优化", className="fw-bold mb-1"),
        html.P("卡尔曼滤波估计均衡价格 · ATR 确定网格间距 · 含滑点和交易费用模拟",
              className="text-muted mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="grid-etf", options=ETF_OPTIONS, value=DEFAULT_ETF, clearable=False),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="grid-years", min=1, max=5, step=1, value=3,
                                   marks={1: "1年", 2: "2年", 3: "3年", 5: "5年"}),
                    ], md=4),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button([html.I(className="bi bi-play-fill me-1"), "运行分析"],
                                   id="grid-run", color="primary", size="lg", className="w-100"),
                    ], md=4),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="grid-loading", type="circle", children=[
            html.Div(id="grid-output"),
        ]),
    ])


@callback(
    Output("grid-output", "children"),
    Input("grid-run", "n_clicks"),
    State("grid-etf", "value"),
    State("grid-years", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, etf_code, years):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("grid", etf_code=etf_code, years=years)
    except Exception as e:
        return error_alert(e)

    params = result.get("grid_params", {})
    simulation = result.get("simulation", None)

    # 参数卡片
    slippage = app_state.system.grid_optimizer.slippage
    fee_rate = app_state.system.grid_optimizer.fee_rate
    param_rows = [
        html.Tr([html.Td("网格中心", className="small text-muted"), html.Td(f'{params.get("网格中心", 0):.3f}', className="fw-semibold")]),
        html.Tr([html.Td("网格间距", className="small text-muted"), html.Td(f'{params.get("网格间距", 0):.4f}', className="fw-semibold")]),
        html.Tr([html.Td("ATR(20)", className="small text-muted"), html.Td(f'{params.get("ATR", 0):.4f}')]),
        html.Tr([html.Td("网格层数", className="small text-muted"), html.Td(f'{params.get("网格层数", 0)}', className="fw-semibold")]),
        html.Tr([html.Td("滑点假设", className="small text-muted"), html.Td(f'{slippage:.4%}')]),
        html.Tr([html.Td("交易费率", className="small text-muted"), html.Td(f'{fee_rate:.4%}')]),
    ]
    params_card = table_card("网格参数", info_table(["参数", "数值"], param_rows), "gear")

    # 网格价格层级
    levels = params.get("网格价格", [])
    center = params.get("网格中心", 0)
    level_rows = []
    for i, p in enumerate(levels):
        direction = "↓ 买入" if p <= center else "↑ 卖出"
        dir_color = "success" if "买入" in direction else "danger"
        level_rows.append(html.Tr([
            html.Td(f"第 {i+1} 层", className="small text-muted"),
            html.Td(f"{p:.3f}", className="fw-semibold"),
            html.Td(html.Span(direction, className=f"badge bg-{dir_color}")),
        ]))
    levels_card = table_card("网格价格层级", info_table(["层级", "价格", "方向"], level_rows), "grid-3x3-gap")

    # 网格价格示意图
    grid_fig = go.Figure()
    grid_fig.add_hline(y=center, line_dash="solid", line_color="#e74c3c", line_width=2,
                       annotation_text=f"网格中心 {center:.3f}")
    for p in levels:
        grid_fig.add_hline(y=p, line_dash="dash", line_color="gray", opacity=0.3, line_width=1)
    grid_fig.update_layout(
        title=dict(text="网格价格层级", font=dict(size=14)),
        yaxis_title="价格", template="plotly_white", height=350,
        margin=dict(l=40, r=20, t=40, b=30),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
    )

    # 净值模拟图 + 指标
    sim_fig = None
    sim_cards = html.Div()
    if simulation is not None and not simulation.empty:
        sim_fig = go.Figure()
        sim_fig.add_trace(go.Scatter(
            x=list(range(len(simulation))), y=simulation["nav"],
            mode="lines", name="策略净值",
            line=dict(color="#22b455", width=2),
            fill="tozeroy", fillcolor="rgba(34,180,85,0.06)",
        ))
        sim_fig.update_layout(
            title=dict(text="网格交易模拟净值", font=dict(size=14)),
            xaxis_title="交易次数", yaxis_title="净值",
            template="plotly_white", height=350,
            margin=dict(l=40, r=20, t=40, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
        )

        total_return = simulation["nav"].iloc[-1] / simulation["nav"].iloc[0] - 1
        final_nav = simulation["nav"].iloc[-1]
        total_slippage = simulation.get("cumulative_slippage_cost", pd.Series([0])).iloc[-1]
        total_fee = simulation.get("cumulative_fee_cost", pd.Series([0])).iloc[-1]
        ret_color = "success" if total_return > 0 else "danger"

        sim_cards = dbc.Row([
            dbc.Col(stat_card(f"{total_return:.2%}", "模拟总收益", ret_color, "graph-up-arrow"), md=3, className="mb-3"),
            dbc.Col(stat_card(f"¥{final_nav:,.2f}", "最终净值", "primary", "cash-coin"), md=3, className="mb-3"),
            dbc.Col(stat_card(f"¥{total_slippage:,.2f}", "累计滑点损失", "warning", "slash-circle"), md=3, className="mb-3"),
            dbc.Col(stat_card(f"¥{total_fee:,.2f}", "累计交易费用", "secondary", "receipt"), md=3, className="mb-3"),
        ])

    return html.Div([
        section_header("网格参数与价格层级", "grid-3x3-gap", "卡尔曼滤波估计均衡价格 · ATR 间距 · 多层挂单"),
        dbc.Row([
            dbc.Col(params_card, md=6, className="mb-3"),
            dbc.Col(levels_card, md=6, className="mb-3"),
        ]),
        dbc.Row([
            dbc.Col(chart_card(grid_fig, "网格价格层级"), md=12, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("网格交易模拟", "cash-coin", "含滑点和交易费用的净值模拟"),
        sim_cards,
        dbc.Row([
            dbc.Col(chart_card(sim_fig, "净值走势"), md=12, className="mb-3")
            if sim_fig else html.Div(),
        ]),
    ])
