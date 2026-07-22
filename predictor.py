"""
幸运猩 — 预测引擎 v3.0
时间衰减 + 重号分析 + 跨度/012路/质数 + 自适应权重 + 多样性采样
"""

import random
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from config import GameConfig, ALL_GAMES


@dataclass
class Prediction:
    """单注预测结果。"""
    numbers: list[list[int]]
    total_score: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)

    def format_str(self, config: GameConfig) -> str:
        if config.key == "daletou":
            reds = ' '.join(f'{n:02d}' for n in self.numbers[0])
            blues = ' '.join(f'{n:02d}' for n in self.numbers[1])
            return f"{reds}  |  {blues}"
        else:
            nums = [self.numbers[i][0] for i in range(config.num_positions)]
            return ' '.join(f'{n:02d}' for n in nums)


# ═══════════════════════════════════════════════════════════
# v3.0 核心: 时间衰减权重
# ═══════════════════════════════════════════════════════════

def _decay_weights(data_len: int, half_life: float = 0.3) -> list[float]:
    """
    指数衰减权重: 最近一期权重最高。
    half_life=0.3 表示 30% 总数据量处权重衰减到 0.5。
    """
    n = data_len
    decay = math.log(2) / (n * half_life)
    weights = [math.exp(-decay * (n - 1 - i)) for i in range(n)]
    # 归一化
    total = sum(weights)
    return [w / total * n for w in weights]


# ═══════════════════════════════════════════════════════════
# 号码分析维度
# ═══════════════════════════════════════════════════════════

def _is_prime(n: int) -> bool:
    if n < 2: return False
    for d in range(2, int(math.sqrt(n)) + 1):
        if n % d == 0: return False
    return True


def _compute_freq_with_decay(numbers_list: list[list[int]],
                              decay_w: list[float],
                              rng: range) -> dict[int, float]:
    """带时间衰减的频次得分。"""
    counter = defaultdict(float)
    for i, nums in enumerate(numbers_list):
        w = decay_w[i]
        for n in nums:
            counter[n] += w
    max_c = max(counter.values()) if counter else 1
    total = sum(counter.values())
    return {n: (counter[n] / max_c) * (counter[n] / total) * 2
            for n in rng}


def _compute_missing_with_decay(numbers_list: list[list[int]],
                                 decay_w: list[float],
                                 rng: range) -> dict[int, float]:
    """带时间衰减的遗漏值得分。"""
    max_w = max(decay_w)
    last_w = {n: max_w * 2 for n in rng}
    for i, nums in enumerate(numbers_list):
        for n in nums:
            last_w[n] = max(0, max_w - decay_w[i])

    return {n: min(1.0, last_w[n] / max_w) for n in rng}


def _compute_repeat(numbers_list: list[list[int]],
                     lookback: int, rng: range) -> dict[int, float]:
    """最近 N 期重号频率。"""
    recent = numbers_list[:min(lookback, len(numbers_list))]
    counter = Counter()
    for nums in recent:
        counter.update(nums)
    max_c = max(counter.values()) if counter else 1
    return {n: counter.get(n, 0) / max_c for n in rng}


def _compute_adjacent(numbers_list: list[list[int]],
                       rng: range) -> dict[int, float]:
    """邻号: 最近一期开奖号码的 ±1 邻居。"""
    if not numbers_list:
        return {n: 0.0 for n in rng}
    last = set(numbers_list[0])
    adj = set()
    for x in last:
        if x - 1 in rng: adj.add(x - 1)
        if x + 1 in rng: adj.add(x + 1)
    return {n: 0.8 if n in adj else 0.2 for n in rng}


# ═══════════════════════════════════════════════════════════
# 大乐透预测
# ═══════════════════════════════════════════════════════════

