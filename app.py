"""
事件合约预测工作台 (Event Contract Prediction Workbench)
支持：实时市场监控、数据分析、模拟交易、策略回测
数据源：Polymarket 公开 API
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import time
import json

# ==================== 配置 ====================
st.set_page_config(
    page_title="事件合约预测工作台",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# ==================== 工具函数 ====================
@st.cache_data(ttl=60)
def fetch_events(limit: int = 50, active: bool = True, closed: bool = False) -> List[Dict]:
    """获取活跃事件列表"""
    try:
        params = {
            "limit": limit,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": "volume24hr",
            "ascending": "false",
        }
        r = requests.get(f"{GAMMA_API}/events", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"获取事件失败: {e}")
        return []


@st.cache_data(ttl=30)
def fetch_markets(limit: int = 100) -> List[Dict]:
    """获取市场列表"""
    try:
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"获取市场失败: {e}")
        return []


@st.cache_data(ttl=20)
def fetch_price_history(token_id: str, interval: str = "1h", fidelity: int = 60) -> List[Dict]:
    """获取价格历史 (CLOB)"""
    try:
        params = {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        }
        r = requests.get(f"{CLOB_API}/prices-history", params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("history", [])
        return []
    except Exception:
        return []


@st.cache_data(ttl=15)
def fetch_orderbook(token_id: str) -> Dict:
    """获取订单簿"""
    try:
        r = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=10)
        if r.status_code == 200:
            return r.json()
        return {}
    except Exception:
        return {}


@st.cache_data(ttl=20)
def fetch_midpoint(token_id: str) -> Optional[float]:
    """获取中间价"""
    try:
        r = requests.get(f"{CLOB_API}/midpoint", params={"token_id": token_id}, timeout=10)
        if r.status_code == 200:
            return float(r.json().get("mid", 0))
        return None
    except Exception:
        return None


def parse_outcome_prices(market: Dict) -> Dict[str, float]:
    """解析 outcomePrices"""
    try:
        outcomes = json.loads(market.get("outcomes", "[]")) if isinstance(market.get("outcomes"), str) else market.get("outcomes", [])
        prices = json.loads(market.get("outcomePrices", "[]")) if isinstance(market.get("outcomePrices"), str) else market.get("outcomePrices", [])
        return {str(o): float(p) for o, p in zip(outcomes, prices)}
    except Exception:
        return {}


def get_token_ids(market: Dict) -> List[str]:
    """获取 clobTokenIds"""
    try:
        tids = market.get("clobTokenIds", "[]")
        if isinstance(tids, str):
            return json.loads(tids)
        return tids or []
    except Exception:
        return []# ==================== 模拟交易引擎 ====================
class PaperPortfolio:
    """简单纸上交易组合"""

    def __init__(self, initial_cash: float = 10000.0):
        self.cash = initial_cash
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.initial_cash = initial_cash

    def buy(self, token_id: str, price: float, qty: float, market_title: str = "", outcome: str = "Yes"):
        cost = price * qty
        if cost > self.cash:
            return False, "现金不足"
        self.cash -= cost
        if token_id in self.positions:
            pos = self.positions[token_id]
            total_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["avg_price"] * pos["qty"] + price * qty) / total_qty
            pos["qty"] = total_qty
        else:
            self.positions[token_id] = {
                "qty": qty,
                "avg_price": price,
                "side": "long",
                "market_title": market_title,
                "outcome": outcome,
            }
        self.trades.append({
            "time": datetime.now().isoformat(),
            "action": "BUY",
            "token_id": token_id[:12] + "...",
            "price": price,
            "qty": qty,
            "cost": cost,
            "market": market_title[:40],
        })
        return True, "买入成功"

    def sell(self, token_id: str, price: float, qty: float):
        if token_id not in self.positions or self.positions[token_id]["qty"] < qty:
            return False, "持仓不足"
        proceeds = price * qty
        self.cash += proceeds
        self.positions[token_id]["qty"] -= qty
        if self.positions[token_id]["qty"] <= 1e-8:
            del self.positions[token_id]
        self.trades.append({
            "time": datetime.now().isoformat(),
            "action": "SELL",
            "token_id": token_id[:12] + "...",
            "price": price,
            "qty": qty,
            "proceeds": proceeds,
        })
        return True, "卖出成功"

    def equity(self, current_prices: Dict[str, float]) -> float:
        total = self.cash
        for tid, pos in self.positions.items():
            price = current_prices.get(tid, pos["avg_price"])
            total += pos["qty"] * price
        return total

    def to_dict(self):
        return {
            "cash": self.cash,
            "positions": self.positions,
            "trades": self.trades,
            "initial_cash": self.initial_cash,
        }

    @classmethod
    def from_dict(cls, d):
        p = cls(d.get("initial_cash", 10000))
        p.cash = d.get("cash", 10000)
        p.positions = d.get("positions", {})
        p.trades = d.get("trades", [])
        return p


# ==================== Session State ====================
if "portfolio" not in st.session_state:
    st.session_state.portfolio = PaperPortfolio(10000.0)
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []
if "backtest_results" not in st.session_state:
    st.session_state.backtest_results = None


# ==================== 侧边栏 ====================
with st.sidebar:
    st.title("📈 事件合约工作台")
    st.caption("Polymarket 数据驱动 | 模拟交易 + 分析")

    page = st.radio(
        "功能模块",
        ["🏠 市场总览", "📊 市场详情 & 监控", "💹 模拟交易", "🧪 策略回测", "📚 数据分析", "ℹ️ 关于"],
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("刷新设置")
    auto_refresh
  st.divider()
    st.subheader("刷新设置")
    auto_refresh = st.checkbox("自动刷新 (60s)", value=False)
    if st.button("立即刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    equity = st.session_state.portfolio.equity({})
    st.metric("模拟账户权益", f"${equity:,.2f}")


# ==================== 页面：市场总览 ====================
if page == "🏠 市场总览":
    st.header("🏠 事件合约市场总览")
    st.markdown("实时展示 Polymarket 高成交量事件合约，概率 = 市场价格")

    col1, col2, col3 = st.columns(3)
    with col1:
        limit = st.slider("显示数量", 10, 100, 30)
    with col2:
        search = st.text_input("搜索关键词", placeholder="bitcoin / election / fed...")
    with col3:
        sort_by = st.selectbox("排序", ["成交量 (24h)", "流动性", "结束时间"])

    with st.spinner("正在拉取最新市场数据..."):
        markets = fetch_markets(limit=limit * 2)

    if not markets:
        st.warning("暂无数据，请稍后重试或检查网络")
    else:
        rows = []
        for m in markets:
            prices = parse_outcome_prices(m)
            yes_price = prices.get("Yes") or prices.get("yes") or (list(prices.values())[0] if prices else None)
            volume = float(m.get("volume24hr") or m.get("volume") or 0)
            liquidity = float(m.get("liquidity") or m.get("liquidityNum") or 0)
            end_date = m.get("endDate") or m.get("end_date_iso") or ""
            title = m.get("question") or m.get("title") or "Unknown"
            if search and search.lower() not in title.lower():
                continue
            rows.append({
                "问题": title[:80],
                "Yes 概率": yes_price,
                "24h 成交量 ($)": volume,
                "流动性 ($)": liquidity,
                "结束时间": end_date[:10] if end_date else "-",
                "市场ID": m.get("id") or m.get("conditionId"),
                "slug": m.get("slug"),
                "raw": m,
            })

        df = pd.DataFrame(rows)
        if sort_by == "成交量 (24h)":
            df = df.sort_values("24h 成交量 ($)", ascending=False)
        elif sort_by == "流动性":
            df = df.sort_values("流动性 ($)", ascending=False)
        else:
            df = df.sort_values("结束时间")

        df = df.head(limit)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("市场数量", len(df))
        c2.metric("总 24h 成交量", f"\( {df['24h 成交量 ( \))'].sum():,.0f}")
        avg_prob = df["Yes 概率"].dropna().mean()
        c3.metric("平均 Yes 概率", f"{avg_prob:.1%}" if pd.notna(avg_prob) else "-")
        c4.metric("最高流动性", f"\( {df['流动性 ( \))'].max():,.0f}")

        display_df = df[["问题", "Yes 概率", "24h 成交量 (\( )", "流动性 ( \))", "结束时间"]].copy()
        display_df["Yes 概率"] = display_df["Yes 概率"].apply(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
        display_df["24h 成交量 (\( )"] = display_df["24h 成交量 ( \))"].apply(lambda x: f"{x:,.0f}")
        display_df["流动性 (\( )"] = display_df["流动性 ( \))"].apply(lambda x: f"{x:,.0f}")

        st.dataframe(display_df, use_container_width=True, height=500)

        st.subheader("Yes 概率分布")
        fig = px.histogram(
            df.dropna(subset=["Yes 概率"]),
            x="Yes 概率",
            nbins=20,
            title="市场隐含概率分布",
            labels={"Yes 概率": "Yes 价格 (概率)"},
        )
        fig.update_layout(xaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("24h 成交量 Top 10")
        top = df.nlargest(10, "24h 成交量 ($)")
        fig2 = px.bar(
            top,
            x="24h 成交量 ($)",
            y="问题",
            orientation="h",
            title="成交量排行",
        )
        fig2.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
        st.plotly_chart(fig2, use_container_width=True)
      # ==================== 页面：市场详情 & 监控 ====================
elif page == "📊 市场详情 & 监控":
    st.header("📊 市场详情 & 实时监控")

    markets = fetch_markets(limit=80)
    if not markets:
        st.warning("无法加载市场")
    else:
        options = {}
        for m in markets:
            title = (m.get("question") or m.get("title") or "Unknown")[:70]
            options[title] = m

        selected_title = st.selectbox("选择市场", list(options.keys()))
        market = options[selected_title]

        prices = parse_outcome_prices(market)
        token_ids = get_token_ids(market)

        col1, col2, col3, col4 = st.columns(4)
        yes_p = prices.get("Yes") or prices.get("yes")
        no_p = prices.get("No") or prices.get("no")
        col1.metric("Yes 价格", f"{yes_p:.3f}" if yes_p else "-")
        col2.metric("No 价格", f"{no_p:.3f}" if no_p else "-")
        vol = float(market.get("volume24hr") or market.get("volume") or 0)
        col3.metric("24h 成交量", f"${vol:,.0f}")
        liq = float(market.get("liquidity") or 0)
        col4.metric("流动性", f"${liq:,.0f}")

        st.markdown(f"**问题**: {market.get('question') or market.get('title')}")
        st.markdown(f"**结束时间**: {str(market.get('endDate') or market.get('end_date_iso') or '-')[:19]}")
        st.markdown(f"**描述**: {(market.get('description') or '')[:300]}...")

        if st.button("⭐ 加入监控列表"):
            if market not in st.session_state.watchlist:
                st.session_state.watchlist.append(market)
                st.success("已加入监控列表")
            else:
                st.info("已在监控列表中")

        st.subheader("订单簿 (Order Book)")
        if token_ids:
            tid = token_ids[0]
            book = fetch_orderbook(tid)
            if book:
                bids = book.get("bids", [])[:10]
                asks = book.get("asks", [])[:10]
                bcol, acol = st.columns(2)
                with bcol:
                    st.write("**买盘 (Bids)**")
                    if bids:
                        bdf = pd.DataFrame(bids)
                        st.dataframe(bdf, use_container_width=True)
                    else:
                        st.write("无数据")
                with acol:
                    st.write("**卖盘 (Asks)**")
                    if asks:
                        adf = pd.DataFrame(asks)
                        st.dataframe(adf, use_container_width=True)
                    else:
                        st.write("无数据")
            else:
                st.info("订单簿暂不可用")

            st.subheader("价格历史")
            interval = st.selectbox("时间粒度", ["1h", "6h", "1d", "1w"], index=0)
            history = fetch_price_history(tid, interval=interval)
            if history:
                hdf = pd.DataFrame(history)
                if "t" in hdf.columns and "p" in hdf.columns:
                    hdf["time"] = pd.to_datetime(hdf["t"], unit="s")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=hdf["time"], y=hdf["p"], mode="lines", name="Price"))
                    fig.update_layout(title="历史价格走势", yaxis_title="价格", xaxis_title="时间", height=400)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.write(hdf.head())
            else:
                st.info("暂无历史价格数据（部分市场可能不支持）")
        else:
            st.warning("该市场无 token_id，无法获取深度数据")

        st.divider()
        st.subheader("⭐ 我的监控列表")
        if not st.session_state.watchlist:
            st.info("监控列表为空，请从上方加入市场")
        else:
            for i, w in enumerate(st.session_state.watchlist):
                wp = parse_outcome_prices(w)
                yp = wp.get("Yes") or wp.get("yes")
                st.write(f"{i+1}. **{(w.get('question') or '')[:60]}** | Yes: {yp:.3f if yp else '-'}")
            if st.button("清空监控列表"):
                st.session_state.watchlist = []
                st.rerun()# ==================== 页面：模拟交易 ====================
elif page == "💹 模拟交易":
    st.header("💹 模拟交易 (Paper Trading)")
    st.markdown("使用虚拟资金在真实市场价格上进行模拟买卖，验证策略思路")

    portfolio = st.session_state.portfolio

    c1, c2, c3 = st.columns(3)
    c1.metric("现金余额", f"${portfolio.cash:,.2f}")
    c2.metric("持仓数量", len(portfolio.positions))
    c3.metric("初始资金", f"${portfolio.initial_cash:,.2f}")

    st.subheader("下单")
    markets = fetch_markets(limit=50)
    if markets:
        m_options = {(m.get("question") or m.get("title") or "")[:60]: m for m in markets}
        sel = st.selectbox("选择市场", list(m_options.keys()))
        market = m_options[sel]
        prices = parse_outcome_prices(market)
        token_ids = get_token_ids(market)

        yes_price = prices.get("Yes") or prices.get("yes") or 0.5
        no_price = prices.get("No") or prices.get("no") or (1 - yes_price)

        col_a, col_b = st.columns(2)
        with col_a:
            side = st.radio("方向", ["买入 Yes", "买入 No", "卖出持仓"])
        with col_b:
            qty = st.number_input("数量 (份)", min_value=1.0, value=10.0, step=1.0)
            price = st.number_input(
                "价格",
                min_value=0.01,
                max_value=0.99,
                value=float(yes_price) if "Yes" in side else float(no_price),
                step=0.01,
                format="%.3f",
            )

        if st.button("执行模拟交易", type="primary"):
            title = market.get("question") or market.get("title") or ""
            if side == "买入 Yes" and token_ids:
                ok, msg = portfolio.buy(token_ids[0], price, qty, title, "Yes")
                st.success(msg) if ok else st.error(msg)
            elif side == "买入 No" and len(token_ids) > 1:
                ok, msg = portfolio.buy(token_ids[1], price, qty, title, "No")
                st.success(msg) if ok else st.error(msg)
            elif side == "卖出持仓":
                if portfolio.positions:
                    tid = list(portfolio.positions.keys())[0]
                    ok, msg = portfolio.sell(tid, price, min(qty, portfolio.positions[tid]["qty"]))
                    st.success(msg) if ok else st.error(msg)
                else:
                    st.error("无持仓可卖")
            st.session_state.portfolio = portfolio
            st.rerun()

    st.subheader("当前持仓")
    if portfolio.positions:
        pos_rows = []
        for tid, p in portfolio.positions.items():
            pos_rows.append({
                "Token": tid[:16] + "...",
                "市场": p.get("market_title", "")[:40],
                "方向": p.get("outcome", ""),
                "数量": p["qty"],
                "成本价": f"{p['avg_price']:.3f}",
                "成本": f"${p['qty'] * p['avg_price']:.2f}",
            })
        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True)
    else:
        st.info("暂无持仓")

    st.subheader("交易记录")
    if portfolio.trades:
        tdf = pd.DataFrame(portfolio.trades[::-1])
        st.dataframe(tdf, use_container_width=True, height=300)
    else:
        st.info("暂无交易")

    if st.button("重置模拟账户"):
        st.session_state.portfolio = PaperPortfolio(10000.0)
        st.success("账户已重置为 $10,000")
        st.rerun()


# ==================== 页面：策略回测 ====================
elif page == "🧪 策略回测":
    st.header("🧪 简单策略回测")
    st.markdown("使用历史价格序列对简单规则进行回测（示例策略，非实盘建议）。")

    markets = fetch_markets(limit=40)
    if markets:
        m_opts = {(m.get("question") or "")[:55]: m for m in markets}
        sel = st.selectbox("选择回测市场", list(m_opts.keys()), key="bt_market")
        market = m_opts[sel]
        token_ids = get_token_ids(market)

        strategy = st.selectbox("策略类型", ["均值回归", "动量突破"])
        lookback = st.slider("回看周期 (点)", 5, 50, 12)
        threshold = st.slider("阈值 / 敏感度", 0.02, 0.20, 0.05, 0.01)
        initial = st.number_input("初始资金", value=10000.0, step=1000.0)

        if st.button("运行回测", type="primary") and token_ids:
            with st.spinner("获取历史数据并回测中..."):
                history = fetch_price_history(token_ids[0], interval="1h", fidelity=60)
                if len(history) < lookback + 5:
                    st.warning("真实历史数据不足，使用模拟价格序列演示回测逻辑")
                    np.random.seed(42)
                    n = 200
                    prices = 0.5 + np.cumsum(np.random.randn(n) * 0.015)
                    prices = np.clip(prices, 0.05, 0.95)
                    times = pd.date_range(end=datetime.now(), periods=n, freq="h")
                else:
                    hdf = pd.DataFrame(history)
                    prices = hdf["p"].values if "p" in hdf.columns else hdf.iloc[:, 1].values
                    times = pd.to_datetime(hdf["t"], unit="s") if "t" in hdf.columns else pd.date_range(end=datetime.now(), periods=len(prices), freq="h")

                cash = initial
                position = 0.0
                equity_curve = []
                trades = []

                for i in range(lookback, len(prices)):
                    window = prices[
