"""
波动率分析页面（GARCH）
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card, chart_card
from config import CFG

dash.register_page(__name__, path="/volatility", name="波动率分析")

ETF_OPTIONS = [{"label": f"{etf.name} ({etf.code})", "value": etf.code} for etf in CFG.etfs]
DEFAULT_ETF = CFG.etfs[0].code


def layout():
    return html.Div([
        html.H3("波动率建模分析 (GARCH)", className="fw-bold mb-1"),
        html.P("GARCH/EGARCH/GJR-GARCH 模型族 · 波动率预测 · 极端事件检测",
              className="text-muted mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("ETF", className="fw-semibold small mb-1"),
                        dcc.Dropdown(id="vol-etf", options=ETF_OPTIONS, value=DEFAULT_ETF, clearable=False),
                    ], md=4, style={"zIndex": 9999, "position": "relative"}),
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="vol-years", min=3, max=10, step=1, value=5,
                                   marks={3: "3年", 5: "5年", 8: "8年", 10: "10年"}),
                    ], md=4),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button([html.I(className="bi bi-play-fill me-1"), "运行分析"],
                                   id="vol-run", color="primary", size="lg", className="w-100"),
                    ], md=4),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="vol-loading", type="circle", children=[
            html.Div(id="vol-output"),
        ]),
    ])


def _build_events_table(extreme_events):
    """极端事件表格"""
    if extreme_events is None or extreme_events.empty:
        return html.Div(html.Small("暂无极端事件", className="text-muted"))
    ext = extreme_events[extreme_events["signal"] != "正常"]
    if ext.empty:
        return html.Div(html.Small("暂无极端事件", className="text-muted"))
    rows = []
    for _, row in ext.tail(10).iterrows():
        d_str = str(row.get("date", row.name))[:10] if hasattr(row, "get") else str(row.name)[:10]
        z = row.get("vol_zscore", 0)
        sig = row.get("signal", "")
        sig_color = "danger" if "骤升" in str(sig) else "success" if "骤降" in str(sig) else "warning"
        rows.append(html.Tr([
            html.Td(d_str, className="small"),
            html.Td(html.Span(f"{z:.2f}", className=f"badge bg-{sig_color}")),
            html.Td(html.Span(sig, className=f"badge bg-{sig_color}")),
        ]))
    return dbc.Table(
        [html.Thead(html.Tr([
            html.Th("日期", className="small text-muted"),
            html.Th("Z-Score", className="small text-muted"),
            html.Th("信号", className="small text-muted"),
        ])),
         html.Tbody(rows)],
        bordered=False, hover=True, size="sm", className="mb-0",
    )


@callback(
    Output("vol-output", "children"),
    Input("vol-run", "n_clicks"),
    State("vol-etf", "value"),
    State("vol-years", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, etf_code, years):
    if not n_clicks:
        return html.Div()

    try:
        result = app_state.run("volatility", etf_code=etf_code, years=years)
    except Exception as e:
        return error_alert(e)

    vol_forecast = result.get("vol_forecast", None)
    extreme_events = result.get("extreme_events", None)
    vol_regime = result.get("vol_regime", None)
    garch_params = result.get("garch_params", {})

    # GARCH 参数
    param_rows = []
    for k, v in garch_params.items():
        v_str = f"{v:.4f}" if isinstance(v, float) else str(v)
        param_rows.append(html.Tr([html.Td(k, className="small text-muted"), html.Td(v_str, className="fw-semibold")]))
    params_card = table_card("GARCH 参数", info_table(["参数", "数值"], param_rows), "gear")

    # 波动率体制
    regime_card = html.Div()
    if vol_regime is not None and not vol_regime.empty:
        lr = vol_regime.iloc[-1]
        regime_labels = {"低波动": "success", "正常波动": "info", "高波动": "warning", "极端波动": "danger"}
        rc = regime_labels.get(lr.get("体制", ""), "secondary")
        regime_card = dbc.Card([
            dbc.CardHeader([html.I(className="bi bi-activity me-2"), "当前波动率体制"],
                          style={"fontSize": "0.9rem", "fontWeight": 600}),
            dbc.CardBody([
                html.H4(html.Span(lr.get("体制", ""), className=f"badge bg-{rc}"), className="mb-3"),
                html.Div([
                    html.Div([
                        html.Small("年化波动率", className="text-muted d-block"),
                        html.Span(f"{lr.get('年化波动率', 0):.2%}", className="fw-bold h5"),
                    ], className="mb-2"),
                    html.Div([
                        html.Small("建议", className="text-muted d-block"),
                        html.Span(lr.get("建议", ""), className="text-info"),
                    ]),
                ]),
            ]),
        ], className="shadow-sm h-100")
    else:
        regime_card = stat_card("—", "波动率体制", "secondary", "activity")

    # 极端事件
    event_card = table_card("极端事件 (最近10次)", _build_events_table(extreme_events), "exclamation-triangle")

    # 条件波动率图
    vol_fig = None
    z_fig = None
    try:
        vol_data = app_state.system.vol_model.vol_data
        if vol_data is not None and not vol_data.empty:
            vol_fig = go.Figure()
            vol_fig.add_trace(go.Scatter(
                x=vol_data.index if isinstance(vol_data.index, (list, pd.Index)) else list(range(len(vol_data))),
                y=vol_data.get("returns", [0]), mode="lines",
                name="日收益率", line=dict(color="gray", width=0.8), opacity=0.4,
            ))
            if "conditional_vol" in vol_data.columns:
                vol_fig.add_trace(go.Scatter(
                    x=vol_data.index if isinstance(vol_data.index, (list, pd.Index)) else list(range(len(vol_data))),
                    y=vol_data["conditional_vol"], mode="lines",
                    name="条件波动率 (GARCH)", line=dict(color="#e74c3c", width=2),
                ))
            vol_fig.update_layout(
                title=dict(text="GARCH 条件波动率", font=dict(size=14)),
                yaxis_title="波动率", template="plotly_white",
                hovermode="x unified", height=280,
                margin=dict(l=40, r=20, t=40, b=30),
                legend=dict(orientation="h", y=1.12),
                paper_bgcolor="rgba(0,0,0,0)",
            )

            if "vol_zscore" in vol_data.columns:
                idx = vol_data.index if isinstance(vol_data.index, (list, pd.Index)) else list(range(len(vol_data)))
                z_fig = go.Figure()
                z_fig.add_trace(go.Scatter(
                    x=idx, y=vol_data["vol_zscore"],
                    mode="lines", name="Z-Score", line=dict(color="#4a7cf7", width=2),
                ))
                z_fig.add_hline(y=2, line_dash="dash", line_color="#e74c3c",
                               annotation_text="+2σ (加仓)")
                z_fig.add_hline(y=-2, line_dash="dash", line_color="#22b455",
                               annotation_text="-2σ (减仓)")
                z_fig.update_layout(
                    title=dict(text="波动率 Z-Score", font=dict(size=14)),
                    yaxis_title="Z-Score", template="plotly_white",
                    hovermode="x unified", height=280,
                    margin=dict(l=40, r=20, t=40, b=30),
                    paper_bgcolor="rgba(0,0,0,0)",
                )
    except Exception:
        pass

    # 波动率预测图
    forecast_fig = None
    if vol_forecast is not None and not vol_forecast.empty:
        forecast_fig = go.Figure()
        forecast_fig.add_trace(go.Scatter(
            x=list(range(len(vol_forecast))), y=vol_forecast["point"],
            mode="lines+markers", name="预测波动率",
            line=dict(color="#e74c3c", width=2),
            marker=dict(size=6),
        ))
        if "upper" in vol_forecast.columns:
            forecast_fig.add_trace(go.Scatter(
                x=list(range(len(vol_forecast))), y=vol_forecast["upper"],
                mode="lines", name="95% 置信上界",
                line=dict(color="gray", dash="dash", width=1),
            ))
        if "lower" in vol_forecast.columns:
            forecast_fig.add_trace(go.Scatter(
                x=list(range(len(vol_forecast))), y=vol_forecast["lower"],
                mode="lines", name="95% 置信下界",
                line=dict(color="gray", dash="dash", width=1),
                fill="tonexty", fillcolor="rgba(128,128,128,0.08)",
            ))
        forecast_fig.update_layout(
            title=dict(text=f"未来 {len(vol_forecast)} 日波动率预测", font=dict(size=14)),
            xaxis_title="天数", yaxis_title="年化波动率 (%)",
            template="plotly_white", hovermode="x unified", height=300,
            margin=dict(l=40, r=20, t=40, b=30),
            legend=dict(orientation="h", y=1.12),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    return html.Div([
        section_header("模型参数与状态", "gear", "GARCH 模型拟合参数、当前波动率体制与极端事件"),
        dbc.Row([
            dbc.Col(params_card, md=4, className="mb-3"),
            dbc.Col(regime_card, md=4, className="mb-3"),
            dbc.Col(event_card, md=4, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("条件波动率分析", "activity", "GARCH 条件波动率序列与 Z-Score 异常检测"),
        dbc.Row([
            dbc.Col(chart_card(vol_fig, "GARCH 条件波动率") if vol_fig else html.Div(), md=6, className="mb-3"),
            dbc.Col(chart_card(z_fig, "波动率 Z-Score") if z_fig else html.Div(), md=6, className="mb-3"),
        ]),
        html.Hr(className="my-2"),

        section_header("波动率预测", "graph-up", "GARCH 模型多步波动率预测"),
        dbc.Row([
            dbc.Col(chart_card(forecast_fig, "波动率预测") if forecast_fig else html.Div(), md=8, className="mb-3"),
        ]),
    ])
