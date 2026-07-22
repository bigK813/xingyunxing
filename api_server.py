"""
幸运猩 — FastAPI 后端服务
为网页 PWA / 微信小程序提供 REST API。
支持定时自动刷新开奖数据。
"""

import os
import time
import random
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
from pydantic import BaseModel, Field

from config import ALL_GAMES, GameConfig
from db import init_table, load_all, count as db_count, get_latest_issue
from data_fetcher import fetch_latest
from predictor import predict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ══════════════════════════════════════════════════════
#  开奖时间表
# ══════════════════════════════════════════════════════

DRAW_SCHEDULE = {
    "daletou": {
        "name": "大乐透",
        "days": [0, 2, 5],           # 周一、三、六 (Mon=0)
        "time": "21:35",              # 开奖后 10 分钟
        "description": "每周一/三/六 21:25 开奖",
    },
    "qixingcai": {
        "name": "七星彩",
        "days": [1, 4, 6],           # 周二、五、日
        "time": "21:35",
        "description": "每周二/五/日 21:25 开奖",
    },
    "pailie5": {
        "name": "排列5",
        "days": [0, 1, 2, 3, 4, 5, 6],  # 每天
        "time": "21:35",
        "description": "每日 21:25 开奖",
    },
}

# ══════════════════════════════════════════════════════
#  应用生命周期
# ══════════════════════════════════════════════════════

# 内存缓存
cache: dict[str, dict] = {}
_last_refresh: dict[str, float] = {}
_last_refresh_result: dict[str, dict] = {}
scheduler: Optional[AsyncIOScheduler] = None


def _load_game_data(config: GameConfig) -> dict:
    """加载单个彩种的全部数据到缓存。"""
    init_table(config)
    raw = load_all(config)
    latest_issue = get_latest_issue(config)
    record_count = db_count(config)

    return {
        "config": config,
        "data": raw,
        "latest_issue": latest_issue,
        "record_count": record_count,
    }


def _ensure_fresh(config: GameConfig) -> None:
    """确保数据最新：距上次拉取超过1小时则自动拉取。"""
    key = config.key
    now = time.time()
    if now - _last_refresh.get(key, 0) > 3600:
        try:
            before = db_count(config)
            n = fetch_latest(config)
            cache[key] = _load_game_data(config)
            _last_refresh[key] = time.time()
            if n > 0:
                print(f"  [auto] {config.name}: +{n} 期 (共 {db_count(config)} 期)")
        except Exception as e:
            print(f"  [auto] {config.name} 拉取失败: {e}")
            _last_refresh[key] = time.time()

def refresh_cache(game_key: Optional[str] = None):
    """刷新缓存（可指定单个彩种或全部）。"""
    keys = [game_key] if game_key else list(ALL_GAMES.keys())
    for key in keys:
        cfg = ALL_GAMES[key]
        cache[key] = _load_game_data(cfg)
        _last_refresh[key] = time.time()


