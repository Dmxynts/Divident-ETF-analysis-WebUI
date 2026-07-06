"""
宏观状态识别页面（HMM）
"""
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np
from webui.state import state as app_state, error_alert
from webui.components import section_header, stat_card, info_table, table_card, chart_card

dash.register_page(__name__, path="/macro", name="宏观状态识别")


def layout():
    return html.Div([
        html.H3("宏观状态识别 (HMM)", className="fw-bold mb-1"),
        html.P("隐含马尔可夫模型将经济划分为复苏/过热/滞胀/衰退四阶段",
              className="text-muted mb-4"),

        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label("回溯年限", className="fw-semibold small mb-1"),
                        dcc.Slider(id="macro-years", min=5, max=20, step=1, value=10,
                                   marks={5: "5年", 10: "10年", 15: "15年", 20: "20年"}),
                    ], md=6),
                    dbc.Col([
                        html.Label("HMM 参数调优", className="fw-semibold small mb-1"),
                        dbc.Checklist(
                            options=[{"label": "对比不同参数组合", "value": "tune"}],
                            value=[], id="macro-tune", switch=True,
                        ),
                        html.Small("增加运行时间，自动推荐最优参数", className="text-muted d-block mt-1"),
                    ], md=3),
                    dbc.Col([
                        html.Label(" ", className="fw-semibold small d-block mb-1"),
                        dbc.Button([html.I(className="bi bi-play-fill me-1"), "运行分析"],
                                   id="macro-run", color="primary", size="lg", className="w-100"),
                    ], md=3),
                ]),
            ]),
        ], className="shadow-sm mb-4"),

        dcc.Loading(id="macro-loading", type="circle", children=[
            html.Div(id="macro-output"),
        ]),
    ])


