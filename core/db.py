"""
Persistencia en SQLite via SQLAlchemy.
Modelos: Portfolio, Tenencia, Transaccion.

Multi-portfolio: cada Tenencia pertenece a un Portfolio. Si la DB ya existia
sin la columna portfolio_id, se hace migracion automatica no destructiva
(ALTER TABLE + asignacion al portfolio "default").
"""
import os
from datetime import datetime, date
from typing import List
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, DateTime,
    ForeignKey, select, inspect,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "portfolio.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()


class Portfolio(Base):
    __tablename__ = "portfolios"
    id      = Column(Integer, primary_key=True, autoincrement=True)
    nombre  = Column(String(64), nullable=False, unique=True)
    cliente = Column(String(128), nullable=True)   # nombre del titular
    notas   = Column(String(512), nullable=True)
    creado  = Column(DateTime, default=datetime.utcnow)

    tenencias = relationship("Tenencia", back_populates="portfolio",
                             cascade="all, delete-orphan")


class Tenencia(Base):
    __tablename__ = "tenencias"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id  = Column(Integer, ForeignKey("portfolios.id"), nullable=True, index=True)
    ticker        = Column(String(32), nullable=False, index=True)
    tipo          = Column(String(32), nullable=False)
    cantidad      = Column(Float, nullable=False)
    precio_compra = Column(Float, nullable=False)
    moneda_compra = Column(String(8), nullable=False, default="ARS")
    fecha_compra  = Column(Date, nullable=False, default=date.today)
    creado        = Column(DateTime, default=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="tenencias")


class Transaccion(Base):
    __tablename__ = "transacciones"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(32), nullable=False)
    tipo_op = Column(String(16), nullable=False)
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)
    moneda = Column(String(8), default="ARS")
    fecha = Column(Date, nullable=False)
    creado = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# MIGRACION NO DESTRUCTIVA
# ---------------------------------------------------------------------------
def _migrate_portfolios() -> None:
    """
    Si la DB ya existia sin la columna portfolio_id en tenencias, la agrega
    y asigna todas las tenencias huerfanas al primer portfolio (creandolo si
    no hay ninguno).
    """
    insp = inspect(engine)
    if "tenencias" in insp.get_table_names():
        cols = [c["name"] for c in insp.get_columns("tenencias")]
        if "portfolio_id" not in cols:
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "ALTER TABLE tenencias ADD COLUMN portfolio_id INTEGER")

    with SessionLocal() as s:
        if not s.query(Portfolio).first():
            s.add(Portfolio(nombre="Portafolio principal", cliente="Yo"))
            s.commit()
        primer = s.query(Portfolio).order_by(Portfolio.id).first()
        if primer is None:
            return
        orphans = s.query(Tenencia).filter(
            (Tenencia.portfolio_id == None) | (Tenencia.portfolio_id == 0)  # noqa
        ).all()
        for o in orphans:
            o.portfolio_id = primer.id
        if orphans:
            s.commit()


def init_db(seed: bool = False) -> None:
    """Crea tablas si no existen y migra al esquema multi-portfolio si hace falta."""
    Base.metadata.create_all(engine)
    _migrate_portfolios()
    if not seed:
        return
    with SessionLocal() as s:
        count = s.scalar(select(Tenencia).limit(1))
        if count is not None:
            return
        pf = s.query(Portfolio).order_by(Portfolio.id).first()
        pf_id = pf.id if pf else 1
        ejemplos = [
            Tenencia(portfolio_id=pf_id, ticker="GGAL.BA", tipo="accion_ar", cantidad=200, precio_compra=4500,  moneda_compra="ARS", fecha_compra=date(2024, 6, 1)),
            Tenencia(portfolio_id=pf_id, ticker="AAPL",    tipo="accion_us", cantidad=5,   precio_compra=180,   moneda_compra="USD", fecha_compra=date(2024, 3, 10)),
            Tenencia(portfolio_id=pf_id, ticker="BTC-USD", tipo="cripto",    cantidad=0.05, precio_compra=62000, moneda_compra="USD", fecha_compra=date(2024, 8, 1)),
        ]
        s.add_all(ejemplos)
        s.commit()


# ---------------------------------------------------------------------------
# CRUD de Portfolios
# ---------------------------------------------------------------------------
def list_portfolios() -> List[dict]:
    """Devuelve [{id, nombre, cliente, n_tenencias}] ordenado por id."""
    with SessionLocal() as s:
        rows = s.query(Portfolio).order_by(Portfolio.id).all()
        out = []
        for p in rows:
            count = s.query(Tenencia).filter(Tenencia.portfolio_id == p.id).count()
            out.append({
                "id": p.id, "nombre": p.nombre, "cliente": p.cliente,
                "notas": p.notas, "n_tenencias": count,
            })
        return out


def create_portfolio(nombre: str, cliente: str = "", notas: str = "") -> int:
    """Crea un portfolio nuevo. Devuelve su id. Lanza si el nombre ya existe."""
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del portfolio no puede estar vacio.")
    with SessionLocal() as s:
        if s.query(Portfolio).filter(Portfolio.nombre == nombre).first():
            raise ValueError(f"Ya existe un portfolio llamado '{nombre}'.")
        p = Portfolio(nombre=nombre, cliente=cliente.strip() or None,
                      notas=notas.strip() or None)
        s.add(p)
        s.commit()
        return p.id


def rename_portfolio(pid: int, nombre: str, cliente: str = "", notas: str = "") -> None:
    with SessionLocal() as s:
        p = s.get(Portfolio, pid)
        if not p:
            raise ValueError("Portfolio no encontrado.")
        if nombre.strip():
            # validar duplicados
            existing = s.query(Portfolio).filter(
                Portfolio.nombre == nombre.strip(),
                Portfolio.id != pid,
            ).first()
            if existing:
                raise ValueError(f"Ya existe '{nombre}'.")
            p.nombre = nombre.strip()
        p.cliente = cliente.strip() or None
        p.notas = notas.strip() or None
        s.commit()


def delete_portfolio(pid: int) -> None:
    """Borra un portfolio Y todas sus tenencias (cascade)."""
    with SessionLocal() as s:
        p = s.get(Portfolio, pid)
        if not p:
            return
        # Bloqueamos borrar el ultimo portfolio
        total = s.query(Portfolio).count()
        if total <= 1:
            raise ValueError("No podes eliminar el unico portfolio. Crea otro primero.")
        s.delete(p)
        s.commit()


def get_session() -> Session:
    return SessionLocal()
