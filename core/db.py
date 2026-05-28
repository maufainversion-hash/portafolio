"""
Persistencia en SQLite via SQLAlchemy.
Modelos: Tenencia, Transaccion.
Incluye seed de tenencias de ejemplo para primer arranque.
"""
import os
from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime, select
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "portfolio.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()


class Tenencia(Base):
    __tablename__ = "tenencias"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(32), nullable=False, index=True)
    tipo = Column(String(32), nullable=False)  # accion_ar, cedear, accion_us, etf, bono, cripto, fci
    cantidad = Column(Float, nullable=False)
    precio_compra = Column(Float, nullable=False)
    moneda_compra = Column(String(8), nullable=False, default="ARS")  # ARS / USD
    fecha_compra = Column(Date, nullable=False, default=date.today)
    creado = Column(DateTime, default=datetime.utcnow)


class Transaccion(Base):
    __tablename__ = "transacciones"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(32), nullable=False)
    tipo_op = Column(String(16), nullable=False)  # compra, venta, dividendo
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)
    moneda = Column(String(8), default="ARS")
    fecha = Column(Date, nullable=False)
    creado = Column(DateTime, default=datetime.utcnow)


def init_db(seed: bool = True) -> None:
    """Crea tablas si no existen y seedea ejemplos si la tabla queda vacia."""
    Base.metadata.create_all(engine)
    if not seed:
        return
    with SessionLocal() as s:
        count = s.scalar(select(Tenencia).limit(1))
        if count is not None:
            return
        ejemplos = [
            Tenencia(ticker="GGAL.BA",  tipo="accion_ar", cantidad=200, precio_compra=4500,  moneda_compra="ARS", fecha_compra=date(2024, 6, 1)),
            Tenencia(ticker="YPFD.BA",  tipo="accion_ar", cantidad=150, precio_compra=35000, moneda_compra="ARS", fecha_compra=date(2024, 7, 1)),
            Tenencia(ticker="PAMP.BA",  tipo="accion_ar", cantidad=300, precio_compra=2800,  moneda_compra="ARS", fecha_compra=date(2024, 5, 15)),
            Tenencia(ticker="AAPL",     tipo="accion_us", cantidad=5,   precio_compra=180,   moneda_compra="USD", fecha_compra=date(2024, 3, 10)),
            Tenencia(ticker="MSFT",     tipo="accion_us", cantidad=3,   precio_compra=410,   moneda_compra="USD", fecha_compra=date(2024, 4, 5)),
            Tenencia(ticker="SPY",      tipo="etf",       cantidad=4,   precio_compra=520,   moneda_compra="USD", fecha_compra=date(2024, 2, 20)),
            Tenencia(ticker="BTC-USD",  tipo="cripto",    cantidad=0.05, precio_compra=62000, moneda_compra="USD", fecha_compra=date(2024, 8, 1)),
        ]
        s.add_all(ejemplos)
        s.commit()


def get_session() -> Session:
    return SessionLocal()