@callback(
    Output("macro-output", "children"),
    Input("macro-run", "n_clicks"),
    State("macro-years", "value"),
    State("macro-tune", "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks, years, tune):
    if not n_clicks:
        return html.Div()

    try:
        tune_flag = "tune" in (tune or [])
        result = app_state.run("macro", years=years, tune=tune_flag)
    except Exception as e:
        return error_alert(e)

    enhanced = result.get("enhanced_score", {})
    labeled = result.get("labeled", None)
    transition = result.get("transition_matrix", None)
    features = result.get("features", None)
    compare = result.get("compare_params", None)

    # 当前状态
    state_color = {
        "复苏": "success", "过热": "danger",
        "滞胀": "warning", "衰退": "info", "未知": "secondary",
    }
    sc = state_color.get(enhanced.get("state", "未知"), "secondary")

    # 核心指标卡片
    indicator_cards = dbc.Row([
        dbc.Col(stat_card(enhanced.get("state", "N/A"), "当前宏观状态", sc, "globe2"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{enhanced.get('macro_score', 0):+.3f}", "宏观评分", "primary", "speedometer2"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{enhanced.get('suggested_position', 0.5):.0%}", "建议仓位", "success", "pie-chart"), md=3, className="mb-3"),
        dbc.Col(stat_card(f"{enhanced.get('persistence_months', 0)}个月", "状态持续", "info", "clock"), md=3, className="mb-3"),
    ])

    # 状态概率表
    state_probs = enhanced.get("state_probs", {})
    prob_badges = html.Div([
        dbc.Row([
            dbc.Col(html.Div([
                html.Div(name, className="small text-muted"),
                html.Div(f"{prob:.1%}", className="fw-bold h5"),
            ], className="text-center p-2 rounded",
                style={"background": "rgba(74,124,247,0.06)"}),
            width=3, className="mb-2") for name, prob in
            (state_probs.items() if isinstance(state_probs, dict) else [])
        ])
    ]) if isinstance(state_probs, dict) and state_probs else html.Small("暂无数据", className="text-muted")

    next_pos = enhanced.get("expected_next_pos", 0.5)

    extra_cards = dbc.Row([
        dbc.Col(table_card("状态概率分布", info_table(
            ["状态", "概率"],
            [html.Tr([html.Td(k, className="small"), html.Td(f"{v:.1%}")])
             for k, v in (state_probs.items() if isinstance(state_probs, dict) else [])]
        ), "pie-chart"), md=4, className="mb-3"),
        dbc.Col(stat_card(f"{next_pos:.0%}", "下期预期仓位", "info", "arrow-right"), md=4, className="mb-3"),
        dbc.Col(dbc.Card([
            dbc.CardHeader([html.I(className="bi bi-arrow-left-right me-2"), "状态转移概率"],
                          style={"fontSize": "0.9rem", "fontWeight": 600}),
            dbc.CardBody(
                info_table(
                    ["当前 \\ 下一状态"] + (list(transition.columns) if transition is not None else []),
                    [html.Tr([html.Td(st, className="small fw-semibold")] +
                             [html.Td(f"{transition.loc[st, col]:.1%}" if transition is not None else "-")
                              for col in transition.columns])
                     for st in transition.index]
                ) if transition is not None and not transition.empty else
                html.Small("无转移矩阵数据", className="text-muted"),
            ),
        ], className="shadow-sm h-100"), md=4, className="mb-3"),
    ])

    # 状态转移热力图
    transition_fig = None
    if transition is not None and not transition.empty:
        states = list(transition.columns)
        z = transition.to_numpy()
        transition_fig = go.Figure(data=go.Heatmap(
            z=z, x=states, y=states,
            colorscale="Blues", text=np.round(z, 3),
            texttemplate="%{text}", textfont=dict(size=11),
        ))
        transition_fig.update_layout(
            title=dict(text="状态转移概率矩阵", font=dict(size=14)),
            xaxis_title="下一状态", yaxis_title="当前状态",
            template="plotly_white", height=350,
            margin=dict(l=40, r=20, t=40, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    # 状态历史走势
    history_fig = None
    if labeled is not None and not labeled.empty:
        hist_df = labeled.reset_index()
        state_colors_map = {"复苏": "#2ecc71", "过热": "#e74c3c",
                           "滞胀": "#f39c12", "衰退": "#3498db", "未知": "#95a5a6"}
        colors = [state_colors_map.get(s, "#95a5a6") for s in hist_df["state_label"]]
        history_fig = go.Figure()
        history_fig.add_trace(go.Scatter(
            x=list(range(len(hist_df))), y=hist_df["state_label"],
            mode="markers", marker=dict(color=colors, size=8, line=dict(width=1, color="white")),
            showlegend=False,
        ))
        history_fig.update_layout(
            title=dict(text="宏观状态历史走势", font=dict(size=14)),
            xaxis_title="时间", yaxis_title="状态",
            template="plotly_white", height=250,
            margin=dict(l=40, r=20, t=40, b=30),
            paper_bgcolor="rgba(0,0,0,0)",
        )

    # 特征数据图表
    feature_figs = []
    if features is not None:
        feature_cols = features.select_dtypes(include=[np.number]).columns[:6]
        for col in feature_cols:
            f = go.Figure()
            f.add_trace(go.Scatter(
                x=list(range(len(features))), y=features[col],
                mode="lines", name=col, line=dict(width=2),
            ))
            f.update_layout(
                title=dict(text=col, font=dict(size=12)),
                template="plotly_white", height=180,
                margin=dict(l=30, r=10, t=30, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            feature_figs.append(chart_card(f, col))

    # 评分明细
    det = enhanced.get("details", {})
    detail_rows = []
    if det:
        for k, v in det.items():
            v_str = f"{v:.3f}" if isinstance(v, float) else str(v)
            color = "success" if isinstance(v, (int, float)) and v > 0 else "danger" if isinstance(v, (int, float)) and v < 0 else "secondary"
            detail_rows.append(html.Tr([
                html.Td(k, className="small text-muted"),
                html.Td(html.Span(v_str, className=f"badge bg-{color}")),
            ]))
    detail_table = table_card("评分明细", info_table(["指标", "数值"], detail_rows), "list-check")

    # 参数调优结果
    tune_table = html.Div()
    if compare is not None:
        tune_rows = []
        best = compare.iloc[0] if len(compare) > 0 else None
        for _, row in compare.iterrows():
            is_best = best is not None and row["score"] == best["score"]
            tune_rows.append(html.Tr([
                html.Td(f"n={row.get('n_states', '')}", className="small"),
                html.Td(f"{row.get('score', 0):.3f}"),
                html.Td("✅ 最优" if is_best else "", className="text-success"),
            ]))
        tune_table = table_card("参数调优对比 (按评分排序)",
                               info_table(["参数", "评分", ""], tune_rows), "gear")

    # 图表行
    charts_row = html.Div()
    if transition_fig or history_fig:
        charts_row = dbc.Row([
            dbc.Col(chart_card(transition_fig, "状态转移概率矩阵") if transition_fig else html.Div(), md=6, className="mb-3"),
            dbc.Col(
                chart_card(history_fig, "宏观状态历史走势") if history_fig else html.Div(),
                md=6,
            ),
        ])

    return html.Div([
        section_header("当前宏观状态", "globe2", "HMM 模型推断的经济阶段与配置建议"),
        indicator_cards,
        html.Hr(className="my-2"),

        section_header("状态概率与预期", "arrow-right-circle", "下期状态概率分布与转移矩阵"),
        extra_cards,
        html.Hr(className="my-2"),

        section_header("状态可视化", "graph-up", "转移矩阵热力图与历史状态演变"),
        charts_row,
        html.Hr(className="my-2"),

        section_header("特征数据", "bar-chart", "模型使用的宏观经济特征序列"),
        dbc.Row([dbc.Col(f, md=4, className="mb-3") for f in feature_figs]),
        html.Hr(className="my-2"),

        section_header("模型诊断", "search-heart", "评分明细与参数调优结果"),
        dbc.Row([
            dbc.Col(detail_table, md=6, className="mb-3"),
            dbc.Col(tune_table, md=6, className="mb-3"),
        ]),
    ])
