"""
Metricas cuantitativas sobre series de retornos.
Todas las funciones aceptan pd.Series y devuelven floats.
Trading days/year = 252.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def returns_from_prices(prices: pd.Series) -> pd.Series:
    """Retornos diarios simples a partir de precios."""
    return prices.pct_change().dropna()


def cagr(prices: pd.Series) -> float:
    """Compound Annual Growth Rate desde una serie de precios."""
    if prices is None or len(prices) < 2:
        return 0.0
    total_return = prices.iloc[-1] / prices.iloc[0]
    days = (prices.index[-1] - prices.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    return float(total_return ** (1 / years) - 1)


def volatility(returns: pd.Series, annualize: bool = True) -> float:
    if returns is None or returns.empty:
        return 0.0
    vol = float(returns.std())
    return vol * np.sqrt(TRADING_DAYS) if annualize else vol


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    """Sharpe anualizado. rf en tasa anual."""
    if returns is None or returns.empty:
        return 0.0
    rf_daily = rf / TRADING_DAYS
    excess = returns - rf_daily
    std = excess.std()
    if std == 0 or pd.isna(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    if returns is None or returns.empty:
        return 0.0
    rf_daily = rf / TRADING_DAYS
    excess = returns - rf_daily
    downside = excess[excess < 0]
    dd_std = downside.std()
    if dd_std == 0 or pd.isna(dd_std) or len(downside) == 0:
        return 0.0
    return float(excess.mean() / dd_std * np.sqrt(TRADING_DAYS))


def max_drawdown(prices: pd.Series) -> float:
    """Max drawdown como fraccion negativa (-0.25 = -25%)."""
    if prices is None or prices.empty:
        return 0.0
    cummax = prices.cummax()
    dd = (prices / cummax) - 1
    return float(dd.min())


def calmar(prices: pd.Series) -> float:
    mdd = abs(max_drawdown(prices))
    if mdd == 0:
        return 0.0
    return cagr(prices) / mdd


def var_historic(returns: pd.Series, alpha: float = 0.05) -> float:
    """VaR historico al nivel alpha (default 5%). Devuelve numero negativo."""
    if returns is None or returns.empty:
        return 0.0
    return float(np.percentile(returns, alpha * 100))


def beta(returns: pd.Series, market_returns: pd.Series) -> float:
    """Beta vs benchmark. Alinea por indice."""
    if returns is None or market_returns is None:
        return 0.0
    df = pd.concat([returns, market_returns], axis=1).dropna()
    if df.shape[0] < 2:
        return 0.0
    cov = df.iloc[:, 0].cov(df.iloc[:, 1])
    var_m = df.iloc[:, 1].var()
    if var_m == 0 or pd.isna(var_m):
        return 0.0
    return float(cov / var_m)


def alpha(returns: pd.Series, market_returns: pd.Series, rf: float = 0.0) -> float:
    """Alpha de Jensen (anualizado, simple)."""
    if returns is None or market_returns is None or returns.empty:
        return 0.0
    rf_daily = rf / TRADING_DAYS
    b = beta(returns, market_returns)
    df = pd.concat([returns, market_returns], axis=1).dropna()
    if df.empty:
        return 0.0
    r_p = df.iloc[:, 0].mean()
    r_m = df.iloc[:, 1].mean()
    return float((r_p - rf_daily - b * (r_m - rf_daily)) * TRADING_DAYS)


def rolling_sharpe(returns: pd.Series, window: int = 30, rf: float = 0.0) -> pd.Series:
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    rf_daily = rf / TRADING_DAYS
    excess = returns - rf_daily
    return (excess.rolling(window).mean() / excess.rolling(window).std()) * np.sqrt(TRADING_DAYS)


def rolling_volatility(returns: pd.Series, window: int = 30) -> pd.Series:
    if returns is None or returns.empty:
        return pd.Series(dtype=float)
    return returns.rolling(window).std() * np.sqrt(TRADING_DAYS)


def summary(prices: pd.Series, rf: float = 0.0) -> dict:
    """Resumen completo de metricas sobre una serie de precios."""
    rets = returns_from_prices(prices)
    return {
        "cagr":         cagr(prices),
        "volatility":   volatility(rets),
        "sharpe":       sharpe(rets, rf),
        "sortino":      sortino(rets, rf),
        "max_drawdown": max_drawdown(prices),
        "calmar":       calmar(prices),
        "var_95":       var_historic(rets, 0.05),
    }
