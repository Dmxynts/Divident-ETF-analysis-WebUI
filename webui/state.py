"""
WebUI 全局状态：共享的量化系统实例 + 分析结果缓存
"""
from typing import Optional
from collections import OrderedDict
from dash import html
import dash_bootstrap_components as dbc
import traceback as _tb

from src.system import DividendETFQuantSystem


# 最大缓存条目数（超限时淘汰最久未访问的条目）
_MAX_CACHE_SIZE = 64


def error_alert(e: Exception) -> dbc.Alert:
    """统一的异常提示组件，消除各页面重复的 try/except 样板代码"""
    return dbc.Alert([
        html.H5(f"分析出错: {type(e).__name__}", className="alert-heading"),
        html.P(str(e)),
        html.Details([
            html.Summary("详细错误", className="text-muted small"),
            html.Pre(_tb.format_exc(), style={"fontSize": "0.75rem", "maxHeight": "200px", "overflow": "auto"}),
        ]),
    ], color="danger")


class AppState:
    """
    应用级状态：持有量化系统单例 + 跨页面结果缓存
    缓存避免用户在页面间切换时重复拉取和计算
    使用 OrderedDict 实现 LRU 淘汰，防止内存无限增长
    """

    MODULE_MAP = {
        "spread": "run_spread_timing",
        "macro": "run_macro_analysis",
        "volatility": "run_volatility_analysis",
        "risk": "run_risk_analysis",
        "grid": "run_grid_optimization",
        "factor": "run_factor_attribution",
        "timing": "run_comprehensive_timing",
    }

    def __init__(self):
        self.system = DividendETFQuantSystem()
        self._cache: OrderedDict = OrderedDict()

    def _cache_key(self, module: str, kwargs: dict) -> str:
        """生成稳定的缓存键"""
        key_parts = [module]
        for k, v in sorted(kwargs.items()):
            if v is not None:
                key_parts.append(f"{k}={v}")
        return ":".join(key_parts)

    def get_result(self, module: str, **kwargs) -> Optional[dict]:
        """获取缓存的分析结果（访问时刷新 LRU 顺序）"""
        key = self._cache_key(module, kwargs)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set_result(self, module: str, result: dict, **kwargs):
        """存入缓存（超限时淘汰最旧条目）"""
        key = self._cache_key(module, kwargs)
        self._cache[key] = result
        self._cache.move_to_end(key)
        if len(self._cache) > _MAX_CACHE_SIZE:
            self._cache.popitem(last=False)

    def run(self, module: str, **kwargs) -> dict:
        """
        运行分析（缓存优先）
        返回系统分析结果 dict
        """
        cached = self.get_result(module, **kwargs)
        if cached is not None:
            return cached
        method_name = self.MODULE_MAP[module]
        func = getattr(self.system, method_name)
        result = func(**kwargs)
        self.set_result(module, result, **kwargs)
        return result

    def clear_cache(self):
        self._cache.clear()


# 全局单例
state = AppState()