def predict_daletou(data: list[dict], config: GameConfig,
                     num_predictions: int) -> list[Prediction]:
    RED_COUNT = config.red_count    # 5
    BLUE_COUNT = config.blue_count  # 2
    RED_HI = config.red_range[1]    # 35
    BLUE_HI = config.blue_range[1]  # 12
    TOTAL = len(data)

    reds_hist = [d["numbers"][:RED_COUNT] for d in data]
    blues_hist = [d["numbers"][RED_COUNT:] for d in data]
    red_rng = range(1, RED_HI + 1)
    blue_rng = range(1, BLUE_HI + 1)

    # ── 时间衰减 ──
    dw = _decay_weights(TOTAL)

    # ── 红球维度 ──
    r_freq = _compute_freq_with_decay(reds_hist, dw, red_rng)
    r_miss = _compute_missing_with_decay(reds_hist, dw, red_rng)
    r_repeat = _compute_repeat(reds_hist, 10, red_rng)
    r_adj = _compute_adjacent(reds_hist, red_rng)

    # 质数 / 合数
    r_prime = {n: 1.0 if _is_prime(n) else 0.3 for n in red_rng}

    # ── 蓝球维度 ──
    b_freq = _compute_freq_with_decay(blues_hist, dw, blue_rng)
    b_miss = _compute_missing_with_decay(blues_hist, dw, blue_rng)
    b_repeat = _compute_repeat(blues_hist, 10, blue_rng)
    b_adj = _compute_adjacent(blues_hist, blue_rng)

    # ── 模式统计 (全历史) ──
    # 奇偶
    oe_counter = Counter()
    bs_counter = Counter()
    m3_counter = Counter()   # 除3余数分布
    spans = []
    for r in reds_hist:
        odd = sum(1 for n in r if n % 2 == 1)
        oe_counter[odd] += 1
        big = sum(1 for n in r if n >= 18)
        bs_counter[big] += 1
        m3 = tuple(sorted(Counter(n % 3 for n in r).values()))
        m3_counter[m3] += 1
        spans.append(max(r) - min(r))

    # 加权奇偶: 最近 50 期
    recent_n = min(50, TOTAL)
    oe_recent = Counter()
    bs_recent = Counter()
    for r in reds_hist[:recent_n]:
        oe_recent[sum(1 for n in r if n % 2 == 1)] += 1
        bs_recent[sum(1 for n in r if n >= 18)] += 1
    # 合并历史+近期
    for k, v in oe_recent.items():
        oe_counter[k] = oe_counter.get(k, 0) + v * 2  # 近期权重翻倍
    for k, v in bs_recent.items():
        bs_counter[k] = bs_counter.get(k, 0) + v * 2

    target_odd = oe_counter.most_common(1)[0][0]
    target_big = bs_counter.most_common(1)[0][0]

    # 和值
    sums = [sum(r) for r in reds_hist]
    recent_sums = sums[:min(50, TOTAL)]
    avg_sum = (sum(recent_sums) / len(recent_sums) + sum(sums) / len(sums)) / 2
    std_sum = (sum((s - avg_sum) ** 2 for s in sums) / len(sums)) ** 0.5

    # 跨度
    avg_span = sum(spans) / len(spans)
    std_span = (sum((s - avg_span) ** 2 for s in spans) / len(spans)) ** 0.5

    # 连号概率
    consec_count = sum(1 for r in reds_hist if any(
        r[j + 1] - r[j] == 1 for j in range(len(r) - 1)))
    consec_prob = consec_count / TOTAL

    # 012 路理想分布 (历史均值)
    m3_avg = [0, 0, 0]
    for r in reds_hist:
        for n in r:
            m3_avg[n % 3] += 1
    m3_total = sum(m3_avg)
    m3_target = [x / m3_total for x in m3_avg]

    # ── 权重配置 ──
    weights = {
        "频次分析": 0.20, "遗漏回补": 0.18, "重号回补": 0.12,
        "和值趋势": 0.12, "奇偶匹配": 0.10, "大小匹配": 0.06,
        "区间覆盖": 0.06, "连号匹配": 0.05, "012路匹配": 0.06,
        "质数匹配": 0.03, "跨度匹配": 0.02,
    }

    # ── 蒙特卡洛 ──
    candidates: list[Prediction] = []

    for _ in range(config.candidates_count):
        # --- 红球采样 ---
        pool = list(red_rng)
        chosen = []
        remaining = list(pool)
        # 综合权重: 频次 × 遗漏 × 重号 × 邻号 × 质数
        rem_w = [
            r_freq.get(n, 0.001) * 0.35 +
            r_miss.get(n, 0) * 0.30 +
            r_repeat.get(n, 0) * 0.20 +
            r_adj.get(n, 0) * 0.15
            for n in remaining
        ]

        for _ in range(RED_COUNT):
            tw = sum(rem_w)
            if tw <= 0: break
            r = random.random() * tw
            cum = 0; pick = 0
            for j, w in enumerate(rem_w):
                cum += w
                if r <= cum: pick = j; break
            chosen.append(remaining.pop(pick))
            rem_w.pop(pick)
        if len(chosen) < RED_COUNT: continue
        chosen.sort()

        # --- 红球评分 ---
        scores = {}

        # 频次
        fs = sum(r_freq.get(n, 0) for n in chosen) / RED_COUNT
        scores["频次分析"] = round(fs, 3)

        # 遗漏
        ms = sum(r_miss.get(n, 0) for n in chosen) / RED_COUNT
        scores["遗漏回补"] = round(ms, 3)

        # 重号 (最近3期)
        recent_3 = set()
        for nums in reds_hist[:3]: recent_3.update(nums)
        rp_score = sum(1 for n in chosen if n in recent_3) / RED_COUNT
        scores["重号回补"] = round(rp_score, 3)

        # 和值趋势 (连续评分, 不二分)
        rs = sum(chosen)
        sum_dev = abs(rs - avg_sum) / max(std_sum * 2, 1)
        sum_score = max(0, 1.0 - sum_dev * 0.5)
        scores["和值趋势"] = round(sum_score, 3)

        # 跨度
        span = max(chosen) - min(chosen)
        span_dev = abs(span - avg_span) / max(std_span * 2, 1)
        span_score = max(0, 1.0 - span_dev * 0.5)
        scores["跨度匹配"] = round(span_score, 3)

        # 奇偶 (连续评分)
        odd_cnt = sum(1 for n in chosen if n % 2 == 1)
        oe_score = max(0, 1.0 - abs(odd_cnt - target_odd) * 0.25)
        scores["奇偶匹配"] = round(oe_score, 3)

        # 大小 (连续评分)
        big_cnt = sum(1 for n in chosen if n >= 18)
        bs_score = max(0, 1.0 - abs(big_cnt - target_big) * 0.3)
        scores["大小匹配"] = round(bs_score, 3)

        # 012路
        m3_cnt = Counter(n % 3 for n in chosen)
        m3_score = sum(
            max(0, 1.0 - abs(m3_cnt.get(i, 0) / RED_COUNT - m3_target[i]) * 2)
            for i in range(3)
        ) / 3
        scores["012路匹配"] = round(m3_score, 3)

        # 区间
        zones = [(1, 7), (8, 14), (15, 21), (22, 28), (29, 35)]
        z_covered = sum(1 for lo, hi in zones
                         if any(lo <= n <= hi for n in chosen))
        zone_score = z_covered / len(zones)
        scores["区间覆盖"] = round(zone_score, 3)

        # 连号 (连续评分)
        has_consec = any(chosen[j+1]-chosen[j]==1
                          for j in range(len(chosen)-1))
        consec_score = 1.0 if has_consec == (consec_prob > 0.45) else (
            0.3 if has_consec else 0.5)
        scores["连号匹配"] = round(consec_score, 3)

        # 质数
        prime_cnt = sum(1 for n in chosen if _is_prime(n))
        prime_ideal = RED_COUNT * 22 / 35  # 35个数中22个质数→约3.14个/5
        pr_score = max(0, 1.0 - abs(prime_cnt - prime_ideal) * 0.4)
        scores["质数匹配"] = round(pr_score, 3)

        # --- 蓝球采样 ---
        pool_b = list(blue_rng)
        rem_b = list(pool_b)
        rem_bw = [
            b_freq.get(n, 0.001) * 0.35 +
            b_miss.get(n, 0) * 0.30 +
            b_repeat.get(n, 0) * 0.20 +
            b_adj.get(n, 0) * 0.15
            for n in rem_b
        ]
        chosen_b = []
        for _ in range(BLUE_COUNT):
            tw = sum(rem_bw)
            if tw <= 0: break
            r = random.random() * tw
            cum = 0; pick = 0
            for j, w in enumerate(rem_bw):
                cum += w
                if r <= cum: pick = j; break
            chosen_b.append(rem_b.pop(pick))
            rem_bw.pop(pick)
        if len(chosen_b) < BLUE_COUNT: continue
        chosen_b.sort()

        # 蓝球频次并入总分
        bf = sum(b_freq.get(n, 0) for n in chosen_b) / BLUE_COUNT
        bm = sum(b_miss.get(n, 0) for n in chosen_b) / BLUE_COUNT
        scores["频次分析"] = round(scores["频次分析"] * 0.7 + bf * 0.3, 3)
        scores["遗漏回补"] = round(scores["遗漏回补"] * 0.7 + bm * 0.3, 3)

        # 总分
        total_score = sum(scores[k] * weights[k] for k in scores)

        candidates.append(Prediction(
            numbers=[chosen, chosen_b],
            total_score=round(total_score, 4),
            scores=scores,
        ))

    # ── 排序 + 多样性去重 ──
    candidates.sort(key=lambda p: p.total_score, reverse=True)
    seen = set()
    unique = []
    for p in candidates:
        # 红球+蓝球联合去重
        key = (tuple(p.numbers[0]), tuple(p.numbers[1]))
        if key not in seen:
            seen.add(key)
            unique.append(p)
        if len(unique) >= num_predictions:
            break

    return unique[:num_predictions]


