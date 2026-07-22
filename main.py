#!/usr/bin/env python3
"""
幸运猩 — 大乐透 / 七星彩 / 排列5 智能预测系统

用法:
    python3 main.py                # 大乐透预测 5 注
    python3 main.py -g qixingcai   # 七星彩预测 5 注
    python3 main.py -g pailie5 -n 10  # 排列5预测 10 注
    python3 main.py --stats         # 查看统计
    python3 main.py --update        # 更新数据

UI 模式:
    python3 -m streamlit run app.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import ALL_GAMES, GameConfig
from data_fetcher import fetch_full, fetch_latest, load
from predictor import predict


def show_stats(config: GameConfig, data: list[dict]):
    """展示统计信息。"""
    from collections import Counter

    print(f"\n{'='*60}")
    print(f"  📊 {config.name} 历史数据统计")
    print(f"{'='*60}")
    print(f"  数据期数: {len(data)} 期")
    print(f"  时间范围: {data[0]['issue']} ~ {data[-1]['issue']}")

    # 每位置频次
    for i in range(config.num_positions):
        counter = Counter(d["numbers"][i] for d in data)
        label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
        top = counter.most_common(5)
        print(f"  {label} 热门: {top}")

    # 和值（仅大乐透）
    if config.key == "daletou":
        sums = [sum(d["numbers"][:5]) for d in data[-50:]]
        avg = sum(sums) / len(sums)
        print(f"  近50期前区和值: 均值 {avg:.0f}, 范围 {min(sums)}-{max(sums)}")


def main():
    parser = argparse.ArgumentParser(description="幸运猩 — 彩票智能预测")
    parser.add_argument("-g", "--game", default="daletou",
                        choices=["daletou", "qixingcai", "pailie5"],
                        help="彩票类型 (默认: daletou)")
    parser.add_argument("-n", "--num", type=int, default=5,
                        help="预测注数 (默认: 5)")
    parser.add_argument("--stats", action="store_true",
                        help="查看历史统计")
    parser.add_argument("--update", action="store_true",
                        help="更新数据")
    args = parser.parse_args()

    config = ALL_GAMES[args.game]

    print(f"\n🦍 幸运猩 — {config.icon} {config.name}")
    print(f'   "用数据说话，不凭感觉下注"\n')

    if args.update:
        fetch_latest(config)
        print("✅ 数据已更新")
        return

    data = load(config)
    if not data:
        print("❌ 无数据，请先运行: python3 main.py --update")
        return

    data.sort(key=lambda x: x["issue"])

    if args.stats:
        show_stats(config, data)
        return

    # 预测
    results = predict(config, data, num_predictions=args.num)

    print(f"\n{'='*60}")
    print(f"  🎯 预测结果 — {len(results)} 注")
    print(f"{'='*60}")

    for i, p in enumerate(results, 1):
        print(f"\n  第 {i} 注:")
        if config.key == "daletou":
            reds = " ".join(f"{n:02d}" for n in p.numbers[0])
            blues = " ".join(f"{n:02d}" for n in p.numbers[1])
            print(f"    前区: {reds}")
            print(f"    后区: {blues}")
        else:
            nums = [n for pos in p.numbers for n in pos]
            labels = config.position_labels
            parts = [f"{l}: {n:02d}" for l, n in zip(labels, nums)]
            print(f"    {'  '.join(parts)}")
        print(f"    得分: {p.total_score:.4f}")

    print(f"\n{'─'*60}")
    print(f"  ⚠️ 预测仅供参考，彩票有风险，理性购彩。")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
