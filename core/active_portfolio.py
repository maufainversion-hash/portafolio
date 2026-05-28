"""
Portfolio activo global.

Vive en st.session_state["active_portfolio_id"]. Si no hay ninguno, se elige
automaticamente el primer portfolio de la DB.

Helpers:
- get_active_portfolio_id() -> int
- get_active_portfolio_info() -> dict (id, nombre, cliente, ...)
- set_active_portfolio(id) -> None
"""
from __future__ import annotations
from typing import Optional
import streamlit as st

from core.db import list_portfolios


def _fallback_first_id() -> Optional[int]:
    plist = list_portfolios()
    return plist[0]["id"] if plist else None


def get_active_portfolio_id() -> Optional[int]:
    pid = st.session_state.get("active_portfolio_id")
    if pid is None:
        pid = _fallback_first_id()
        if pid is not None:
            st.session_state["active_portfolio_id"] = pid
    return pid


def set_active_portfolio(pid: int) -> None:
    st.session_state["active_portfolio_id"] = pid


def get_active_portfolio_info() -> Optional[dict]:
    pid = get_active_portfolio_id()
    if pid is None:
        return None
    for p in list_portfolios():
        if p["id"] == pid:
            return p
    return None


def get_active_portfolio_label() -> str:
    info = get_active_portfolio_info()
    if not info:
        return "Sin portfolio"
    if info.get("cliente"):
        return f"{info['nombre']} · {info['cliente']}"
    return info["nombre"]