# ═══════════════════════════════════════════════════════════
# 数字彩预测
# ═══════════════════════════════════════════════════════════

def predict_digit(config: GameConfig, data: list[dict],
                   num_predictions: int) -> list[Prediction]:
    TOTAL = len(data)
    dw = _decay_weights(TOTAL)

    # 每位独立统计
    pos_data = [[d["numbers"][i] for d in data]
                for i in range(config.num_positions)]

    pos_stats = []
    for i in range(config.num_positions):
        rng = range(config.positions[i].lo, config.positions[i].hi + 1)
        # 构建 list[list[int]] 格式给通用函数
        list_of_lists = [[n] for n in pos_data[i]]
        freq = _compute_freq_with_decay(list_of_lists, dw, rng)
        miss = _compute_missing_with_decay(list_of_lists, dw, rng)
        repeat = _compute_repeat(list_of_lists, 10, rng)
        adj = _compute_adjacent(list_of_lists, rng)
        pos_stats.append({
            "freq": freq, "miss": miss, "repeat": repeat, "adj": adj,
            "rng": rng, "data": pos_data[i],
        })

    # 012路统计 (每位)
    m3_stats = []
    for i in range(config.num_positions):
        cnt = Counter()
        for v in pos_data[i]:
            cnt[v % 3] += 1
        total = sum(cnt.values())
        m3_stats.append({k: v / total for k, v in cnt.items()})

    # 奇偶/大小/质数统计 (每位)
    oe_stats = []
    bs_stats = []
    mid = config.positions[0].hi // 2
    for i in range(config.num_positions):
        cnt_o = Counter()
        cnt_b = Counter()
        for v in pos_data[i]:
            cnt_o[v % 2] += 1
            cnt_b[1 if v > mid else 0] += 1
        total = max(sum(cnt_o.values()), 1)
        oe_stats.append({k: v / total for k, v in cnt_o.items()})
        bs_stats.append({k: v / total for k, v in cnt_b.items()})

    weights = config.prediction_weights

    # ── 蒙特卡洛 ──
    candidates: list[Prediction] = []

    for _ in range(config.candidates_count):
        chosen = []
        scores = {}
        score_totals = defaultdict(float)

        for i in range(config.num_positions):
            st = pos_stats[i]
            rng = st["rng"]
            pool = list(rng)
            ws = []
            for n in pool:
                w = (st["freq"].get(n, 0.001) * 0.35 +
                     st["miss"].get(n, 0) * 0.30 +
                     st["repeat"].get(n, 0) * 0.20 +
                     st["adj"].get(n, 0) * 0.15)
                ws.append(max(w, 0.0001))
            tw = sum(ws)
            r = random.random() * tw
            cum = 0; pick = 0
            for j, w in enumerate(ws):
                cum += w
                if r <= cum: pick = j; break
            chosen.append(pool[pick])

        # 评分
        # 频次
        f_score = sum(pos_stats[i]["freq"].get(chosen[i], 0)
                       for i in range(config.num_positions)) / config.num_positions
        scores["频次分析"] = round(f_score, 3)
        score_totals["频次分析"] = f_score

        # 遗漏
        m_score = sum(pos_stats[i]["miss"].get(chosen[i], 0)
                       for i in range(config.num_positions)) / config.num_positions
        scores["遗漏回补"] = round(m_score, 3)
        score_totals["遗漏回补"] = m_score

        # 重号 (最近5期)
        recent_vals = [set(pos_data[i][:5]) for i in range(config.num_positions)]
        rp_score = sum(1 for i in range(config.num_positions)
                        if chosen[i] in recent_vals[i]) / config.num_positions
        scores["重号回补"] = round(rp_score, 3)
        score_totals["重号回补"] = rp_score

        # 012路平衡
        m3_score = sum(
            m3_stats[i].get(chosen[i] % 3, 0)
            for i in range(config.num_positions)
        ) / config.num_positions
        scores["012路匹配"] = round(m3_score, 3)
        score_totals["012路匹配"] = m3_score

        # 奇偶匹配
        oe_score = sum(
            oe_stats[i].get(chosen[i] % 2, 0)
            for i in range(config.num_positions)
        ) / config.num_positions
        scores["奇偶匹配"] = round(oe_score, 3)
        score_totals["奇偶匹配"] = oe_score

        # 大小匹配
        mid = config.positions[0].hi // 2
        bs_score = sum(
            bs_stats[i].get(1 if chosen[i] > mid else 0, 0)
            for i in range(config.num_positions)
        ) / config.num_positions
        scores["大小匹配"] = round(bs_score, 3)
        score_totals["大小匹配"] = bs_score

        # 总得分
        total_score = sum(score_totals[k] * weights.get(k, 0.15) for k in score_totals)

        candidates.append(Prediction(
            numbers=[[n] for n in chosen],
            total_score=round(total_score, 4),
            scores=scores,
        ))

    candidates.sort(key=lambda p: p.total_score, reverse=True)

    # 多样性去重
    seen = set()
    unique = []
    for p in candidates:
        key = tuple(p.numbers[i][0] for i in range(config.num_positions))
        if key not in seen:
            seen.add(key)
            unique.append(p)
        if len(unique) >= num_predictions:
            break

    return unique[:num_predictions]


# ═══════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════

def predict(config: GameConfig, data: list[dict],
            num_predictions: int = 5) -> list[Prediction]:
    """统一预测入口。"""
    if config.key == "daletou":
        return predict_daletou(data, config, num_predictions)
    else:
        return predict_digit(config, data, num_predictions)
