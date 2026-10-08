# Livestock Trader

**CME-focused quantitative research platform for livestock futures and options.**

Livestock Trader is a Python-based quantitative research and visualization platform for futures and options markets, initially focused on **Lean Hogs, Live Cattle, and Feeder Cattle**.

The project combines derivatives positioning, volatility analytics, futures term-structure research, CFTC positioning, market-data collection, and interactive visualization in a single modular research environment.

> **Project status:** Active development  
> **Current portfolio scope:** CME livestock derivatives  
> **Long-term direction:** A broader CME quantitative research platform

---

## Overview

Livestock markets combine several characteristics that make them particularly interesting from a quantitative research perspective:

- multiple simultaneously traded futures expirations
- contract rolling and discontinuities between contracts
- options positioning across strikes and expirations
- changing implied volatility
- futures term structure
- seasonal behavior
- CFTC positioning
- exchange-specific settlement mechanics

Livestock Trader is designed to bring these different dimensions into one research system rather than treating them as isolated notebooks or scripts.

The architecture separates:

```text
DATA ACQUISITION
       ↓
NORMALIZATION
       ↓
STORAGE
       ↓
QUANTITATIVE ANALYTICS
       ↓
VISUALIZATION
```

This separation allows the analytical layer to evolve independently from individual data-delivery mechanisms.

---

# Key Features

## Gamma Exposure (GEX)

The project includes dedicated Gamma Exposure analytics across option strikes.

Current research capabilities include:

- Call and Put gamma exposure
- Net GEX by strike
- Gamma concentration zones
- Gamma walls
- Local gamma regime analysis
- Global gamma regime analysis
- Strike-level exposure profiles
- Dynamic GEX visualization
- Synchronized strike ranges

The objective is to transform the raw option chain into a market-structure representation that can be analyzed alongside the underlying futures 