def scheduled_fetch():
    """
    定时任务：自动从体彩官网拉取最新开奖数据。
    每天开奖时间后执行。
    """
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] 定时刷新数据...")
    results = {}
    for key, cfg in ALL_GAMES.items():
        try:
            before = db_count(cfg)
            n = fetch_latest(cfg)
            after = db_count(cfg)
            # 重载缓存
            cache[key] = _load_game_data(cfg)
            _last_refresh[key] = time.time()
            added = after - before
            results[key] = {
                "name": cfg.name,
                "before": before,
                "after": after,
                "added": added,
                "latest_issue": get_latest_issue(cfg),
                "status": "ok" if added >= 0 else "error",
            }
            if added > 0:
                print(f"  ✅ {cfg.name}: +{added} 期 → 共 {after} 期")
        except Exception as e:
            results[key] = {"name": cfg.name, "status": "error", "error": str(e)}
            print(f"  ❌ {cfg.name}: {e}")

    _last_refresh_result["all"] = {
        "time": datetime.now().isoformat(),
        "results": results,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时加载数据 + 启动定时刷新。"""
    global scheduler
    print("🚀 幸运猩 API 启动中...")
    refresh_cache()
    for key, data in cache.items():
        print(f"  ✅ {data['config'].name} — {data['record_count']} 期")

    # 启动定时调度
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    # 每天 21:35 和 22:00 刷新（开奖后）
    scheduler.add_job(scheduled_fetch, CronTrigger(hour=21, minute=35), id="draw_refresh_1")
    scheduler.add_job(scheduled_fetch, CronTrigger(hour=22, minute=0), id="draw_refresh_2")
    # 每天 8:00 刷新（补充前日遗漏）
    scheduler.add_job(scheduled_fetch, CronTrigger(hour=8, minute=0), id="morning_refresh")
    scheduler.start()
    print("⏰ 定时刷新已启动 (每天 08:00 / 21:35 / 22:00)")

    print("📡 API 就绪: http://0.0.0.0:8000")
    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    print("👋 幸运猩 API 关闭")


app = FastAPI(
    title="幸运猩 · 彩票智能预测 API",
    description="支持大乐透、七星彩、排列5的历史数据查询与智能预测",
    version="1.0.0",
    lifespan=lifespan,
)

# 静态文件 — PWA 前端
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回 PWA 前端页面。"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>幸运猩 API 已就绪</h1><p>前端文件未找到，请访问 <a href='/docs'>/docs</a> 查看 API 文档。</p>"


# CORS — 允许 PWA / 小程序 / 开发环境访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════
#  Pydantic 模型
# ══════════════════════════════════════════════════════

class GameInfo(BaseModel):
    key: str
    name: str
    icon: str
    record_count: int
    latest_issue: Optional[str]
    num_positions: int
    position_labels: list[str]
    position_ranges: list[dict]


class DrawRecord(BaseModel):
    issue: str
    date: str
    numbers: list[int]


class FrequencyItem(BaseModel):
    number: int
    count: int
    ratio: float


class PosFrequency(BaseModel):
    position: str
    data: list[FrequencyItem]


class NumberBall(BaseModel):
    number: int
    label: str


class PredictionResult(BaseModel):
    rank: int = Field(ge=1)
    numbers: list[list[int]]
    formatted: str
    total_score: float
    scores: dict[str, float]


class StatOverview(BaseModel):
    record_count: int
    date_from: Optional[str]
    date_to: Optional[str]
    latest_issue: Optional[str]
    latest_numbers: Optional[list[int]]
    latest_date: Optional[str]
    frequency: list[PosFrequency]
    missing: list[PosFrequency]
    hot_numbers: list[NumberBall]
    cold_numbers: list[NumberBall]


# ══════════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════════

def _ensure_cache(game_key: str) -> dict:
    """确保缓存中有最新数据，没有则加载。"""
    cfg = ALL_GAMES.get(game_key)
    if not cfg:
        raise HTTPException(404, f"未知彩种: {game_key}")
    if game_key not in cache:
        cache[game_key] = _load_game_data(cfg)
    # 自动检测是否有新数据
    _ensure_fresh(cfg)
    return cache[game_key]


def _format_numbers(config: GameConfig, numbers: list[int]) -> str:
    """格式化号码为显示字符串。"""
    if config.key == "daletou":
        reds = ' '.join(f'{n:02d}' for n in numbers[:5])
        blues = ' '.join(f'{n:02d}' for n in numbers[5:])
        return f"{reds}  |  {blues}"
    else:
        return ' '.join(f'{n:02d}' for n in numbers)


def _build_frequency(config: GameConfig, data: list[dict]) -> list[PosFrequency]:
    """构建每位的频次统计。"""
    pos_counters = [Counter() for _ in range(config.num_positions)]
    for d in data:
        for i, n in enumerate(d["numbers"]):
            pos_counters[i][n] += 1

    total = max(len(data), 1)
    result = []
    for i in range(config.num_positions):
        label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
        rng = range(config.positions[i].lo, config.positions[i].hi + 1)
        items = []
        for n in rng:
            c = pos_counters[i].get(n, 0)
            items.append(FrequencyItem(number=n, count=c, ratio=round(c / total, 4)))
        items.sort(key=lambda x: x.count, reverse=True)
        result.append(PosFrequency(position=label, data=items))
    return result


def _build_missing(config: GameConfig, data: list[dict]) -> list[PosFrequency]:
    """构建每位的遗漏统计。"""
    total = len(data)
    last_seen = [{} for _ in range(config.num_positions)]
    for idx, d in enumerate(data):
        for i, n in enumerate(d["numbers"]):
            last_seen[i][n] = idx

    result = []
    for i in range(config.num_positions):
        label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
        rng = range(config.positions[i].lo, config.positions[i].hi + 1)
        items = []
        for n in rng:
            miss = total - 1 - last_seen[i].get(n, -1)
            miss = max(miss, 0)
            items.append(FrequencyItem(number=n, count=miss, ratio=round(miss / total, 4)))
        items.sort(key=lambda x: x.count, reverse=True)
        result.append(PosFrequency(position=label, data=items))
    return result


# ══════════════════════════════════════════════════════
#  API 路由
# ══════════════════════════════════════════════════════

@app.get("/api/health")
async def health_check():
    """健康检查。"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "games": list(cache.keys()),
        "scheduler_running": scheduler is not None and scheduler.running if scheduler else False,
    }


