"""
网格交易优化模块
结合卡尔曼滤波动态估计均衡价格，用优化算法确定最优网格参数
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from scipy.optimize import minimize
import pykalman


class KalmanFilter:
    """
    卡尔曼滤波估计短期均衡价格
    状态: 均衡价格 (random walk)
    观测: 实际价格
    """

    def __init__(self, delta: float = 1e-4, R: float = 1e-3):
        """
        Parameters
        ----------
        delta : float  状态转移方差（越小越平滑）
        R : float      观测噪声方差
        """
        self.delta = delta
        self.R = R
        self._state_means: Optional[np.ndarray] = None
        self._state_stds: Optional[np.ndarray] = None

    def fit(self, prices: np.ndarray, auto_params: bool = False) -> np.ndarray:
        """
        估计均衡价格序列

        Parameters
        ----------
        prices : 观测价格序列
        auto_params : 是否先用EM自动估计最优delta/R

        Returns
        -------
        filtered_state_means : 均衡价格序列
        """
        if auto_params:
            self.delta, self.R = self.estimate_noise(prices)

        kf = pykalman.KalmanFilter(
            transition_matrices=[1],
            observation_matrices=[1],
            initial_state_mean=prices[0],
            initial_state_covariance=1.0,
            transition_covariance=self.delta,
            observation_covariance=self.R,
        )
        means, covs = kf.filter(prices)
        self._state_means = means.flatten()
        self._state_stds = np.sqrt(covs.flatten())
        return self._state_means

    @property
    def state_std(self) -> np.ndarray:
        """滤波状态的标准差序列（反映每个时点均衡价格估计的不确定性）"""
        if self._state_stds is None:
            raise ValueError("请先调用 fit()")
        return self._state_stds

    def estimate_noise(self, prices: np.ndarray) -> Tuple[float, float]:
        """
        用EM算法估计最优的 delta（状态转移方差）和 R（观测噪声方差）
        """
        kf = pykalman.KalmanFilter(
            transition_matrices=[1],
            observation_matrices=[1],
            initial_state_mean=prices[0],
            n_dim_obs=1,
        )
        kf = kf.em(prices, n_iter=10)
        return kf.transition_covariance[0, 0], kf.observation_covariance[0, 0]


class GridOptimizer:
    """
    网格交易参数优化器
    使用历史数据计算最优网格间距和每格仓位
    目标: 最大化夏普比率 / 卡尔玛比率
    """

    def __init__(self, num_grids: int = 10, atr_period: int = 20,
                 slippage: float = 0.0001, fee_rate: float = 0.0003):
        self.num_grids = num_grids
        self.atr_period = atr_period
        self.slippage = slippage
        self.fee_rate = fee_rate
        self.optimal_params: Optional[dict] = None

    def _compute_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
        """计算平均真实波幅 (ATR)"""
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        # 简单移动平均
        atr = np.mean(tr[-self.atr_period:]) if len(tr) >= self.atr_period else np.mean(tr)
        return float(atr)

    def calibrate_grid_levels(self, prices: pd.DataFrame,
                               kalman_delta: float = 1e-4,
                               auto_estimate: bool = False) -> dict:
        """
        基于卡尔曼滤波和ATR校准网格

        Parameters
        ----------
        prices : DataFrame with columns ['close','high','low']
        kalman_delta : 状态转移方差（越小越平滑，默认1e-4适合网格交易）
        auto_estimate : 是否用EM自动估计最优参数（覆盖kalman_delta）

        Returns
        -------
        dict: grid_center, grid_spacing, grid_levels, kalman_lower, kalman_upper
        """
        close = prices["close"].values
        has_hl = "high" in prices.columns and "low" in prices.columns

        # 卡尔曼滤波求均衡价格
        kf = KalmanFilter(delta=kalman_delta)
        equilibrium = kf.fit(close, auto_params=auto_estimate)
        kalman_std = kf.state_std

        # ATR作为波动率度量（缺少 high/low 时用 close 近似）
        if has_hl:
            high = prices["high"].values
            low = prices["low"].values
            atr = self._compute_atr(high, low, close)
        else:
            atr = float(np.mean(np.abs(np.diff(close))[-self.atr_period:])) if len(close) > self.atr_period else float(np.mean(np.abs(np.diff(close))))

        # 网格间距 = ATR × 系数（防止过密）
        grid_spacing = atr * 1.5

        # 网格中心 = 最新均衡价
        grid_center = float(equilibrium[-1])

        # 生成网格层级
        grid_levels = []
        for i in range(self.num_grids // 2, 0, -1):
            grid_levels.append(grid_center - i * grid_spacing)
        grid_levels.append(grid_center)
        for i in range(1, self.num_grids // 2 + 1):
            grid_levels.append(grid_center + i * grid_spacing)

        self.optimal_params = {
            "网格中心": grid_center,
            "网格间距": grid_spacing,
            "ATR": atr,
            "网格层数": self.num_grids,
            "网格价格": [round(p, 3) for p in grid_levels],
            "均衡价": equilibrium.tolist(),
            "均衡价_上限": (equilibrium + 1.96 * kalman_std).tolist(),
            "均衡价_下限": (equilibrium - 1.96 * kalman_std).tolist(),
        }
        return self.optimal_params

    def _execute_sell(self, price: float, capital: float, grid_ratio: float,
                       n_levels: int, position: float, cash: float,
                       total_slippage: float, total_fee: float, t: int) -> dict:
        """执行一次卖出：返回更新后的状态字典"""
        exec_price = price * (1 - self.slippage)
        sell_amount = capital * grid_ratio / n_levels
        actual_sell = min(sell_amount / exec_price, position)
        trade_value = actual_sell * exec_price
        fee = trade_value * self.fee_rate
        slippage_cost = actual_sell * (price - exec_price)
        return {
            "position": position - actual_sell,
            "cash": cash + trade_value - fee,
            "total_slippage": total_slippage + slippage_cost,
            "total_fee": total_fee + fee,
            "record": {"date": t, "type": "sell", "price": price,
                       "exec_price": exec_price, "shares": actual_sell,
                       "fee": fee, "slippage_cost": slippage_cost, "cash": cash + trade_value - fee},
        }

    def _execute_buy(self, price: float, capital: float, grid_ratio: float,
                      n_levels: int, position: float, cash: float,
                      total_slippage: float, total_fee: float, t: int) -> dict:
        """执行一次买入：返回更新后的状态字典"""
        exec_price = price * (1 + self.slippage)
        buy_amount = capital * grid_ratio / n_levels
        actual_buy = min(buy_amount / exec_price, cash / exec_price)
        trade_value = actual_buy * exec_price
        fee = trade_value * self.fee_rate
        slippage_cost = actual_buy * (exec_price - price)
        return {
            "position": position + actual_buy,
            "cash": cash - trade_value - fee,
            "total_slippage": total_slippage + slippage_cost,
            "total_fee": total_fee + fee,
            "record": {"date": t, "type": "buy", "price": price,
                       "exec_price": exec_price, "shares": actual_buy,
                       "fee": fee, "slippage_cost": slippage_cost, "cash": cash - trade_value - fee},
        }

    def simulate_grid(self, price_series: pd.Series, grid_levels: list,
                       capital: float = 100000, grid_ratio: float = 0.1) -> pd.DataFrame:
        """
        模拟网格交易（含滑点和交易费用）
        Parameters
        ----------
        price_series : 价格序列
        grid_levels : 网格价格列表（从小到大）
        capital : 初始资金
        grid_ratio : 每格资金比例
        """
        cash = capital
        position = 0.0
        total_slippage = 0.0
        total_fee = 0.0
        n_levels = len(grid_levels)
        nav = []
        prev_level = -1

        for t, price in enumerate(price_series):
            # 找到当前价格在哪个网格区间
            current_level = -1
            for j, lvl in enumerate(grid_levels):
                if price >= lvl:
                    current_level = j

            # 网格触发: 穿过了某个格子边界
            if prev_level != -1 and current_level != prev_level:
                if current_level > prev_level:
                    # 上穿 → 逐格卖出
                    for lvl_idx in range(prev_level + 1, current_level + 1):
                        st = self._execute_sell(
                            grid_levels[lvl_idx], capital, grid_ratio, n_levels,
                            position, cash, total_slippage, total_fee, t,
                        )
                        position = st["position"]
                        cash = st["cash"]
                        total_slippage = st["total_slippage"]
                        total_fee = st["total_fee"]
                else:
                    # 下穿 → 逐格买入
                    for lvl_idx in range(prev_level - 1, current_level - 1, -1):
                        st = self._execute_buy(
                            grid_levels[lvl_idx], capital, grid_ratio, n_levels,
                            position, cash, total_slippage, total_fee, t,
                        )
                        position = st["position"]
                        cash = st["cash"]
                        total_slippage = st["total_slippage"]
                        total_fee = st["total_fee"]

            # 记录净资产
            total_value = cash + position * price
            nav.append({
                "date": t, "nav": total_value, "position": position, "cash": cash,
                "cumulative_slippage_cost": total_slippage,
                "cumulative_fee_cost": total_fee,
            })
            prev_level = current_level

        return pd.DataFrame(nav)

    def optimize_grid_by_sharpe(self, price_series: pd.Series,
                                  grid_levels: list) -> dict:
        """
        用优化算法搜索最优网格间距（最大化夏普比率）
        """
        from scipy.optimize import minimize_scalar

        def objective(spacing_mult):
            # 重建网格
            center = grid_levels[len(grid_levels) // 2] if grid_levels else price_series.iloc[-1]
            levels = []
            half = self.num_grids // 2
            atr_est = price_series.diff().abs().rolling(20).mean().iloc[-1]
            spacing = atr_est * spacing_mult
            for i in range(half, 0, -1):
                levels.append(center - i * spacing)
            levels.append(center)
            for i in range(1, half + 1):
                levels.append(center + i * spacing)

            nav_df = self.simulate_grid(price_series, levels)
            if nav_df.empty or len(nav_df) < 10:
                return 999

            returns = nav_df["nav"].pct_change().dropna()
            if returns.std() == 0:
                return 999

            sharpe = returns.mean() / returns.std() * np.sqrt(252)
            return -sharpe  # 最小化负夏普

        result = minimize_scalar(objective, bounds=(0.5, 4.0), method="bounded")
        return {"最优间距乘数": result.x, "最优夏普": -result.fun}

    @staticmethod
    def generate_grid_report(optimal_params: dict) -> str:
        """生成网格交易参数报告"""
        lines = [
            "=" * 50,
            "网格交易优化参数",
            "=" * 50,
            f"网格中心价格: {optimal_params.get('网格中心', 'N/A'):.3f}",
            f"网格间距: {optimal_params.get('网格间距', 'N/A'):.4f}",
            f"网格层数: {optimal_params.get('网格层数', 'N/A')}",
            f"ATR(20): {optimal_params.get('ATR', 'N/A'):.4f}",
        ]

        levels = optimal_params.get("网格价格", [])
        if levels:
            lines.append("\n网格价格层级:")
            for i, p in enumerate(levels):
                direction = "↓买" if p <= optimal_params.get("网格中心", 0) else "↑卖"
                lines.append(f"  [{i + 1:2d}] {direction}  {p:.3f}")

        return "\n".join(lines)
