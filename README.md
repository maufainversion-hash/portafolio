# 📊 TuPortafolioIA

App de seguimiento y análisis de portafolios de inversión enfocada en el mercado argentino, hecha en Streamlit.

## Features (Bloque 1 — MVP)

- 📊 **Dashboard** — KPIs, equity curve, donut de allocation, tabla de posiciones
- 🥧 **Allocation** — Treemap y sunburst por tipo / moneda / sector / país
- 📈 **Performance** — Sharpe, Sortino, CAGR, Max Drawdown, Calmar, VaR, rolling 30d
- ⚖️ **Rebalanceo** — Placeholder (bloque 2)
- 🇦🇷 **Contexto AR** — Dólar oficial / MEP / CCL / blue, brecha, riesgo país, Merval, inflación

## Stack

- **Streamlit** + `streamlit-option-menu` (nav horizontal)
- **yfinance** para precios y datos globales
- **dolarapi.com** + **argentinadatos.com** + **criptoya.com** para datos AR
- **SQLAlchemy** + **SQLite** para persistencia local
- **Plotly** para gráficos

## Setup local

```bash
git clone https://github.com/<TU_USUARIO>/tu-portafolio-ia.git
cd tu-portafolio-ia
python -m venv .venv
source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

La app levanta en `http://localhost:8501`. La primera vez crea `data/portfolio.db` con tenencias de ejemplo (GGAL, YPF, PAMP, AAPL, MSFT, SPY, BTC).

## Subir a GitHub

```bash
git init
git add .
git commit -m "feat(bloque-1): setup inicial + dashboard funcional"
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/tu-portafolio-ia.git
git push -u origin main
```

## Deploy a Streamlit Community Cloud (gratis)

1. Subí el repo a GitHub (paso anterior).
2. Entrá a [share.streamlit.io](https://share.streamlit.io/).
3. Login con GitHub → **New app**.
4. Repo: `<TU_USUARIO>/tu-portafolio-ia`, branch `main`, file `app.py`.
5. Click **Deploy**. Tarda ~2 min y queda en `https://<algo>.streamlit.app`.

> **Nota:** En Streamlit Community Cloud, la SQLite se reinicia con cada redeploy (filesystem efímero). Para persistencia real, en el bloque 2 podemos migrar a Postgres en Supabase.

## Estructura

```
tu-portafolio-ia/
├── app.py                   # entrypoint + nav horizontal
├── views/                   # una vista por tab
│   ├── dashboard.py
│   ├── allocation.py
│   ├── performance.py
│   ├── rebalanceo.py
│   └── contexto_ar.py
├── core/
│   ├── db.py                # SQLAlchemy + SQLite + seed
│   ├── data.py              # yfinance / dolarapi / criptoya / argentinadatos
│   ├── metrics.py           # Sharpe, Sortino, MaxDD, etc.
│   └── portfolio.py         # valuación, P&L, equity curve
├── data/                    # SQLite (gitignored)
├── .streamlit/config.toml   # tema dark
└── requirements.txt
```

## Roadmap

- **Bloque 2** — Rebalanceador con PyPortfolioOpt (frontera eficiente, risk parity, min variance), Monte Carlo, sugerencias de operación.
- **Bloque 3** — Módulo quant avanzado (factor exposure, PCA, correlaciones dinámicas, stress testing).
- **Bloque 4** — AI insights (alertas inteligentes, portfolio health score, oportunidades).
- **Bloque 5** — Migración a Postgres (Supabase) para persistencia en deploy.

## Licencia

MIT.
