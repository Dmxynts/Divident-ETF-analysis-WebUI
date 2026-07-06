#!/usr/bin/env python3
"""
红利ETF量化分析系统 - CLI 入口
"""
import argparse
import logging
from pathlib import Path

from config import CFG
from src.system import DividendETFQuantSystem


def setup_parser() -> argparse.ArgumentParser:
    """配置命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="红利ETF量化分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py all          # 运行全部分析
  python main.py spread       # 仅股债利差分析
  python main.py macro        # 仅宏观状态分析
  python main.py volatility   # 仅波动率分析
  python main.py risk         # 仅风险管理
  python main.py grid         # 仅网格优化
  python main.py timing       # 综合择时
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "spread", "macro", "volatility", "risk", "grid", "timing", "factor"],
        help="分析模块",
    )
    parser.add_argument(
        "--etf", type=str, default=CFG.etfs[0].code,
        help=f"ETF代码 (默认: {CFG.etfs[0].code} {CFG.etfs[0].name})",
    )
    parser.add_argument(
        "--index", type=str, default=CFG.etfs[0].index_code,
        help=f"指数代码 (默认: {CFG.etfs[0].index_code} {CFG.etfs[0].index_name})",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="输出图表到 output/ 目录",
    )
    parser.add_argument(
        "--tune", action="store_true",
        help="对HMM模型进行参数对比调优 (需搭配 macro 命令)",
    )
    return parser


def main():
    """主函数"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = setup_parser()
    args = parser.parse_args()
    system = DividendETFQuantSystem()

    CFG.output_dir.mkdir(parents=True, exist_ok=True)

    cmd_map = {
        "all": lambda: system.run_all(args.index, args.etf, args.plot),
        "spread": lambda: system.run_spread_timing(args.index, plot=args.plot),
        "macro": lambda: system.run_macro_analysis(plot=args.plot, tune=args.tune),
        "volatility": lambda: system.run_volatility_analysis(args.etf, plot=args.plot),
        "risk": lambda: system.run_risk_analysis(args.etf),
        "grid": lambda: system.run_grid_optimization(args.etf),
        "timing": lambda: system.run_comprehensive_timing(args.index),
        "factor": lambda: system.run_factor_attribution(args.etf),
    }

    func = cmd_map.get(args.command)
    if func:
        func()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
