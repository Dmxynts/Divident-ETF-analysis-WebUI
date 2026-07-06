"""
因子归因分析 (Barra多因子模型思维)
拆解红利ETF的超额收益来源：纯红利因子 vs. 低波因子 vs. 价值因子
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict

import statsmodels.api as sm


def _fit_ols(X: pd.DataFrame, y: pd.Series) -> sm.OLS:
    """添加截距并拟合 OLS 回归（模块级函数，供实例方法和静态方法共用）"""
    X_const = sm.add_constant(X)
    return sm.OLS(y, X_const).fit()


class FactorAttribution:
    """
    对红利ETF进行因子归因分析
    模型: Y = α + β1*DivYield + β2*BP + β3*Volatility + β4*Size + β5*Momentum + ε
    """

    def __init__(self):
        self.factor_data: Optional[pd.DataFrame] = None
        self.regression_result: Optional[dict] = None

    def prepare_factor_data(self, stock_returns: pd.DataFrame,
                             factor_values: Dict[str, pd.Series]) -> pd.DataFrame:
        """
        准备因子数据
        Parameters
        ----------
        stock_returns : DataFrame index=date, columns=stock_code
        factor_values : dict of {factor_name: Series(index=date, value)}
        """
        df = pd.DataFrame(index=stock_returns.index)
        for name, series in factor_values.items():
            df[name] = series
        # 平均收益作为Y
        df["return"] = stock_returns.mean(axis=1)
        self.factor_data = df.dropna()
        return self.factor_data

    def run_regression(self, y_col: str = "return") -> dict:
        """
        运行多元线性回归
        Returns
        -------
        dict: coefficients, t-stats, r_squared, etc.
        """
        if self.factor_data is None:
            raise ValueError("请先准备因子数据")

        X_cols = [c for c in self.factor_data.columns if c != y_col]
        model = _fit_ols(self.factor_data[X_cols], self.factor_data[y_col])

        self.regression_result = {
            "因子": ["截距"] + X_cols,
            "系数": model.params.tolist(),
            "t值": model.tvalues.tolist(),
            "p值": model.pvalues.tolist(),
            "R²": model.rsquared,
            "调整R²": model.rsquared_adj,
            "F值": model.fvalue,
        }
        return self.regression_result

    def factor_contribution(self) -> pd.DataFrame:
        """计算各因子对收益的贡献度"""
        if self.regression_result is None:
            self.run_regression()

        df = pd.DataFrame(self.regression_result)
        # 去掉截距
        contrib = df[df["因子"] != "截距"].copy()
        abs_coef = contrib["系数"].abs()
        contrib["贡献度"] = abs_coef / abs_coef.sum()
        contrib = contrib.sort_values("贡献度", ascending=False)
        return contrib[["因子", "系数", "t值", "p值", "贡献度"]]

    def decompose_etf_return(self, etf_returns: pd.Series,
                              factor_returns: pd.DataFrame) -> pd.DataFrame:
        """
        对ETF收益进行因子分解
        Y(t) = α + Σ βi * Fi(t) + ε(t)
        Parameters
        ----------
        etf_returns : Series of ETF daily returns
        factor_returns : DataFrame of factor returns (columns=factor names)
        """
        # 对齐
        df = factor_returns.copy()
        df["ETF_return"] = etf_returns
        df = df.dropna()

        X = df.drop(columns=["ETF_return"])
        model = _fit_ols(X, df["ETF_return"])

        # 分解收益（使用已含截距的设计矩阵做预测）
        X_design = model.model.exog
        decomp = pd.DataFrame(index=df.index)
        decomp["实际收益"] = df["ETF_return"]
        decomp["解释收益"] = model.predict(X_design)
        decomp["Alpha"] = model.params["const"]
        decomp["残差"] = df["ETF_return"] - decomp["解释收益"]

        for col in df.drop(columns=["ETF_return"]).columns:
            decomp[f"{col}_贡献"] = model.params[col] * df[col]

        return decomp

    @staticmethod
    def summary_text(factor_contrib: pd.DataFrame, r_squared: float = None) -> str:
        """生成因子归因的文字总结"""
        lines = ["=" * 50, "红利ETF因子归因分析", "=" * 50]
        for _, row in factor_contrib.iterrows():
            sig = "***" if row["p值"] < 0.01 else "**" if row["p值"] < 0.05 else "*" if row["p值"] < 0.1 else ""
            lines.append(
                f"{row['因子']:15s}  系数={row['系数']:+.4f}  t={row['t值']:+.2f}  "
                f"贡献度={row['贡献度']:.1%}{sig}"
            )
        if r_squared is not None:
            lines.append(f"\nR² = {r_squared:.4f}")
        lines.append("\n结论: 红利ETF的超额收益中")
        lines.append("  如果有显著的低波因子暴露 → 说明涨是因低波而非高股息")
        lines.append("  如果有显著的价值因子暴露 → 说明涨是因估值修复而非分红")
        return "\n".join(lines)

    @staticmethod
    def rolling_factor_beta(etf_returns: pd.Series,
                             factor_returns: pd.DataFrame,
                             window: int = 60) -> pd.DataFrame:
        """
        滚动计算因子Beta（时变因子暴露）
        Parameters
        ----------
        window : int  滚动窗口天数，默认60天
        """
        df = factor_returns.copy()
        df["ETF_return"] = etf_returns
        df = df.dropna()

        results = []
        for i in range(window, len(df)):
            chunk = df.iloc[i - window:i]
            model = _fit_ols(chunk.drop(columns=["ETF_return"]), chunk["ETF_return"])
            row = {"date": chunk.index[-1]}
            for col_name, param in zip(model.model.exog_names, model.params):
                row[f"{col_name}_beta"] = param
            results.append(row)

        return pd.DataFrame(results).set_index("date")
