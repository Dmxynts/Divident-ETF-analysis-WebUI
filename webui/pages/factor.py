"""
因子归因分析页面
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card, chart_card
from config import CFG

dash.register_page(__name__, path="/factor", name="因子归因")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
DEFAULT_ETF = CFG.etfs[0].code


def layout():
    return html.Div([
        html.H3("因子归因分析", className="fw-bold mb-1"),
        html.P("时间序列多因子回归 · 拆解红利 ETF 收益来源（市场/小盘/低波因子）",
              className="text-muted mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="factor-etf", options=ETF_OPTIONS, value=DEFAULT_ETF, clearable=False),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="factor-years", min=3, max=10, step=1, value=5,
                                   marks={3: "3年", 5: "5年", 8: "8年", 10: "10年"}),
                    ], md=4),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button([html.I(className="bi bi-play-fill me-1"), "运行分析"],
                                   id="factor-run", color="primary", size="lg", className="w-100"),
                    ], md=4),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="factor-loading", type="circle", children=[
            html.Div(id="factor-output"),
        ]),
    ])


@callback(
    Output("factor-output", "children"),
    Input("factor-run", "n_clicks"),
    State("factor-etf", "value"),
    State("factor-years", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, etf_code, years):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("factor", etf_code=etf_code, years=years)
    except Exception as e:
        return error_alert(e)

    if not result:
        return dbc.Alert("因子数据不足，请检查网络连接或数据源可用性", color="warning")

    factor_contrib = result.get("factor_contribution", pd.DataFrame())
    regression = result.get("regression", {})

    # R² 卡片
    r2 = regression.get("R²", 0)
    r2_color = "success" if r2 > 0.8 else "warning" if r2 > 0.5 else "secondary"

    r2_card = stat_card(f"{r2:.3f}" if isinstance(r2, (int, float)) else str(r2),
                       "模型拟合度 R²", r2_color, "bar-chart")

    # 回归结果
    reg_rows = []
    for k, v in regression.items():
        if k in ("R²", "调整R²", "F值"):
            continue
        v_str = f"{v:.4f}" if isinstance(v, (int, float)) and abs(v) < 100 else str(v)
        reg_rows.append(html.Tr([html.Td(k, className="small text-muted"), html.Td(v_str)]))
    reg_card = table_card("回归摘要", info_table(["指标", "数值"], reg_rows), "table")

    # 因子贡献表
    contrib_rows = []
    if factor_contrib is not None and not factor_contrib.empty:
        for _, row in factor_contrib.iterrows():
            coef = row.get("系数", 0)
            coef_color = "success" if coef > 0 else "danger"
            sig = ""
            pv = row.get("p值", 1)
            if pv < 0.01:
                sig = " ***"
            elif pv < 0.05:
                sig = " **"
            elif pv < 0.1:
                sig = " *"

            contrib_rows.append(html.Tr([
                html.Td(row.get("因子", ""), className="fw-semibold"),
                html.Td(html.Span(f"{coef:+.4f}", className=f"badge bg-{coef_color}")),
                html.Td(f"{row.get('贡献度', 0):.2%}{sig}"),
            ]))
    contrib_card = table_card("因子贡献度", info_table(["因子", "系数", "贡献度"], contrib_rows), "pie-chart")

    # 因子贡献柱状图
    contrib_fig = None
    if factor_contrib is not None and not factor_contrib.empty:
        factors = factor_contrib["因子"].tolist()
        contributions = factor_contrib["贡献度"].tolist()
        colors = ["#22b455" if c >= 0 else "#e74c3c" for c in contributions]
        contrib_fig = go.Figure()
        contrib_fig.add_trace(go.Bar(
            x=factors, y=contributions,
            marker_color=colors,
            text=[f"{c:.2%}" for c in contributions],
            textposition="auto", textfont=dict(size=12),
            hovertemplate="%{x}: %{y:.2%}<extra></extra>",
        ))
        contrib_fig.update_layout(
            title=dict(text="因子贡献度", font=dict(size=14)),
            yaxis_title="贡献度", template="plotly_white",
            height=300,
            margin=dict(l=40, r=20, t=40, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    # 滚动 Beta
    rolling_beta_fig = None
    rolling_beta = result.get("rolling_beta")
    if rolling_beta is not None and not rolling_beta.empty:
        rolling_beta_fig = go.Figure()
        for col in rolling_beta.columns:
            rolling_beta_fig.add_trace(go.Scatter(
                x=rolling_beta.index, y=rolling_beta[col],
                mode="lines", name=col, line=dict(width=2),
            ))
        rolling_beta_fig.update_layout(
            title=dict(text="滚动因子 Beta (120日窗口)", font=dict(size=14)),
            xaxis_title="日期", yaxis_title="Beta",
            template="plotly_white", hovermode="x unified",
            height=300, margin=dict(l=40, r=20, t=40, b=30),
            legend=dict(orientation="h", y=1.12),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    # 近期收益分解
    decomp_table = html.Div()
    factor_series_names = result.get("factor_series_names", [])
    decomp = result.get("decomp")
    if decomp is not None and not decomp.empty:
        recent = decomp.tail(10)
        decomp_rows = []
        for date, row in recent.iterrows():
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
            total_ret = row.get("实际收益", 0)
            parts = [html.Td(date_str, className="small text-muted")]
            parts.append(html.Td(f"{total_ret:.4%}", className="fw-semibold"))
            for col in factor_series_names:
                key = f"{col}_贡献"
                val = row.get(key, 0)
                c = "success" if val > 0 else "danger"
                parts.append(html.Td(html.Span(f"{val:+.4%}", className=f"badge bg-{c}")))
            parts.append(html.Td(html.Span(f"α={row.get('Alpha', 0):+.4%}", className="badge bg-info")))
            decomp_rows.append(html.Tr(parts))
        headers = ["日期", "实际收益"] + list(factor_series_names) + ["Alpha"]
        decomp_table = table_card("近期收益分解 (最近10期)",
                                 info_table(headers, decomp_rows), "table")

    # 如果不足10行，加个提示
    no_data = html.Div()
    if decomp is not None and len(decomp) < 10:
        no_data = html.Small(f"仅 {len(decomp)} 期数据", className="text-muted")

    return html.Div([
        section_header("回归结果", "table", "因子模型拟合度与各因子贡献度"),
        dbc.Row([
            dbc.Col(r2_card, md=3, className="mb-3"),
            dbc.Col(reg_card, md=4, className="mb-3"),
            dbc.Col(contrib_card, md=5, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("因子可视化", "graph-up", "因子贡献柱状图与滚动 Beta"),
        dbc.Row([
            dbc.Col(chart_card(contrib_fig, "因子贡献度") if contrib_fig else html.Div(), md=6, className="mb-3"),
            dbc.Col(chart_card(rolling_beta_fig, "滚动因子 Beta") if rolling_beta_fig else html.Div(), md=6, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("收益分解", "pie-chart", "将每日 ETF 收益拆解到各因子 + Alpha"),
        decomp_table, no_data,
    ])
