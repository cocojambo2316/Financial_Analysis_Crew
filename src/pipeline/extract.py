from datetime import timedelta
import ast
from collections import defaultdict
from pathlib import Path
import os

import duckdb
import pandas as pd
import yfinance as yf


DB_PATH = Path("data/risk_database.duckdb")
NORMALIZED_STOCK_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "Ticker"]


def _ensure_data_dir() -> None:
    if not os.path.exists("data"):
        os.makedirs("data")


def _ensure_stocks_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        'CREATE TABLE IF NOT EXISTS stocks ("Date" TIMESTAMP, Open DOUBLE, High DOUBLE, Low DOUBLE, Close DOUBLE, "Adj Close" DOUBLE, Volume BIGINT, Ticker VARCHAR)'
    )


def _stock_table_is_normalized(con: duckdb.DuckDBPyConnection) -> bool:
    try:
        columns = [row[1] for row in con.execute("PRAGMA table_info('stocks')").fetchall()]
    except Exception:
        return False

    return columns == NORMALIZED_STOCK_COLUMNS
    \


def _parse_legacy_column_name(column_name: str) -> tuple[str, str] | None:
    try:
        parsed = ast.literal_eval(column_name)
    except Exception:
        return None

    if not isinstance(parsed, tuple) or len(parsed) != 2:
        return None

    metric, ticker = parsed
    metric = str(metric).strip()
    ticker = str(ticker).strip()
    if metric.lower() == "date":
        return ("Date", "")
    return metric, ticker


def _migrate_legacy_stocks_table(con: duckdb.DuckDBPyConnection) -> None:
    if _stock_table_is_normalized(con):
        return

    legacy_df = con.execute("SELECT * FROM stocks").fetchdf()
    if legacy_df.empty:
        con.execute("DROP TABLE IF EXISTS stocks")
        _ensure_stocks_table(con)
        return

    parsed_columns: list[tuple[str, str, str]] = []
    for column_name in legacy_df.columns:
        parsed = _parse_legacy_column_name(str(column_name))
        if parsed is None:
            continue
        metric, ticker = parsed
        parsed_columns.append((str(column_name), metric, ticker))

    if not parsed_columns:
        con.execute("DROP TABLE IF EXISTS stocks")
        _ensure_stocks_table(con)
        return

    tickers = sorted({ticker for _, _, ticker in parsed_columns if ticker})
    if not tickers:
        con.execute("DROP TABLE IF EXISTS stocks")
        _ensure_stocks_table(con)
        return

    normalized_rows = []
    date_column = next((col for col, metric, ticker in parsed_columns if metric == "Date"), None)
    if date_column is None:
        con.execute("DROP TABLE IF EXISTS stocks")
        _ensure_stocks_table(con)
        return

    for ticker in tickers:
        ticker_columns = {
            metric: column_name
            for column_name, metric, column_ticker in parsed_columns
            if column_ticker == ticker and metric != "Date"
        }
        if not ticker_columns:
            continue

        ticker_frame = pd.DataFrame({"Date": legacy_df[date_column]})
        for metric in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
            source_column = ticker_columns.get(metric)
            if source_column is not None:
                ticker_frame[metric] = legacy_df[source_column]
            elif metric == "Adj Close":
                ticker_frame[metric] = pd.NA
            else:
                ticker_frame[metric] = pd.NA

        ticker_frame["Ticker"] = ticker
        ticker_frame = ticker_frame.dropna(subset=["Date"])
        normalized_rows.append(ticker_frame)

    normalized_df = pd.concat(normalized_rows, ignore_index=True) if normalized_rows else pd.DataFrame(columns=NORMALIZED_STOCK_COLUMNS)
    normalized_df = normalized_df[NORMALIZED_STOCK_COLUMNS]

    con.execute("DROP TABLE IF EXISTS stocks")
    _ensure_stocks_table(con)
    if not normalized_df.empty:
        con.register("normalized_stock_data", normalized_df)
        con.execute(
            'INSERT INTO stocks ("Date", Open, High, Low, Close, "Adj Close", Volume, Ticker) '
            'SELECT "Date", Open, High, Low, Close, "Adj Close", Volume, Ticker FROM normalized_stock_data'
        )


def _get_last_loaded_date(con: duckdb.DuckDBPyConnection, ticker: str):
    try:
        row = con.execute(
            'SELECT MAX(CAST("Date" AS DATE)) FROM stocks WHERE Ticker = ?',
            [ticker],
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _download_stock_data(ticker: str, last_loaded_date) -> pd.DataFrame:
    if last_loaded_date is None:
        data = yf.download(ticker, period="1y", interval="1d", progress=False)
    else:
        start_date = pd.Timestamp(last_loaded_date) + pd.Timedelta(days=1)
        end_date = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
        if start_date >= end_date:
            return pd.DataFrame()
        data = yf.download(
            ticker,
            start=start_date.to_pydatetime(),
            end=end_date.to_pydatetime(),
            interval="1d",
            progress=False,
        )

    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    data = data.reset_index()
    if "Adj Close" not in data.columns:
        data["Adj Close"] = pd.NA

    data["Ticker"] = ticker
    return data[["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "Ticker"]]


def get_stock_data(ticker="TSLA"):
    ticker = ticker.strip().upper()
    print(f"Data is getting downloaded {ticker}...")

    _ensure_data_dir()

    con = duckdb.connect(str(DB_PATH))
    try:
        _ensure_stocks_table(con)
        _migrate_legacy_stocks_table(con)
        last_loaded_date = _get_last_loaded_date(con, ticker)
        data = _download_stock_data(ticker, last_loaded_date)

        if data.empty:
            message = f"⏭️ No new rows for {ticker}; using cached DuckDB data."
            print(message)
            return message

        con.register("incoming_stock_data", data)
        con.execute(
            'INSERT INTO stocks ("Date", Open, High, Low, Close, "Adj Close", Volume, Ticker) '
            'SELECT "Date", Open, High, Low, Close, "Adj Close", Volume, Ticker FROM incoming_stock_data'
        )

        message = f"✅ Stored {len(data)} fresh rows for {ticker} in {DB_PATH}."
        print(message)
        return message
    finally:
        con.close()

if __name__ == "__main__":
    portfolio = ["AAPL", "TSLA", "MSFT", "CDR.WA"]
    
    for company in portfolio:
        try:
            get_stock_data(company)
        except Exception as e:
            print(f"Error occurred while downloading data for {company}: {e}")