@app.get("/api/status")
async def system_status():
    """
    系统状态：下次开奖时间、上次刷新结果、各彩种数据情况。
    前端用此接口做自动刷新倒计时。
    """
    now = datetime.now()
    today = now.weekday()  # 0=Mon

    # 计算下次开奖时间
    next_draws = []
    for key, info in DRAW_SCHEDULE.items():
        hour, minute = map(int, info["time"].split(":"))
        draw_today = datetime(now.year, now.month, now.day, hour, minute)

        # 找最近一个开奖日
        days = info["days"]
        found = None
        for offset in range(8):  # 查未来 7 天
            check = now + timedelta(days=offset)
            if check.weekday() in days:
                candidate = datetime(check.year, check.month, check.day, hour, minute)
                if candidate > now or (offset == 0 and candidate > now):
                    found = candidate
                    break
                elif offset > 0:
                    found = candidate
                    break
        if not found:
            found = now + timedelta(days=1)

        data = cache.get(key, {})
        next_draws.append({
            "key": key,
            "name": info["name"],
            "schedule": info["description"],
            "next_draw": found.isoformat(),
            "next_draw_ts": found.timestamp(),
            "countdown_seconds": max(0, (found - now).total_seconds()),
            "latest_issue": data.get("latest_issue"),
            "record_count": data.get("record_count", 0),
        })
    next_draws.sort(key=lambda x: x["next_draw_ts"])

    # 上次刷新结果
    last = _last_refresh_result.get("all", {})

    return {
        "server_time": now.isoformat(),
        "server_ts": now.timestamp(),
        "next_draws": next_draws,
        "last_refresh": last,
        "games_cached": list(cache.keys()),
    }


# ---- 彩种信息 ----

@app.get("/api/games", response_model=list[GameInfo])
async def list_games():
    """获取全部彩种基本信息。"""
    result = []
    for key, cfg in ALL_GAMES.items():
        data = _ensure_cache(key)
        ranges = [{"lo": p.lo, "hi": p.hi} for p in cfg.positions]
        result.append(GameInfo(
            key=cfg.key,
            name=cfg.name,
            icon=cfg.icon,
            record_count=data["record_count"],
            latest_issue=data["latest_issue"],
            num_positions=cfg.num_positions,
            position_labels=cfg.position_labels,
            position_ranges=ranges,
        ))
    return result


@app.get("/api/games/{game_key}")
async def get_game_info(game_key: str):
    """获取单个彩种详情。"""
    cfg = ALL_GAMES.get(game_key)
    if not cfg:
        raise HTTPException(404, f"未知彩种: {game_key}")
    data = _ensure_cache(game_key)
    ranges = [{"lo": p.lo, "hi": p.hi} for p in cfg.positions]
    return GameInfo(
        key=cfg.key,
        name=cfg.name,
        icon=cfg.icon,
        record_count=data["record_count"],
        latest_issue=data["latest_issue"],
        num_positions=cfg.num_positions,
        position_labels=cfg.position_labels,
        position_ranges=ranges,
    )


