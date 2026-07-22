"""
幸运猩 — 彩票智能预测系统 UI v2.2
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import Counter

from config import ALL_GAMES
from data_fetcher import fetch_full, load
from db import count as db_count
from predictor import predict

st.set_page_config(
    page_title="幸运猩 · 彩票预测",
    page_icon="🦍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- Styles ----
st.markdown("""
<style>
    /* Fix content cutoff */
    [data-testid="stAppViewContainer"] > .main { padding: 1rem 2rem; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border-right: 1px solid #21262d;
    }
    [data-testid="stSidebar"] .block-container { padding: 1.2rem; }

    /* Buttons */
    .stButton > button {
        border-radius: 8px; font-weight: 500;
        transition: all 0.2s;
    }
    .stButton > button:hover { transform: translateY(-1px); }

    /* Metric override */
    [data-testid="stMetric"] label { font-size: 0.7rem; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 1.2rem; }

    /* DataFrame */
    .stDataFrame { font-size: 0.8rem; }

    hr { margin: 0.8rem 0; border-color: #21262d; }
</style>
""", unsafe_allow_html=True)

# ---- Sidebar ----
with st.sidebar:
    st.markdown("### 🦍 幸运猩")
    st.caption("用数据说话，不凭感觉下注")

    game_key = st.radio(
        "彩票类型",
        ["daletou", "qixingcai", "pailie5"],
        format_func=lambda k: f"{ALL_GAMES[k].icon}  {ALL_GAMES[k].name}",
        horizontal=False,
    )
    config = ALL_GAMES[game_key]

    st.divider()
    num_pred = st.slider("预测注数", 1, 20, 5)
    st.divider()

    btn_cols = st.columns(2)
    with btn_cols[0]:
        do_predict = st.button("🚀 生成预测", type="primary", use_container_width=True)
    with btn_cols[1]:
        do_update = st.button("🔄 更新数据", use_container_width=True)

    if do_update:
        fetch_full(config)
        st.rerun()

    st.divider()
    st.caption(
        f"{config.name}  ·  "
        f"{config.num_positions}位  ·  "
        f"历史 {db_count(config):,} 期"
    )

# ---- Load data ----
@st.cache_data(ttl=3600)
def load_data(key: str):
    return load(key)

data = load_data(game_key)
if not data:
    st.warning("暂无数据，点击侧边栏「更新数据」")
    st.stop()

top = data[-1]

# ---- Hero strip ----
st.markdown(
    f"<h1 style='font-size:1.4rem;font-weight:600;margin:0'>"
    f"{config.icon} {config.name} 预测中心</h1>",
    unsafe_allow_html=True,
)

mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
mc1.metric("总期数", f"{len(data):,}")
mc2.metric("最新期", top["issue"])

# Show latest winning numbers in hero
latest_nums_html = ""
if config.key == "daletou":
    reds = "&thinsp;".join(f"<b>{n:02d}</b>" for n in top["numbers"][:5])
    blues = "&thinsp;".join(f"<b>{n:02d}</b>" for n in top["numbers"][5:])
    latest_nums_html = (
        f'<span style="background:#2d1b1b;color:#ff6b6b;padding:4px 10px;'
        f'border-radius:6px;font-size:1.05rem;font-family:monospace">'
        f'{reds}</span>&ensp;'
        f'<span style="background:#1b2d2d;color:#4ecdc4;padding:4px 10px;'
        f'border-radius:6px;font-size:1.05rem;font-family:monospace">'
        f'{blues}</span>'
    )
else:
    nums = "&thinsp;".join(f"<b>{n:02d}</b>" for n in top["numbers"])
    latest_nums_html = (
        f'<span style="background:#1a1a2e;color:#ffd700;padding:4px 10px;'
        f'border-radius:6px;font-size:1.0rem;font-family:monospace">'
        f'{nums}</span>'
    )
mc3.markdown(
    f'<div style="margin-top:4px"><small style="color:#888">最新开奖  ← {top["date"]}</small><br>'
    f'{latest_nums_html}</div>',
    unsafe_allow_html=True,
)

mc4.metric("范围", f"{config.positions[0].lo}-{config.positions[0].hi}")
mc5.metric("算法", "7项" if config.key == "daletou" else "3项")

# predict button (also in sidebar, but having inline is more intuitive)
with mc6:
    st.write("&nbsp;")
    if st.button("🎯 生成预测", type="primary", use_container_width=True):
        do_predict = True

st.divider()

# ---- Run prediction ----
if do_predict:
    with st.spinner("🦍 分析历史数据，计算最优组合..."):
        st.session_state["predictions"] = predict(
            config, data, num_predictions=num_pred
        )

predictions = st.session_state.get("predictions")

# ================================================================
#  MAIN CONTENT — two-column layout
# ================================================================
col_left, col_right = st.columns([3.5, 2.5])

# ---- LEFT: Prediction Results ----
with col_left:
    if predictions:
        st.markdown("### 🎯 本期推荐")

        if config.key == "daletou":
            # Table-style display for DLT
            rows_html = []
            for i, p in enumerate(predictions):
                red_html = " ".join(
                    f'<span class="nr">{n:02d}</span>'
                    for n in p.numbers[0]
                ).replace(
                    'class="nr"',
                    'style="display:inline-block;width:28px;height:28px;'
                    'line-height:28px;text-align:center;background:#2d1b1b;'
                    'color:#ff6b6b;border-radius:50%;font-weight:600;'
                    'font-size:0.85rem;margin:1px"',
                )
                blue_html = " ".join(
                    f'<span class="nb">{n:02d}</span>'
                    for n in p.numbers[1]
                ).replace(
                    'class="nb"',
                    'style="display:inline-block;width:28px;height:28px;'
                    'line-height:28px;text-align:center;background:#1b2d2d;'
                    'color:#4ecdc4;border-radius:50%;font-weight:600;'
                    'font-size:0.85rem;margin:1px"',
                )
                bar_w = int(min(p.total_score / 0.8, 1.0) * 100)
                bar_c = "#4ecdc4" if p.total_score > 0.55 else "#ffd93d"
                rows_html.append(
                    f'<tr>'
                    f'<td style="color:#888;font-size:0.8rem;padding-right:12px">#{i+1}</td>'
                    f'<td style="padding:4px 0">{red_html}</td>'
                    f'<td style="color:#555;font-size:0.7rem;padding:0 6px">|</td>'
                    f'<td style="padding:4px 0">{blue_html}</td>'
                    f'<td style="padding-left:12px">'
                    f'<span style="font-weight:600;font-size:0.9rem">{p.total_score:.3f}</span>'
                    f'</td>'
                    f'<td style="padding-left:8px;width:80px">'
                    f'<div style="height:4px;background:#1a1a2e;border-radius:2px">'
                    f'<div style="width:{bar_w}%;height:4px;background:{bar_c};'
                    f'border-radius:2px"></div></div>'
                    f'</td>'
                    f'</tr>'
                )

            st.markdown(
                '<table style="width:100%;border-collapse:collapse">'
                + "".join(rows_html)
                + "</table>",
                unsafe_allow_html=True,
            )
        else:
            # Digit games: compact grid
            pcols = st.columns(min(len(predictions), 3))
            for i, p in enumerate(predictions):
                with pcols[i % 3]:
                    nums = [n for pos in p.numbers for n in pos]
                    num_html = " ".join(
                        f'<span style="display:inline-block;width:26px;height:26px;'
                        f'line-height:26px;text-align:center;background:#1a1a2e;'
                        f'color:#ffd700;border-radius:50%;font-weight:600;'
                        f'font-size:0.8rem;margin:1px">{n:02d}</span>'
                        for n in nums
                    )
                    bar_w = int(min(p.total_score / 0.8, 1.0) * 100)
                    st.markdown(
                        f'<div style="padding:8px;margin:4px 0;border:1px solid #21262d;'
                        f'border-radius:8px">'
                        f'<div style="margin-bottom:6px">#{i+1}&ensp;{num_html}</div>'
                        f'<div style="height:3px;background:#1a1a2e;border-radius:2px">'
                        f'<div style="width:{bar_w}%;height:3px;background:#4ecdc4;'
                        f'border-radius:2px"></div></div>'
                        f'<div style="text-align:right;font-size:0.7rem;color:#888;'
                        f'margin-top:2px">{p.total_score:.3f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Score detail — compact
        if predictions:
            with st.expander("🔍 最优注得分分解"):
                top_pred = predictions[0]
                rank_cols = st.columns(len(top_pred.scores))
                for j, (algo, sc) in enumerate(top_pred.scores.items()):
                    pct = f"{sc*100:.0f}%"
                    rank_cols[j].metric(algo, f"{sc:.3f}", delta=pct, delta_color="off")

    else:
        # Empty state
        st.markdown(
            '<div style="text-align:center;padding:3rem 2rem;color:#555">'
            '<div style="font-size:3rem;margin-bottom:1rem">🎯</div>'
            '<p>点击「生成预测」按钮，幸运猩将分析 '
            f'<b>{len(data):,}</b> 期历史数据</p>'
            '<p style="font-size:0.8rem;color:#444">'
            '综合频次 · 遗漏 · 和值 · 奇偶 · 区间 · 连号多项算法交叉计算</p>'
            '</div>',
            unsafe_allow_html=True,
        )

# ---- RIGHT: Quick Stats ----
with col_right:
    st.markdown("### 📊 数据快照")

    # Hot numbers card
    pos_counters = [Counter() for _ in range(config.num_positions)]
    for d in data:
        for i, n in enumerate(d["numbers"]):
            pos_counters[i][n] += 1

    # Tabs for different stat views
    st1, st2 = st.tabs(["热号", "冷号"])

    with st1:
        for i in range(min(config.num_positions, 5)):
            counter = pos_counters[i]
            top5 = counter.most_common(5)
            label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
            nums_html = " ".join(
                f'<span style="display:inline-block;width:22px;height:22px;'
                f'line-height:22px;text-align:center;font-size:0.7rem;'
                f'font-weight:600;color:#ff6b6b;background:#2d1b1b;'
                f'border-radius:4px;margin:1px">{n:02d}</span>'
                for n, _ in top5
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;margin:4px 0;font-size:0.8rem">'
                f'<span style="width:32px;color:#888">{label}</span>'
                f'<span>{nums_html}</span>'
                f'<span style="color:#555;font-size:0.7rem;margin-left:auto">'
                f'{top5[0][1]}次</span></div>',
                unsafe_allow_html=True,
            )

    with st2:
        total = len(data)
        last_seen_dicts = [{} for _ in range(config.num_positions)]
        for idx, d in enumerate(data):
            for i, n in enumerate(d["numbers"]):
                last_seen_dicts[i][n] = idx

        cold_all = []
        for i in range(config.num_positions):
            rng = range(config.positions[i].lo, config.positions[i].hi + 1)
            label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
            for n in rng:
                miss = max(total - 1 - last_seen_dicts[i].get(n, -1), 0)
                cold_all.append((miss, label, n))

        cold_all.sort(reverse=True)
        for miss, label, n in cold_all[:8]:
            intensity = min(miss / max(total * 0.2, 1), 1.0)
            r, g = 255, int(255 * (1 - intensity))
            st.markdown(
                f'<div style="display:flex;align-items:center;margin:4px 0;font-size:0.8rem">'
                f'<span style="width:32px;color:#888">{label}</span>'
                f'<span style="display:inline-block;width:22px;height:22px;line-height:22px;'
                f'text-align:center;font-weight:600;color:rgb({r},{g},{g});'
                f'background:rgba({r},{g},{g},0.15);border-radius:4px">'
                f'{n:02d}</span>'
                f'<span style="color:#888;font-size:0.7rem;margin-left:auto">{miss}期未出</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # Summary numbers
    if config.key == "daletou":
        recent_50_sums = [sum(d["numbers"][:5]) for d in data[-50:]]
        avg_sum = sum(recent_50_sums) / len(recent_50_sums)

        from collections import Counter as Ct
        oe = Ct()
        for d in data[-200:]:
            odd = sum(1 for n in d["numbers"][:5] if n % 2 == 1)
            oe[f"{odd}:{5-odd}"] += 1

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("和值均值", f"{avg_sum:.0f}")
        sm2.metric("常见奇偶比", oe.most_common(1)[0][0])
        bs = Ct()
        for d in data[-200:]:
            big = sum(1 for n in d["numbers"][:5] if n >= 18)
            bs[f"{big}:{5-big}"] += 1
        sm3.metric("常见大小比", bs.most_common(1)[0][0])

st.divider()

# ---- Bottom: Full Analysis Tab ----
tab_a, tab_b = st.tabs(["📈 趋势图表", "📋 历史数据"])

with tab_a:
    if config.key == "daletou":
        # Compact frequency + sum trend side by side
        ac1, ac2 = st.columns(2)

        with ac1:
            fig = go.Figure()
            for i in range(min(config.num_positions, 5)):
                c = pos_counters[i]
                rng = sorted(c.keys())
                fig.add_trace(go.Bar(
                    name=config.position_labels[i],
                    x=rng, y=[c[n] for n in rng],
                    marker_line_width=0,
                ))
            fig.update_layout(
                height=250, template="plotly_dark",
                legend=dict(orientation="h", font_size=9, y=1.02),
                margin=dict(l=10, r=10, t=5, b=5),
                xaxis=dict(title=None),
                yaxis=dict(title=None),
            )
            st.caption("前区频次分布")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        with ac2:
            sums = [sum(d["numbers"][:config.red_count]) for d in data[-100:]]
            issues = [d["issue"] for d in data[-100:]]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=issues, y=sums,
                mode="lines", line=dict(color="#ffd700", width=1.5),
                fill="tozeroy", fillcolor="rgba(255,215,0,0.05)",
            ))
            avg_s = sum(sums) / len(sums)
            fig2.add_hline(
                y=avg_s, line_dash="dot", line_color="#ff6b6b",
                annotation_text=f"均值 {avg_s:.0f}",
                annotation_font_size=10,
            )
            fig2.update_layout(
                height=250, template="plotly_dark",
                margin=dict(l=10, r=10, t=5, b=5),
                xaxis=dict(title=None, tickfont_size=8),
                yaxis=dict(title=None, tickfont_size=9),
            )
            st.caption("近100期前区和值趋势")
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    else:
        # Per-position mini charts
        st.caption("各位置近50期号码走势")
        pcols = st.columns(min(config.num_positions, 7))
        for i in range(min(config.num_positions, 7)):
            with pcols[i]:
                recent = [d["numbers"][i] for d in data[-50:]]
                fig_p = go.Figure()
                fig_p.add_trace(go.Scatter(
                    y=recent, mode="lines",
                    line=dict(width=1.2, color="#ffd700"),
                ))
                avg_v = sum(recent) / len(recent)
                fig_p.add_hline(y=avg_v, line_dash="dot", line_color="#ff6b6b")
                fig_p.update_layout(
                    height=160, template="plotly_dark",
                    title=config.position_labels[i], title_font_size=10,
                    margin=dict(l=2, r=2, t=20, b=2),
                    showlegend=False,
                    yaxis=dict(tickfont_size=8, dtick=2),
                )
                st.plotly_chart(fig_p, use_container_width=True, config={"displayModeBar": False})

with tab_b:
    rows = []
    for d in reversed(data[-200:]):
        row = {"期号": d["issue"], "日期": d["date"]}
        for i, n in enumerate(d["numbers"]):
            label = config.position_labels[i] if i < len(config.position_labels) else f"位{i+1}"
            row[label] = f"{n:02d}"
        rows.append(row)
    df = pd.DataFrame(rows)

    cl, cr = st.columns([4, 1])
    cl.caption(f"显示最近 {len(df)} 期，共 {len(data):,} 期")
    csv = df.to_csv(index=False).encode("utf-8")
    cr.download_button("📥 导出 CSV", csv, f"{config.key}.csv", "text/csv", use_container_width=True)
    st.dataframe(df, use_container_width=True, height=400, hide_index=True)
