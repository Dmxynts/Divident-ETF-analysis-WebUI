"""
波动率建模模块
使用 GARCH(1,1) 模型预测红利ETF的波动率变化
识别统计意义上显著的加仓/减仓信号
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple

from arch import arch_model


class VolatilityModel:
    """
    GARCH族波动率模型
    - GARCH(1,1)预测未来波动率
    - 波动率扩张/收敛识别
    - 3-Sigma事件检测（极端加仓信号）
    """

    def __init__(self, p: int = 1, q: int = 1, forecast_days: int = 5,
                 dist: str = "studentst", model_type: str = "EGARCH",
                 z_high: float = 2.0, z_mid: float = 1.5, z_low: float = 1.0,
                 z_neg_high: float = -1.5, z_neg_low: float = -1.0):
        self.p = p
        self.q = q
        self.forecast_days = forecast_days
        self.dist = dist
        self.model_type = model_type
        self.z_high = z_high
        self.z_mid = z_mid
        self.z_low = z_low
        self.z_neg_high = z_neg_high
        self.z_neg_low = z_neg_low
        self.model = None
        self.results = None
        self.vol_data: Optional[pd.DataFrame] = None

    def fit_garch(self, returns: pd.Series, dates: Optional[pd.Series] = None) -> dict:
        """
        拟合 GARCH(p,q) 模型

        支持模型类型:
        - "Garch": 标准 GARCH，对称响应
        - "EGARCH": 指数 GARCH，捕捉杠杆效应（对数方差形式）
        - "GJR-GARCH": 门限 GARCH，用虚拟变量捕捉非对称性

        Parameters
        ----------
        returns : pd.Series  日收益率序列（小数，如 0.01 表示 +1%）
        dates : pd.Series, optional  对应日期，用于记录

        Returns
        -------
        dict: 模型参数、AIC、BIC等
        """
        # 转百分比确保数值稳定，同时允许 arch 自动 rescale
        returns_pct = returns * 100

        # EGARCH 和 GJR-GARCH 需 o=1 来启用杠杆效应
        vol_type = self.model_type
        asym_term = 0
        if self.model_type == "GJR-GARCH":
            vol_type = "Garch"
            asym_term = 1
        elif self.model_type == "EGARCH":
            asym_term = 1  # 加上 gamma[1] 杠杆项

        self.model = arch_model(
            returns_pct,
            vol=vol_type,
            p=self.p,
            o=asym_term,
            q=self.q,
            dist=self.dist,
        )
        self.results = self.model.fit(disp="off")

        # arch 输出在百分比单位，转回小数
        conditional_vol = self.results.conditional_volatility / 100

        self.vol_data = pd.DataFrame(
            {"returns": returns, "conditional_vol": conditional_vol},
            index=returns.index
        )
        # 标准化残差：若模型正确设定应为 ~N(0,1)，GARCH 诊断的基本统计量
        if hasattr(self.results, "std_resid") and self.results.std_resid is not None:
            self.vol_data["std_resid"] = self.results.std_resid.values
        else:
            self.vol_data["std_resid"] = self.results.resid / conditional_vol
        # 波动率体制 Z-Score（检测波动率自身的突变）
        mv = self.vol_data["conditional_vol"].rolling(252, min_periods=60).mean()
        sv = self.vol_data["conditional_vol"].rolling(252, min_periods=60).std()
        self.vol_data["vol_zscore"] = (self.vol_data["conditional_vol"] - mv) / sv
        if dates is not None:
            self.vol_data["date"] = dates.values

        # 杠杆参数名: arch 包统一使用 gamma[1]
        asym_key = "gamma[1]"

        return {
            "模型": self.model_type,
            "分布": self.dist,
            "omega": self.results.params.get("omega", 0),
            "alpha[1]": self.results.params.get("alpha[1]", 0),
            "asym": self.results.params.get(asym_key, None),
            "beta[1]": self.results.params.get("beta[1]", 0),
            "nu(自由度)": self.results.params.get("nu", None),
            "AIC": self.results.aic,
            "BIC": self.results.bic,
            "持久性": self._persistence(),
            "半衰期(天)": self._half_life(),
        }

    def _persistence(self) -> float:
        """模型持久性（各模型计算公式不同）"""
        if self.results is None:
            return 0
        alpha = self.results.params.get("alpha[1]", 0)
        beta = self.results.params.get("beta[1]", 0)

        if self.model_type == "GJR-GARCH":
            asym = self.results.params.get("gamma[1]", 0)
            return alpha + beta + asym / 2
        elif self.model_type == "EGARCH":
            return beta
        else:
            return alpha + beta

    def _half_life(self) -> float:
        """波动率冲击的半衰期"""
        pers = self._persistence()
        if pers >= 1:
            return np.inf
        return -np.log(2) / np.log(pers) if pers > 0 else 0

    def compute_news_impact_curve(self, n_points: int = 100) -> pd.DataFrame:
        """
        新闻冲击曲线 (News Impact Curve)

        展示不同方向和大小的收益率冲击（ε）对下一期条件波动率的影响。
        固定 σ²_t = 无条件方差（长期均值），遍历 ε ∈ [-4σ, 4σ]。

        - GARCH:      正负冲击对称（只取决于 ε²），曲线为抛物线
        - EGARCH:     不对称，负冲击推高波动更多（杠杆效应）
        - GJR-GARCH:  不对称，负冲击通过 γ 项额外放大波动

        Returns
        -------
        DataFrame: shock(冲击), vol(下一期波动率, 小数)
        """
        if self.results is None:
            raise ValueError("请先拟合模型")

        params = self.results.params
        omega = params.get("omega", 0)
        alpha1 = params.get("alpha[1]", 0)
        beta1 = params.get("beta[1]", 0)
        gamma1 = params.get("gamma[1]", 0)
        mt = self.model_type

        # 无条件方差（百分比平方）
        pers = self._persistence()
        if pers >= 1:
            uncond_var = np.var(self.results.resid)  # fallback
        else:
            uncond_var = omega / (1 - pers)

        uncond_vol = np.sqrt(uncond_var)
        shocks = np.linspace(-4 * uncond_vol, 4 * uncond_vol, n_points)

        if mt == "EGARCH":
            from scipy.stats import norm
            e_abs_z = np.sqrt(2 / np.pi)
            ln_uncond = np.log(uncond_var)
            # z = ε / σ (标准化冲击)
            z = shocks / uncond_vol
            ln_var = omega + alpha1 * (abs(z) - e_abs_z) + gamma1 * z + beta1 * ln_uncond
            next_vol = np.sqrt(np.exp(ln_var))
        else:
            if mt == "GJR-GARCH":
                asym = np.where(shocks < 0, gamma1, 0)
            else:
                asym = 0
            next_var = omega + (alpha1 + asym) * shocks**2 + beta1 * uncond_var
            next_vol = np.sqrt(next_var)

        return pd.DataFrame({
            "shock": shocks / 100,          # 百分比 → 小数
            "vol": next_vol / 100,          # 百分比 → 小数
        })

    def forecast_volatility(self, days: int = None, alpha: float = 0.10) -> pd.DataFrame:
        """
        预测未来波动率（含置信区间）

        用残差 bootstrap 模拟未来波动率的完整后验分布：
        1. 从标准化残差中有放回抽样，生成未来收益率路径
        2. 沿每条路径递推计算条件方差（因模型类型而异）
        3. 取解析预测作为点估计，bootstrap 分位数作为置信区间
        模拟路径随预测步长自然发散，CI 宽度自动增加。

        Parameters
        ----------
        days : int  预测天数
        alpha : float  显著性水平, 默认0.10 → 90%置信区间

        Returns
        -------
        DataFrame: point(点估计), lower(下界), upper(上界)
        """
        if self.results is None:
            raise ValueError("请先拟合模型")

        days = days or self.forecast_days

        # 点估计：GARCH 解析预测（EGARCH 多步需用 simulation）
        if self.model_type == "EGARCH" and days > 1:
            fcst = self.results.forecast(horizon=days, method="simulation")
        else:
            fcst = self.results.forecast(horizon=days)
        # fcst.variance 是百分比平方 (因 fit 时输入 returns*100)，转回小数
        point_vol = np.sqrt(fcst.variance.iloc[-1] / 10000)

        # 残差 bootstrap 获得 CI
        std_resid = self.results.std_resid.dropna().values
        if len(std_resid) < 10:
            result = pd.DataFrame({
                "point": point_vol.values,
                "lower": point_vol.values * 0.5,
                "upper": point_vol.values * 1.5,
            })
            result.index.name = "horizon"
            return result

        n_sim = min(2000, len(std_resid) * 10)
        params = self.results.params
        omega = params.get("omega", 0)
        alpha1 = params.get("alpha[1]", 0)
        beta1 = params.get("beta[1]", 0)
        gamma1 = params.get("gamma[1]", 0)
        mt = self.model_type

        last_var = max(self.results.conditional_volatility.iloc[-1]**2, 1e-15)
        sim_vols = np.zeros((n_sim, days))

        if mt == "EGARCH":
            from scipy.stats import norm
            e_abs_z = np.sqrt(2 / np.pi)
            ln_last = np.log(last_var)
            for i in range(n_sim):
                z = np.random.choice(std_resid, size=days)
                lvt = ln_last
                for h in range(days):
                    zh = z[h]
                    lvt = omega + alpha1 * (abs(zh) - e_abs_z) + gamma1 * zh + beta1 * lvt
                    sim_vols[i, h] = np.sqrt(max(np.exp(lvt), 1e-15))
        else:
            for i in range(n_sim):
                z = np.random.choice(std_resid, size=days)
                vt = last_var
                for h in range(days):
                    zh = z[h]
                    asym = gamma1 if (mt == "GJR-GARCH" and zh < 0) else 0
                    vt = omega + (alpha1 + asym) * zh**2 * vt + beta1 * vt
                    vt = max(vt, 1e-15)
                    sim_vols[i, h] = np.sqrt(vt)

        result = pd.DataFrame({
            "point": point_vol.values,
            "lower": np.percentile(sim_vols, 100 * alpha / 2, axis=0) / 100,
            "upper": np.percentile(sim_vols, 100 * (1 - alpha / 2), axis=0) / 100,
        })
        result.index.name = "horizon"
        return result

    def detect_extreme_events(self, n_sigma: float = 3.0) -> pd.DataFrame:
        """
        检测极端事件（GARCH 标准化残差诊断）

        使用标准化残差 z_t = ε_t / σ_t（~N(0,1) 若模型正确设定）：
          |z_t| > 3  → 该日收益率超出了模型预期的 3 倍条件波动率
          z_t > +3   → 正向极端（收益率骤升）
          z_t < -3   → 负向极端（收益率骤降，恐慌）

        同时保留 vol_of_vol_zscore 反映波动率体制的突变。

        Returns
        -------
        DataFrame: date, conditional_vol, z_score, signal
        """
        if self.vol_data is None:
            raise ValueError("请先拟合模型")

        df = self.vol_data.copy()

        # 标准化残差 Z-Score（GARCH 模型的基本诊断统计量）
        if "std_resid" in df.columns:
            df["z_score"] = df["std_resid"]
        else:
            df["z_score"] = 0

        # 波动率自身的 Z-Score（检测波动率体制突变）
        mean_v = df["conditional_vol"].rolling(252, min_periods=60).mean()
        std_v = df["conditional_vol"].rolling(252, min_periods=60).std()
        df["vol_of_vol_zscore"] = (df["conditional_vol"] - mean_v) / std_v

        # 信号：基于标准化残差的极端值
        df["signal"] = "正常"
        df.loc[df["z_score"] > n_sigma, "signal"] = "恐慌加仓(收益率骤降)"
        df.loc[df["z_score"] < -n_sigma, "signal"] = "平静减仓(收益率骤升)"

        cols = ["conditional_vol", "z_score", "vol_of_vol_zscore", "signal"]
        if "date" in df.columns:
            cols.insert(0, "date")
        return df[cols].dropna()

    def get_composite_signal(self, returns: Optional[pd.Series] = None) -> dict:
        """
        细分化波动率信号: 从四个维度评分

        已拟合模型后可省略 returns 重复传入，避免重复拟合 GARCH。

        Parameters
        ----------
        returns : pd.Series, optional  日收益率序列（未拟合时必传）

        Returns
        -------
        dict: level_score, trend_score, forecast_score, event_score, vol_zscore
        """
        if self.results is None:
            if returns is None:
                raise ValueError("请先拟合模型（调用 fit_garch）或提供收益率数据")
            self.fit_garch(returns)

        cv = self.vol_data["conditional_vol"]
        if len(cv) < 60:
            return {
                "level_score": 0, "trend_score": 0,
                "forecast_score": 0, "event_score": 0,
                "vol_zscore": 0,
            }

        # --- 1. Level: 当前波动率 Z-Score（使用可配置阈值） ---
        mean_vol = cv.rolling(252, min_periods=60).mean()
        std_vol = cv.rolling(252, min_periods=60).std()
        current_z = (cv.iloc[-1] - mean_vol.iloc[-1]) / std_vol.iloc[-1]

        if current_z > self.z_high:
            level_score = 1.0
        elif current_z > self.z_mid:
            level_score = 0.7
        elif current_z > self.z_low:
            level_score = 0.4
        elif current_z < self.z_neg_high:
            level_score = -0.8
        elif current_z < self.z_neg_low:
            level_score = -0.4
        else:
            level_score = np.clip(current_z / 3, -0.5, 0.5)

        # --- 2. Trend: 短均线 vs 长均线 ---
        short_ma = cv.rolling(20, min_periods=10).mean()
        long_ma = cv.rolling(60, min_periods=30).mean()
        vol_ratio = short_ma.iloc[-1] / long_ma.iloc[-1] - 1
        # vol_ratio > 0 → 波动在上升 = 负向信号
        trend_score = np.clip(-vol_ratio * 5, -1, 1)

        # --- 3. Forecast: GARCH 预测方向 ---
        try:
            fcst = self.forecast_volatility(days=5)
            forecast_vol = fcst["point"].mean()
            current_vol = cv.iloc[-1]
            fcst_change = forecast_vol / current_vol - 1
            # forecast 升高 = 谨慎, 降低 = 利好
            forecast_score = np.clip(-fcst_change * 10, -1, 1)
        except Exception:
            forecast_score = 0

        # --- 4. Event: 极端事件信号 ---
        try:
            events = self.detect_extreme_events()
            if not events.empty:
                last_sig = events.iloc[-1]["signal"]
                if last_sig == "恐慌加仓(收益率骤降)":
                    event_score = 1.0
                elif last_sig == "平静减仓(收益率骤升)":
                    event_score = -0.8
                else:
                    event_score = 0
            else:
                event_score = 0
        except Exception:
            event_score = 0

        return {
            "level_score": round(level_score, 3),
            "trend_score": round(trend_score, 3),
            "forecast_score": round(forecast_score, 3),
            "event_score": round(event_score, 3),
            "vol_zscore": round(current_z, 3),
        }

    @staticmethod
    def compare_models(returns: pd.Series, dist: str = "studentst",
                       model_list: list = None) -> pd.DataFrame:
        """
        比较不同 GARCH 模型族的拟合效果

        Parameters
        ----------
        returns : pd.Series  日收益率序列（小数）
        dist : str           分布假设
        model_list : list    要比较的模型列表, 默认 ["Garch", "EGARCH", "GJR-GARCH"]

        Returns
        -------
        DataFrame: 各模型的 AIC、BIC、参数对比
        """
        model_list = model_list or ["Garch", "EGARCH", "GJR-GARCH"]
        results = []

        for mt in model_list:
            try:
                vm = VolatilityModel(dist=dist, model_type=mt)
                params = vm.fit_garch(returns)
                results.append({
                    "模型": mt,
                    "AIC": round(params["AIC"], 1),
                    "BIC": round(params["BIC"], 1),
                    "alpha": round(params.get("alpha[1]", 0), 4),
                    "asym": round(params.get("asym", 0), 4) if params.get("asym") is not None else "-",
                    "beta": round(params["beta[1]"], 4),
                    "nu(自由度)": round(params.get("nu(自由度)", 0), 2) if params.get("nu(自由度)") else "-",
                    "持久性": round(params["持久性"], 4),
                    "收敛": "OK",
                })
            except Exception as e:
                results.append({
                    "模型": mt, "AIC": None, "BIC": None,
                    "收敛": str(e)[:40],
                })

        df = pd.DataFrame(results)
        valid = df.dropna(subset=["AIC"])
        if not valid.empty:
            df["排名"] = None
            for i, idx in enumerate(valid.sort_values("AIC").index):
                df.loc[idx, "排名"] = i + 1
        return df

    @staticmethod
    def analyze_vol_regime(returns: pd.Series, window: int = 60) -> pd.DataFrame:
        """
        滚动波动率体制分析
        将波动率分为: 低波/正常/高波 三种状态
        """
        rolling_vol = returns.rolling(window).std() * np.sqrt(252)
        hist = rolling_vol.dropna().values

        # 三分位
        q33, q66 = np.percentile(hist, [33, 66])

        regime = pd.DataFrame(index=rolling_vol.index)
        regime["年化波动率"] = rolling_vol
        regime["体制"] = "正常"
        regime.loc[rolling_vol <= q33, "体制"] = "低波"
        regime.loc[rolling_vol >= q66, "体制"] = "高波"
        regime["建议"] = "持有"
        regime.loc[rolling_vol <= q33, "建议"] = "网格加仓区（低波稳健）"
        regime.loc[rolling_vol >= q66, "建议"] = "观望/减仓区（高波风险）"
        return regime.dropna()

    @staticmethod
    def get_entry_signal(vol_zscore: float, spread_percentile: float) -> dict:
        """
        综合波动率和利差给出买入信号
        Parameters
        ----------
        vol_zscore : float  当前波动率Z-Score
        spread_percentile : float  当前利差分位
        """
        score = 0
        reasons = []

        # 波动率信号（低位恐慌时加仓）
        if vol_zscore > 2.0:
            score += 3
            reasons.append("波动率3Sigma事件 → 恐慌加仓机会")
        elif vol_zscore > 1.5:
            score += 2
            reasons.append("波动率偏高 → 关注加仓")
        elif vol_zscore < -1.0:
            score -= 1
            reasons.append("波动率偏低 → 可能过于拥挤")

        # 利差信号
        if spread_percentile > 0.8:
            score += 2
            reasons.append("利差高位 → 高安全边际")
        elif spread_percentile < 0.2:
            score -= 2
            reasons.append("利差低位 → 安全边际不足")

        if score >= 3:
            action = "[强烈] 强烈加仓信号"
        elif score >= 1:
            action = "[温和] 温和加仓信号"
        elif score <= -1:
            action = "[注意] 减仓/观望信号"
        else:
            action = "[持有] 持有"

        return {"综合得分": score, "操作": action, "理由": " | ".join(reasons)}
