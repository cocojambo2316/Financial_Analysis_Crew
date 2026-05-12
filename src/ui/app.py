from pathlib import Path
import sys
import hashlib

import streamlit as st
import pandas as pd
import duckdb
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.all_agents import ANALYSTS
from src.cache_store import analysis_cache_key, db_signature, load_json_cache, normalize_tickers, save_json_cache
from src.pipeline.extract import get_stock_data


@st.cache_data(show_spinner=False, ttl=300)
def get_stocks_from_db() -> pd.DataFrame:
    """Fetch stocks table from DuckDB."""
    try:
        con = duckdb.connect('data/risk_database.duckdb')
        df = con.execute("SELECT * FROM stocks LIMIT 100").fetchdf()
        con.close()
        return df
    except Exception as e:
        st.warning(f"Could not read DuckDB: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=300)
def get_price_data(ticker: str, days: int = 90) -> pd.DataFrame:
    """Fetch historical price data from yfinance, falling back to DuckDB if needed."""
    ticker = ticker.strip().upper()
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

        if not data.empty:
            data = data.reset_index()
            data.columns = [str(col).strip() for col in data.columns]
            if "Adj Close" not in data.columns:
                data["Adj Close"] = pd.NA
            data = data[[col for col in ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if col in data.columns]]
            if "Date" in data.columns:
                data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
                data = data.dropna(subset=["Date"])
                return data.sort_values("Date")
    except Exception:
        pass

    try:
        con = duckdb.connect('data/risk_database.duckdb')
        query = """
            SELECT "Date", Open, High, Low, Close, "Adj Close", Volume
            FROM stocks
            WHERE Ticker = ?
            ORDER BY "Date" DESC
            LIMIT ?
        """
        data = con.execute(query, [ticker, days + 5]).fetchdf()
        con.close()
        if not data.empty:
            data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
            data = data.dropna(subset=["Date"]).sort_values("Date")
        return data
    except Exception:
        return pd.DataFrame()


def run_cached_agent(agent_name: str, tickers: list[str]) -> tuple[str, bool]:
    signature = db_signature()
    cache_key = analysis_cache_key(agent_name, tickers, signature)
    cached_payload = load_json_cache(cache_key)
    if cached_payload and cached_payload.get("report"):
        return compact_report_text(cached_payload["report"]), True

    if agent_name not in ANALYSTS:
        raise ValueError(f"Unknown agent: {agent_name}")

    report = ANALYSTS[agent_name]()
    report = compact_report_text(report)
    save_json_cache(
        cache_key,
        {
            "agent": agent_name,
            "tickers": normalize_tickers(tickers),
            "db_signature": signature,
            "report": report,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return report, False


def run_cached_news_agent(tickers: list[str], volatility_summary: str) -> tuple[str, bool]:
    signature = f"{db_signature()}:{hashlib.sha256(volatility_summary.encode('utf-8')).hexdigest()}"
    cache_key = analysis_cache_key("news", tickers, signature)
    cached_payload = load_json_cache(cache_key)
    if cached_payload and cached_payload.get("report"):
        return compact_report_text(cached_payload["report"]), True

    from src.agents.News_Scout import run_news_scout

    report = compact_report_text(run_news_scout(volatility_summary))
    save_json_cache(
        cache_key,
        {
            "agent": "news",
            "tickers": normalize_tickers(tickers),
            "db_signature": signature,
            "report": report,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return report, False


def compact_report_text(report: str, max_lines: int = 25, max_chars: int = 2500) -> str:
    """Remove duplicate lines and cap the visible report length."""
    if not report:
        return report

    lines = [line.rstrip() for line in report.splitlines()]
    compacted: list[str] = []
    seen_lines: set[str] = set()

    for line in lines:
        normalized = line.strip()
        if not normalized:
            if compacted and compacted[-1] != "":
                compacted.append("")
            continue

        if normalized in seen_lines:
            continue

        seen_lines.add(normalized)
        compacted.append(line)

        if len(compacted) >= max_lines:
            break

    result = "\n".join(compacted).strip()
    if len(result) > max_chars:
        result = result[:max_chars].rstrip() + "\n... (truncated)"

    return result


def is_valid_ticker(symbol: str) -> bool:
    """Validate ticker exists on yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        return ticker.info.get('symbol') is not None
    except Exception:
        return False

st.set_page_config(page_title="Financial AI Agent", layout="wide")

st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at 10% 15%, rgba(0, 255, 179, 0.22), transparent 18%),
                radial-gradient(circle at 85% 12%, rgba(255, 87, 163, 0.22), transparent 16%),
                radial-gradient(circle at 78% 78%, rgba(102, 227, 255, 0.18), transparent 20%),
                linear-gradient(135deg, #061126 0%, #081634 36%, #120f52 68%, #030712 100%);
            color: #f4f7fb;
        }

        .stApp::before {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
            background-size: 72px 72px;
            mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.55), transparent 90%);
            opacity: 0.18;
            z-index: 0;
        }

        section.main > div.block-container {
            position: relative;
            z-index: 1;
            padding: 1.1rem 1.2rem 2rem;
            border-radius: 28px;
            background: rgba(7, 13, 33, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
            backdrop-filter: blur(18px);
        }

        .hero-panel {
            position: relative;
            overflow: hidden;
            min-height: 140px;
            padding: 1.35rem 1.4rem;
            border-radius: 26px;
            background:
                linear-gradient(135deg, rgba(23, 40, 110, 0.86), rgba(7, 12, 35, 0.72)),
                radial-gradient(circle at 18% 20%, rgba(55, 255, 184, 0.16), transparent 24%),
                radial-gradient(circle at 80% 30%, rgba(255, 90, 190, 0.16), transparent 22%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 20px 45px rgba(0, 0, 0, 0.24);
        }

        .hero-panel::after {
            content: "";
            position: absolute;
            inset: auto -12% -38% auto;
            width: 280px;
            height: 280px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(95, 220, 255, 0.26), rgba(95, 220, 255, 0.02) 68%, transparent 72%);
            filter: blur(12px);
            opacity: 0.85;
            pointer-events: none;
        }

        .hero-grid {
            position: relative;
            display: grid;
            grid-template-columns: 1.6fr 0.9fr;
            gap: 1rem;
            align-items: stretch;
            z-index: 1;
        }

        .hero-copy {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 1rem;
        }

        .hero-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            width: fit-content;
            padding: 0.38rem 0.72rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: rgba(245, 249, 255, 0.9);
            font-size: 0.82rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .hero-kicker .pulse {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #67ffce;
            box-shadow: 0 0 16px #67ffce;
        }

        .hero-aside {
            display: grid;
            gap: 0.75rem;
            align-content: start;
        }

        .hero-card {
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: rgba(10, 16, 39, 0.58);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 14px 28px rgba(0, 0, 0, 0.2);
        }

        .hero-card-label {
            color: rgba(235, 243, 255, 0.68);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .hero-card-value {
            margin-top: 0.3rem;
            color: #ffffff;
            font-size: 1.05rem;
            font-weight: 700;
        }

        .hero-card-note {
            margin-top: 0.25rem;
            color: rgba(235, 243, 255, 0.64);
            font-size: 0.8rem;
        }

        .hero-title {
            font-size: 2.1rem;
            font-weight: 800;
            line-height: 1.05;
            color: #ffffff;
            margin: 0;
        }

        .hero-subtitle {
            margin-top: 0.45rem;
            color: rgba(235, 243, 255, 0.78);
            font-size: 1rem;
            max-width: 54rem;
        }

        .signal-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 1rem 0 0.6rem;
        }

        .signal-card {
            position: relative;
            overflow: hidden;
            padding: 0.95rem 1rem;
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(10, 18, 44, 0.78), rgba(8, 12, 31, 0.62));
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.18);
        }

        .signal-card::before {
            content: "";
            position: absolute;
            top: -40px;
            right: -28px;
            width: 110px;
            height: 110px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(95, 220, 255, 0.22), transparent 68%);
        }

        .signal-label {
            color: rgba(235, 243, 255, 0.68);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .signal-value {
            margin-top: 0.32rem;
            color: #fff;
            font-size: 1.05rem;
            font-weight: 700;
        }

        .signal-foot {
            margin-top: 0.2rem;
            color: rgba(235, 243, 255, 0.62);
            font-size: 0.8rem;
        }

        .section-title {
            margin: 1.1rem 0 0.55rem;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: rgba(235, 243, 255, 0.64);
        }

        .orb {
            position: fixed;
            border-radius: 999px;
            filter: blur(2px);
            opacity: 0.7;
            pointer-events: none;
            z-index: 0;
            animation: floatOrb 14s ease-in-out infinite;
        }

        .orb.one {
            width: 210px;
            height: 210px;
            left: -70px;
            top: 110px;
            background: radial-gradient(circle at 35% 30%, #69ffe0, #5a6cff 58%, #26104f 100%);
            animation-duration: 18s;
        }

        .orb.two {
            width: 150px;
            height: 150px;
            right: 2%;
            top: 10%;
            background: radial-gradient(circle at 35% 30%, #ff76c6, #7f5dff 60%, #14215f 100%);
            animation-duration: 16s;
        }

        .orb.three {
            width: 120px;
            height: 120px;
            right: 15%;
            bottom: 8%;
            background: radial-gradient(circle at 35% 30%, #9dffb0, #43d2ff 55%, #15315f 100%);
            animation-duration: 20s;
        }

        @keyframes floatOrb {
            0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
            50% { transform: translate3d(0, -16px, 0) scale(1.04); }
        }

        .stMetric {
            background: rgba(10, 18, 44, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            padding: 12px 14px;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
            backdrop-filter: blur(10px);
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            margin-top: 0.45rem;
            padding: 0.4rem 0.75rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(255, 255, 255, 0.05);
            font-size: 0.9rem;
            font-weight: 700;
        }

        .status-pill .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: currentColor;
            box-shadow: 0 0 16px currentColor;
        }

        .metric-note {
            margin-top: 0.35rem;
            color: rgba(235, 243, 255, 0.72);
            font-size: 0.82rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }

        .stTabs [data-baseweb="tab"] {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px 14px 0 0;
            padding: 10px 16px;
        }

        .stTabs [aria-selected="true"] {
            background: rgba(95, 220, 255, 0.16);
            border-color: rgba(95, 220, 255, 0.28);
        }

        .stExpander {
            border-radius: 18px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.08);
            background: rgba(10, 16, 39, 0.48);
            box-shadow: 0 16px 28px rgba(0, 0, 0, 0.16);
        }

        .stButton > button {
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: linear-gradient(135deg, rgba(95, 220, 255, 0.24), rgba(115, 86, 255, 0.2));
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 14px 28px rgba(0, 0, 0, 0.2);
            transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
        }

        .stButton > button:hover {
            transform: translateY(-1px);
            border-color: rgba(95, 220, 255, 0.34);
            box-shadow: 0 18px 34px rgba(0, 0, 0, 0.24);
        }

        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(7, 13, 33, 0.96), rgba(9, 15, 38, 0.92));
            border-right: 1px solid rgba(255, 255, 255, 0.07);
        }

        div[data-testid="stSidebar"] .stTextInput input,
        div[data-testid="stSidebar"] .stMultiSelect div,
        div[data-testid="stSidebar"] .stSelectbox div {
            border-radius: 14px;
        }
    </style>
    <div class="orb one"></div>
    <div class="orb two"></div>
    <div class="orb three"></div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero-panel">
        <div class="hero-grid">
            <div class="hero-copy">
                <div class="hero-kicker"><span class="pulse"></span> Real-time portfolio intelligence</div>
                <div>
                    <h1 class="hero-title">🛡️ Financial Risk Control Center</h1>
                    <div class="hero-subtitle">Live portfolio monitoring, quantitative risk checks, and market catalyst tracking wrapped in a premium control-room layout.</div>
                </div>
            </div>
            <div class="hero-aside">
                <div class="hero-card">
                    <div class="hero-card-label">Status</div>
                    <div class="hero-card-value">Multimodal dashboard</div>
                    <div class="hero-card-note">Signals, news, and pricing in one glass panel.</div>
                </div>
                <div class="hero-card">
                    <div class="hero-card-label">Focus</div>
                    <div class="hero-card-value">Risk first, then opportunity</div>
                    <div class="hero-card-note">Designed for fast scanning and low-friction decisions.</div>
                </div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if "last_update" not in st.session_state:
    st.session_state.last_update = "Not yet run"
if "system_status" not in st.session_state:
    st.session_state.system_status = "Ready"
if "system_status_color" not in st.session_state:
    st.session_state.system_status_color = "#61ff9a"
if "quant_report" not in st.session_state:
    st.session_state.quant_report = ""
if "news_report" not in st.session_state:
    st.session_state.news_report = ""

# We'll store tickers in session state to persist across interactions
if 'tickers' not in st.session_state:
    st.session_state.tickers = ["AAPL", "TSLA", "CDR.WA"]
if 'risk_report' not in st.session_state:
    st.session_state.risk_report = ""

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Total Assets", len(st.session_state.tickers), "Portfolio")
metric_col2.metric("Last Update", st.session_state.last_update, "Manual")
metric_col3.metric("System Status", "")
st.markdown(
    f"<div class='status-pill' style='color: {st.session_state.system_status_color};'>"
    f"<span class='dot'></span>{st.session_state.system_status}</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='metric-note'>Yellow means the pipeline is working. Green means the app is ready.</div>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="signal-row">
        <div class="signal-card">
            <div class="signal-label">Portfolio Basket</div>
            <div class="signal-value">High-signal names ready</div>
            <div class="signal-foot">The active universe is staged for analysis.</div>
        </div>
        <div class="signal-card">
            <div class="signal-label">Analysis Mode</div>
            <div class="signal-value">Parallel agents armed</div>
            <div class="signal-foot">Risk, tech, and news can run side-by-side.</div>
        </div>
        <div class="signal-card">
            <div class="signal-label">Market View</div>
            <div class="signal-value">Candlestick-first insights</div>
            <div class="signal-foot">Price action stays visible without leaving the cockpit.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='section-title'>Workspace</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Portfolio Management")
    new_ticker = st.text_input("Add Ticker (e.g., MSFT)").strip().upper()

    if st.button("Add"):
        if not new_ticker:
            st.toast("Enter a ticker symbol first.")
        elif not is_valid_ticker(new_ticker):
            st.toast(f"Ticker {new_ticker} not found on yfinance. Check spelling.")
        elif new_ticker in st.session_state.tickers:
            st.toast(f"{new_ticker} is already in the portfolio.")
        else:
            st.session_state.tickers.append(new_ticker)
            st.toast(f"{new_ticker} added to portfolio", icon="✅")

    active_tickers = st.multiselect(
        "Active Assets:",
        options=st.session_state.tickers,
        default=st.session_state.tickers,
        key="active_tickers",
    )

# Main Panel
analysis_col, news_col = st.columns([1, 1])

with analysis_col:
    if st.button("🚀 Run Data Collection"):
        st.session_state.system_status = "Analyzing..."
        st.session_state.system_status_color = "#ffd84d"
        with st.status("Syncing market data...", expanded=False) as status:
            loaded_messages = []
            for ticker in active_tickers or st.session_state.tickers:
                loaded_messages.append(get_stock_data(ticker))
            st.write("\n".join(loaded_messages))
            status.update(label="Data sync complete", state="complete")
        st.session_state.last_update = datetime.now().strftime("%H:%M (Today)")
        st.session_state.system_status = "Ready"
        st.session_state.system_status_color = "#61ff9a"
        st.cache_data.clear()
        st.toast("Data collection complete")

with news_col:
    if st.button("🧠 Run AI Analysis"):
        st.session_state.system_status = "Analyzing..."
        st.session_state.system_status_color = "#ffd84d"
        with st.status("Agents are collaborating...", expanded=False) as status:
            st.write("Quant is calculating sigma events...")
            st.write("NewsGuy is searching for catalysts...")
            active_selection = active_tickers or st.session_state.tickers
            st.session_state.risk_report, risk_cached = run_cached_agent("risk", active_selection)
            st.session_state.quant_report, quant_cached = run_cached_agent("tech", active_selection)
            st.session_state.news_report, news_cached = run_cached_news_agent(active_selection, st.session_state.quant_report)
            cache_state = ", ".join(
                [
                    f"risk={'hit' if risk_cached else 'fresh'}",
                    f"tech={'hit' if quant_cached else 'fresh'}",
                    f"news={'hit' if news_cached else 'fresh'}",
                ]
            )
            st.write(f"Cache status: {cache_state}")
            status.update(label="Analysis Complete!", state="complete")
        st.session_state.system_status = "Ready"
        st.session_state.system_status_color = "#61ff9a"
        st.toast("AI analysis complete")

results_tab, news_tab = st.tabs(["Quantitative Analysis", "Market News"])
with results_tab:
    st.subheader("Quantitative Risk Audit")
    with st.expander("Show Detailed SQL Calculations", expanded=False):
        st.code("SELECT ticker, MAX(close) - MIN(close) AS price_range FROM stocks GROUP BY ticker;")
        db_df = get_stocks_from_db()
        if not db_df.empty:
            st.dataframe(db_df, use_container_width=True, height=300)
        else:
            st.info("No data in DuckDB yet. Run Data Collection first.")
    if st.session_state.quant_report:
        st.markdown("<div class='hero-card'>" + st.session_state.quant_report.replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
    else:
        st.info("Results from your Tech Agent will be here.")
    if st.session_state.risk_report:
        with st.expander("Risk Agent Summary", expanded=False):
            st.markdown("<div class='hero-card'>" + st.session_state.risk_report.replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
with news_tab:
    st.subheader("Market Catalyst Report")
    col_news, col_chart = st.columns([1, 1])
    with col_news:
        st.write("Recent Catalysts:")
        with st.expander("Show News Search Context", expanded=False):
            st.code("search_news('AAPL earnings')")
        if st.session_state.news_report:
            st.markdown("<div class='hero-card'>" + st.session_state.news_report.replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
        else:
            st.warning("Results from NewsGuy will be here.")
    with col_chart:
        st.write("Price Trends:")
        if active_tickers or st.session_state.tickers:
            selected_ticker = st.selectbox(
                "Select ticker for chart:",
                active_tickers or st.session_state.tickers,
                key="chart_ticker",
            )
            price_df = get_price_data(selected_ticker, days=90)
            if not price_df.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=price_df["Date"],
                    open=price_df["Open"],
                    high=price_df["High"],
                    low=price_df["Low"],
                    close=price_df["Close"]
                )])
                fig.update_layout(
                    title=f"{selected_ticker} Price (90D)",
                    yaxis_title="Price (USD)",
                    xaxis_title="Date",
                    template="plotly_dark",
                    height=400,
                    hovermode="x unified"
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"Could not fetch price data for {selected_ticker}")
        else:
            st.info("Add tickers to see price trends.")