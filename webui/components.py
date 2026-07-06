"""
WebUI 共享组件 — 统一风格的卡片、表头、指标、表格
"""
from dash import html
import dash_bootstrap_components as dbc


def section_header(title: str, icon: str = None, subtitle: str = None) -> html.Div:
    """章节标题：彩色左边框 + 图标 + 可选副标题"""
    icon_el = html.I(className=f"bi bi-{icon} me-2") if icon else None
    return html.Div([
        html.Div([
            html.Div([
                html.H5([icon_el, title], className="fw-bold mb-0",
                        style={"color": "var(--text-primary)"}),
                html.P(subtitle, className="text-muted small mb-0 mt-1") if subtitle else None,
            ], style={
                "borderLeft": "3px solid var(--accent-blue)",
                "paddingLeft": "14px",
            }),
        ]),
    ])


def stat_card(value, label: str, color: str = "primary",
              icon: str = None, suffix: str = None) -> dbc.Card:
    """大数字指标卡片"""
    icon_el = html.I(className=f"bi bi-{icon}",
                     style={"fontSize": "2rem", "color": f"var(--accent-{color})"}) if icon else None
    value_str = f"{value}{suffix or ''}"
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                icon_el,
                html.Div([
                    html.Div(value_str, className=f"h3 fw-bold mb-0 text-{color}"),
                    html.Small(label, className="text-muted"),
                ]),
            ], className="d-flex align-items-center gap-3"),
        ]),
    ], className="shadow-sm h-100", style={"borderRadius": "var(--glass-radius, 14px)"})


def info_table(headers: list, rows: list, striped: bool = True) -> dbc.Table:
    """统一样式的信息表格"""
    return dbc.Table(
        [html.Thead(html.Tr([html.Th(h, className="small text-muted fw-semibold") for h in headers])),
         html.Tbody(rows)],
        bordered=False, hover=True, striped=striped, size="sm",
        className="mb-0",
        style={"fontSize": "0.88rem"},
    )


def metric_row(items: list) -> dbc.Row:
    """一行等宽指标卡片"""
    cols = []
    for value, label, color, icon in items:
        cols.append(dbc.Col(stat_card(value, label, color, icon), md=12 // len(items), className="mb-3"))
    return dbc.Row(cols)


def status_badge(text: str, color: str = "secondary") -> html.Span:
    """状态标签"""
    return html.Span(text, className=f"badge bg-{color}",
                    style={"fontSize": "0.85rem", "padding": "4px 12px"})


def chart_card(figure, title: str = None) -> dbc.Card:
    """包裹图表的卡片"""
    children = [dcc.Graph(figure=figure, className="rounded")]
    if title:
        children = [dbc.CardHeader([
            html.I(className="bi bi-graph-up me-1"),
            title,
        ], style={"fontSize": "0.9rem"})] + children
    return dbc.Card(children, className="shadow-sm mb-3",
                    style={"borderRadius": "var(--glass-radius, 14px)"})


def table_card(header: str, table: dbc.Table, icon: str = None) -> dbc.Card:
    """包裹表格的卡片"""
    icon_el = html.I(className=f"bi bi-{icon} me-2") if icon else None
    return dbc.Card([
        dbc.CardHeader([icon_el, header], style={"fontSize": "0.9rem", "fontWeight": 600}),
        dbc.CardBody(table, className="p-2"),
    ], className="shadow-sm h-100 mb-3",
        style={"borderRadius": "var(--glass-radius, 14px)"})


from dash import dcc  # noqa: E402 — dcc needed only for chart_card
