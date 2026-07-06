"""
总览页面 - Dashboard 首页
"""
import sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_root))

import dash
from dash import html
import dash_bootstrap_components as dbc
from config import CFG

dash.register_page(__name__, path="/", name="总览")

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
        # 欢迎横幅
        dbc.Row([
            dbc.Col([
                html.H2("红利ETF量化分析系统", className="fw-bold"),
                html.P("基于金融工程方法的 A股红利ETF 研究与交易决策支持系统",
                       className="text-muted lead"),
            ]),
        ], className="mb-4"),

        # ETF 列表
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("跟踪标的"),
                    dbc.CardBody(
                        html.Div([
                            html.Span(f"{etf.name} ({etf.code})",
                                     className="badge bg-light text-dark me-2 mb-1")
                            for etf in CFG.etfs
                        ])
                    ),
                ], className="shadow-sm"),
            ]),
        ], className="mb-4"),

        # 模块入口
        html.H5("分析模块", className="mb-3"),
        dbc.Row(
            [
                dbc.Col(module_card(mod), md=4, sm=6, className="mb-3")
                for mod in MODULES
            ],
        ),

        # 技术栈
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("技术栈"),
                    dbc.CardBody([
                        html.Span("Python", className="badge bg-secondary me-1"),
                        html.Span("Pandas", className="badge bg-secondary me-1"),
                        html.Span("NumPy", className="badge bg-secondary me-1"),
                        html.Span("AKShare", className="badge bg-secondary me-1"),
                        html.Span("HMMLearn", className="badge bg-secondary me-1"),
                        html.Span("Arch", className="badge bg-secondary me-1"),
                        html.Span("Scikit-learn", className="badge bg-secondary me-1"),
                        html.Span("Dash", className="badge bg-secondary me-1"),
                        html.Span("Plotly", className="badge bg-secondary me-1"),
                        html.Span("Matplotlib", className="badge bg-secondary me-1"),
                    ]),
                ], className="shadow-sm"),
            ]),
        ], className="mt-2"),
    ])
