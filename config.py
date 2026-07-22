"""
幸运猩 — 彩票游戏规则配置
每种彩票的定义：号码范围、表名、API参数、预测算法权重等
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class PositionRange(NamedTuple):
    """单个号码位置的范围 [min, max]（闭区间）。"""
    lo: int
    hi: int


@dataclass
class GameConfig:
    """彩票游戏完整规则配置。"""

    # ---- 标识 ----
    key: str                          # 内部键名，如 "daletou"
    name: str                         # 中文显示名，如 "大乐透"
    icon: str                         # emoji 图标

    # ---- 数据源 ----
    api_game_no: str                  # 体彩 API gameNo 参数

    # ---- 号码规则 ----
    positions: list[PositionRange]     # 每个位置的号码范围

    # ---- 预测参数 ----
    zones: list[list[tuple[int, int]]] = field(default_factory=list)
    prediction_weights: dict[str, float] = field(default_factory=dict)
    candidates_count: int = 3000

    # ---- 显示 ----
    position_labels: list[str] = field(default_factory=list)

    # ---- 大乐透特化字段 (兼容旧红/蓝术语) ----
    red_count: int = 0                # "前区"号码个数
    blue_count: int = 0               # "后区"号码个数
    red_range: tuple[int, int] = (0, 0)
    blue_range: tuple[int, int] = (0, 0)

    @property
    def num_positions(self) -> int:
        return len(self.positions)

    @property
    def table_name(self) -> str:
        return self.key

    @property
    def total_range(self) -> int:
        """所有号码可能取值的总数（用于频次统计）。"""
        return sum(p.hi - p.lo + 1 for p in self.positions)


# ══════════════════════════════════════════════════════
#  大乐透：前区 35选5 + 后区 12选2
# ══════════════════════════════════════════════════════

DALETOU = GameConfig(
    key="daletou",
    name="大乐透",
    icon="🔴🔵",
    api_game_no="85",
    positions=[
        PositionRange(1, 35),   # 红1
        PositionRange(1, 35),   # 红2
        PositionRange(1, 35),   # 红3
        PositionRange(1, 35),   # 红4
        PositionRange(1, 35),   # 红5
        PositionRange(1, 12),   # 蓝1
        PositionRange(1, 12),   # 蓝2
    ],
    zones=[
        [(1, 7), (8, 14), (15, 21), (22, 28), (29, 35)],   # 前区 5 区
        [(1, 4), (5, 8), (9, 12)],                           # 后区 3 区
    ],
    prediction_weights={
        "频次分析": 0.20,
        "遗漏回补": 0.18,
        "重号回补": 0.12,
        "和值趋势": 0.12,
        "奇偶匹配": 0.10,
        "大小匹配": 0.06,
        "区间覆盖": 0.06,
        "连号匹配": 0.05,
        "012路匹配": 0.06,
        "质数匹配": 0.03,
        "跨度匹配": 0.02,
    },
    candidates_count=5000,
    position_labels=["红1", "红2", "红3", "红4", "红5", "蓝1", "蓝2"],
    red_count=5,
    blue_count=2,
    red_range=(1, 35),
    blue_range=(1, 12),
)

# ══════════════════════════════════════════════════════
#  七星彩：7 位数字，每位 0-9（第 7 位 0-14）
# ══════════════════════════════════════════════════════

QIXINGCAI = GameConfig(
    key="qixingcai",
    name="七星彩",
    icon="⭐",
    api_game_no="04",
    positions=[
        PositionRange(0, 9),   # 第1位
        PositionRange(0, 9),   # 第2位
        PositionRange(0, 9),   # 第3位
        PositionRange(0, 9),   # 第4位
        PositionRange(0, 9),   # 第5位
        PositionRange(0, 9),   # 第6位
        PositionRange(0, 14),  # 第7位（特别号 0-14）
    ],
    zones=[
        [(0, 4), (5, 9)],       # 每位可单独做大小分析
    ],
    prediction_weights={
        "频次分析": 0.20,
        "遗漏回补": 0.18,
        "重号回补": 0.14,
        "012路匹配": 0.16,
        "奇偶匹配": 0.16,
        "大小匹配": 0.16,
    },
    candidates_count=3000,
    position_labels=["第1位", "第2位", "第3位", "第4位", "第5位", "第6位", "第7位"],
)

# ══════════════════════════════════════════════════════
#  排列5：5 位数字，每位 0-9
# ══════════════════════════════════════════════════════

PAILIE5 = GameConfig(
    key="pailie5",
    name="排列5",
    icon="🎲",
    api_game_no="350133",
    positions=[
        PositionRange(0, 9),   # 第1位
        PositionRange(0, 9),   # 第2位
        PositionRange(0, 9),   # 第3位
        PositionRange(0, 9),   # 第4位
        PositionRange(0, 9),   # 第5位
    ],
    zones=[
        [(0, 4), (5, 9)],
    ],
    prediction_weights={
        "频次分析": 0.22,
        "遗漏回补": 0.20,
        "重号回补": 0.16,
        "012路匹配": 0.16,
        "奇偶匹配": 0.13,
        "大小匹配": 0.13,
    },
    candidates_count=3000,
    position_labels=["万位", "千位", "百位", "十位", "个位"],
)

# 注册表
ALL_GAMES: dict[str, GameConfig] = {
    "daletou": DALETOU,
    "qixingcai": QIXINGCAI,
    "pailie5": PAILIE5,
}