# ---- 历史数据 ----

@app.get("/api/{game_key}/latest")
async def get_latest(game_key: str):
    """获取最新一期开奖号码。"""
    data = _ensure_cache(game_key)
    records = data["data"]
    if not records:
        raise HTTPException(404, "无数据")

    latest = records[-1]
    cfg = data["config"]
    return {
        "game": cfg.name,
        "issue": latest["issue"],
        "date": latest["date"],
        "numbers": latest["numbers"],
        "formatted": _format_numbers(cfg, latest["numbers"]),
    }


@app.get("/api/{game_key}/history")
async def get_history(
    game_key: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页条数"),
):
    """分页获取历史开奖数据（按期号降序）。"""
    data = _ensure_cache(game_key)
    cfg = data["config"]
    records = data["data"]

    # 按时间倒序
    reversed_data = list(reversed(records))
    total = len(reversed_data)
    total_pages = max(1, (total + page_size - 1) // page_size)

    if page > total_pages:
        raise HTTPException(404, f"页码超出范围: {page}/{total_pages}")

    start = (page - 1) * page_size
    end = min(start + page_size, total)
    items = reversed_data[start:end]

    return {
        "game": cfg.name,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_count": total,
        "items": [
            DrawRecord(
                issue=item["issue"],
                date=item["date"],
                numbers=item["numbers"],
            ) for item in items
        ],
    }


# ---- 统计分析 ----

@app.get("/api/{game_key}/stats", response_model=StatOverview)
async def get_stats(game_key: str):
    """获取彩种完整统计分析。"""
    data = _ensure_cache(game_key)
    cfg = data["config"]
    records = data["data"]

    if not records:
        raise HTTPException(404, "无数据")

    # 频次与遗漏
    freq = _build_frequency(cfg, records)
    miss = _build_missing(cfg, records)

    # 热冷号：取全部位置的频次汇总
    pos_counters = [Counter() for _ in range(cfg.num_positions)]
    for d in records:
        for i, n in enumerate(d["numbers"]):
            pos_counters[i][n] += 1

    all_num_counts: list[tuple[int, int, str]] = []
    for i in range(cfg.num_positions):
        label = cfg.position_labels[i] if i < len(cfg.position_labels) else f"位{i+1}"
        rng = range(cfg.positions[i].lo, cfg.positions[i].hi + 1)
        for n in rng:
            c = pos_counters[i].get(n, 0)
            all_num_counts.append((n, c, label))

    all_num_counts.sort(key=lambda x: x[1], reverse=True)
    top_n = min(10, len(all_num_counts))
    hot = [NumberBall(number=n, label=f"{l}({c}次)")
           for n, c, l in all_num_counts[:top_n]]
    cold = [NumberBall(number=n, label=f"{l}({c}次)")
            for n, c, l in all_num_counts[-top_n:]]
    cold.reverse()

    latest = records[-1]

    return StatOverview(
        record_count=data["record_count"],
        date_from=records[0]["date"] if records else None,
        date_to=records[-1]["date"] if records else None,
        latest_issue=latest["issue"],
        latest_numbers=latest["numbers"],
        latest_date=latest["date"],
        frequency=freq,
        missing=miss,
        hot_numbers=hot,
        cold_numbers=cold,
    )


@app.get("/api/{game_key}/trend")
async def get_trend(game_key: str, limit: int = Query(100, ge=10, le=500)):
    """获取近 N 期的号码趋势数据（供图表使用）。"""
    data = _ensure_cache(game_key)
    cfg = data["config"]
    records = data["data"]
    recent = records[-limit:] if len(records) > limit else records

    # 每期的号码与和值
    items = []
    for r in recent:
        s = sum(r["numbers"])
        items.append({
            "issue": r["issue"],
            "date": r["date"],
            "numbers": r["numbers"],
            "sum": s,
        })

    # 每位号码的移动平均出现频次
    moving_avg = []
    window = min(30, len(records))
    for i in range(cfg.num_positions):
        label = cfg.position_labels[i] if i < len(cfg.position_labels) else f"位{i+1}"
        rng = range(cfg.positions[i].lo, cfg.positions[i].hi + 1)
        window_data = records[-window:]
        counter = Counter()
        for d in window_data:
            counter[d["numbers"][i]] += 1
        freq_list = [{"number": n, "count": counter.get(n, 0),
                       "ratio": round(counter.get(n, 0) / window, 3)}
                      for n in rng]
        moving_avg.append({"position": label, "frequency": freq_list})

    return {
        "game": cfg.name,
        "limit": limit,
        "items": items,
        "moving_average_30": moving_avg,
    }


# ---- 预测 ----

class PredictRequest(BaseModel):
    game_key: str = Field(..., description="彩种键名: daletou / qixingcai / pailie5")
    count: int = Field(5, ge=1, le=20, description="预测注数")
    seed: Optional[int] = Field(None, description="随机种子（可选，用于复现结果）")


@app.post("/api/predict", response_model=list[PredictionResult])
async def predict_numbers(req: PredictRequest):
    """生成彩票预测号码。"""
    cfg = ALL_GAMES.get(req.game_key)
    if not cfg:
        raise HTTPException(404, f"未知彩种: {req.game_key}")

    data = _ensure_cache(req.game_key)
    records = data["data"]
    if len(records) < 50:
        raise HTTPException(400, f"数据不足（仅 {len(records)} 期，至少需要 50 期）")

    if req.seed is not None:
        random.seed(req.seed)

    results = predict(cfg, records, num_predictions=req.count)

    return [
        PredictionResult(
            rank=i + 1,
            numbers=p.numbers,
            formatted=p.format_str(cfg),
            total_score=p.total_score,
            scores=p.scores,
        )
        for i, p in enumerate(results)
    ]


@app.get("/api/{game_key}/predict")
async def predict_get(
    game_key: str,
    count: int = Query(5, ge=1, le=20),
    seed: Optional[int] = Query(None),
):
    """GET 方式生成预测（便于分享链接）。"""
    cfg = ALL_GAMES.get(game_key)
    if not cfg:
        raise HTTPException(404, f"未知彩种: {game_key}")

    data = _ensure_cache(game_key)
    records = data["data"]
    if len(records) < 50:
        raise HTTPException(400, f"数据不足")

    if seed is not None:
        random.seed(seed)

    results = predict(cfg, records, num_predictions=count)

    return {
        "game": cfg.name,
        "generated_at": datetime.now().isoformat(),
        "data_based_on": f"{len(records)} 期历史数据 ({records[0]['date']} ~ {records[-1]['date']})",
        "predictions": [
            PredictionResult(
                rank=i + 1,
                numbers=p.numbers,
                formatted=p.format_str(cfg),
                total_score=p.total_score,
                scores=p.scores,
            )
            for i, p in enumerate(results)
        ],
    }


# ---- 数据刷新 ----

@app.post("/api/data/refresh")
async def refresh_data(game_key: Optional[str] = None):
    """触发数据刷新（从体彩官网拉取最新数据）。"""
    keys = [game_key] if game_key else list(ALL_GAMES.keys())
    results = {}

    for key in keys:
        cfg = ALL_GAMES.get(key)
        if not cfg:
            continue
        try:
            before = db_count(cfg)
            n = fetch_latest(cfg)
            after = db_count(cfg)
            # 重载缓存
            cache[key] = _load_game_data(cfg)
            _last_refresh[key] = time.time()
            results[key] = {
                "name": cfg.name,
                "before": before,
                "after": after,
                "added": n,
                "status": "ok",
            }
        except Exception as e:
            results[key] = {"name": cfg.name, "status": "error", "error": str(e)}

    return {
        "refreshed_at": datetime.now().isoformat(),
        "results": results,
    }


# ══════════════════════════════════════════════════════
#  启动入口
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("ENV", "dev") == "dev"
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info",
    )
