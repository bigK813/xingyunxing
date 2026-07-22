"""
幸运猩 — 数据抓取模块 v2.0
支持大乐透、七星彩、排列5，全量历史抓取 + 增量更新。
"""

import time
from typing import Optional
import requests
from config import GameConfig, ALL_GAMES
from db import init_table, save_batch, load_all, get_latest_issue, count

API_URL = (
    "https://webapi.sporttery.cn/gateway/lottery/"
    "getHistoryPageListV1.qry"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Accept": "application/json",
}

_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def _parse_draw(item: dict, config: GameConfig) -> Optional[dict]:
    """解析单条开奖记录。"""
    result = item.get("lotteryDrawResult", "")
    if not result:
        return None
    parts = result.split()
    if len(parts) < config.num_positions:
        return None

    nums = [int(p) for p in parts[:config.num_positions]]
    return {
        "issue": item.get("lotteryDrawNum", ""),
        "date": item.get("lotteryDrawTime", ""),
        "numbers": nums,
    }


def _fetch_page(config: GameConfig, page_no: int,
                page_size: int = 50) -> tuple[list[dict], int]:
    """抓取单页数据。返回 (数据列表, 总页数)。"""
    session = _get_session()
    params = {
        "gameNo": config.api_game_no,
        "provinceId": "0",
        "pageSize": page_size,
        "isVerify": "1",
        "pageNo": page_no,
    }
    resp = session.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()

    if not body.get("success"):
        return [], 0

    value = body.get("value", {})
    items = value.get("list", [])
    total_pages = value.get("pages", 0)

    results = []
    for item in items:
        parsed = _parse_draw(item, config)
        if parsed:
            results.append(parsed)

    return results, total_pages


def fetch_full(config: GameConfig, delay: float = 0.6) -> int:
    """
    全量抓取历史数据并入库。
    自动跳过已有数据。返回新增条数。
    """
    init_table(config)

    print(f"🔄 [{config.name}] 开始全量抓取...")

    # 先获取第一页，确认总页数
    try:
        first_page, total_pages = _fetch_page(config, 1, page_size=50)
    except Exception as e:
        print(f"  ❌ [{config.name}] 请求失败: {e}")
        return 0

    if not first_page or total_pages == 0:
        print(f"  ⚠️ [{config.name}] 无数据")
        return 0

    print(f"  📄 总页数: {total_pages}，每页 50 条")

    all_data = list(first_page)
    existing_issue = get_latest_issue(config)

    # 如果数据库数据太少（<200条），强制全量抓取
    existing_count = count(config)
    if existing_issue and first_page and existing_count >= 200:
        latest_in_page = first_page[0]["issue"]
        if existing_issue >= latest_in_page:
            print(f"  ✅ [{config.name}] 已是最新 (最新期: {existing_issue})")
            return 0

    # 逐页抓取
    for page in range(2, total_pages + 1):
        try:
            batch, _ = _fetch_page(config, page, page_size=50)
            all_data.extend(batch)
            if page % 20 == 0:
                print(f"  ... [{config.name}] {page}/{total_pages} 页, "
                      f"累计 {len(all_data)} 条")
            time.sleep(delay)
        except Exception as e:
            print(f"  ⚠️ [{config.name}] 第{page}页失败: {e}")
            time.sleep(2)
            continue

    # 入库
    written = save_batch(config, all_data)
    print(f"  ✅ [{config.name}] 写入 {written} 条 "
          f"(共 {len(all_data)} 条原始数据)")
    return written


def fetch_latest(config: GameConfig) -> int:
    """增量更新：只抓最新一页，对比本地期号。"""
    init_table(config)
    existing = get_latest_issue(config)

    try:
        batch, _ = _fetch_page(config, 1, page_size=50)
    except Exception as e:
        print(f"  ❌ [{config.name}] 请求失败: {e}")
        return 0

    if not batch:
        return 0

    # 过滤出新数据
    new_data = [d for d in batch
                if not existing or d["issue"] > existing]

    if not new_data:
        print(f"  ✅ [{config.name}] 已是最新 ({existing})")
        return 0

    written = save_batch(config, new_data)
    print(f"  ✅ [{config.name}] 新增 {written} 期 "
          f"({new_data[-1]['issue']} ~ {new_data[0]['issue']})")
    return written


def load(config_or_key) -> list[dict]:
    """从数据库加载数据。config_or_key 可以是 GameConfig 或字符串键名。"""
    if isinstance(config_or_key, str):
        config = ALL_GAMES[config_or_key]
    else:
        config = config_or_key
    init_table(config)
    data = load_all(config)
    if not data:
        print(f"  ⚠️ [{config.name}] 本地无数据，尝试抓取...")
        fetch_full(config)
        data = load_all(config)
    return data


def fetch_all_games() -> dict[str, int]:
    """首次初始化：抓取全部 3 种彩票的完整历史。"""
    totals = {}
    for key in ["daletou", "qixingcai", "pailie5"]:
        cfg = ALL_GAMES[key]
        init_table(cfg)
        existing = count(cfg)
        if existing > 100:
            print(f"  [{cfg.name}] 已有 {existing} 期，跳过全量（使用增量）")
            n = fetch_latest(cfg)
        else:
            n = fetch_full(cfg)
        totals[key] = n
    return totals
