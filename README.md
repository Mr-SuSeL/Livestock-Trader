# Livestock Trader

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Market](https://img.shields.io/badge/Market-CME-00529B)](https://www.cmegroup.com/)
[![Research](https://img.shields.io/badge/Research-Quantitative-6f42c1)](#)
[![Asset Class](https://img.shields.io/badge/Asset-Futures%20%26%20Options-a44f00)](#)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange)](#)

**CME-focused quantitative research platform for livestock futures and options.**

Livestock Trader is a Python-based quantitative research and visualization platform for futures and options markets, initially focused on **Lean Hogs, Live Cattle, and Feeder Cattle**.

The project combines derivatives positioning, volatility analytics, futures term-structure research, CFTC positioning, market-data collection, and interactive visualization in a single modular research environment.

> **Project status:** Active development  
> **Current portfolio scope:** CME livestock derivatives  
> **Long-term direction:** A broader CME quantitative research platform

---

## Overview

Livestock markets combine several characteristics that make them particularly interesting from a quantitative research perspective:

- Multiple simultaneously traded futures expirations
- Contract rolling and discontinuities between contracts
- Options positioning across strikes and expirations
- Changing implied volatility
- Futures term structure
- Seasonal behavior
- CFTC positioning
- Exchange-specific settlement mechanics

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

The objective is to transform the raw option chain into a market-structure representation that can be analyzed alongside the underlying futures market.

---

## Vanna Exposure (VEX)

Livestock Trader also includes a dedicated Vanna Exposure layer.

Features include:

- Call VEX
- Put VEX
- Net VEX by strike
- Vanna walls
- Local exposure structure
- Synchronized GEX and VEX visualization

GEX and VEX charts share compatible strike ranges and visualization behavior, allowing both exposure profiles to be compared over the same region of the option surface.

```text
                  OPTION CHAIN
                       │
             ┌─────────┴─────────┐
             │                   │
            GEX                 VEX
             │                   │
             ▼                   ▼
      Gamma Structure     Vanna Structure
             │                   │
             └─────────┬─────────┘
                       │
                       ▼
                MARKET STRUCTURE
```

---

## Expected Move & Volatility

The project contains options-derived volatility analytics intended to study the relationship between implied volatility and the underlying futures market.

Research components include:

- Expected Move
- Implied Volatility
- Volatility structure
- Volatility nodes
- Positioning around the underlying futures price

This layer is intended to evolve into broader multi-timeframe volatility research.

---

## Futures Curve Analysis

Dedicated futures-curve analytics examine the relationship between simultaneously traded contract months.

The futures-curve layer includes research around:

- Individual futures contracts
- Front and deferred contracts
- Contract ordering
- Calendar spreads
- Spread percentages
- Relative contract prices
- Volume and activity
- Curve highs and lows

Conceptually:

```text
Front Month
    │
    ├──── Contract 2
    │        │
    ├────────┴──── Contract 3
    │                 │
    └─────────────────┴──── ... deferred contracts

                FUTURES CURVE
```

This architecture will also support future research into contract rolls and price discontinuities.

---

## CFTC Positioning

The project includes a CFTC positioning layer intended to combine derivatives-market structure with trader positioning.

The long-term objective is to evaluate relationships between:

```text
Futures Price
      +
Futures Curve
      +
Options Positioning
      +
Implied Volatility
      +
CFTC Positioning
```

rather than analyzing each dataset independently.

---

# Interactive Dashboard

Livestock Trader includes an interactive research dashboard built with **NiceGUI** and visualization components based on **Plotly**.

Current dashboard development includes:

- Multi-market navigation
- Futures-curve visualization
- GEX profiles
- VEX profiles
- Synchronized exposure profiles
- Dynamic GEX zones
- Volatility information
- Options-derived market structure

The dashboard acts as the presentation layer over the collectors, models, storage layer, and quantitative analytics.

---

## Dashboard Preview

```text
┌─────────────────────────────────────────────────────┐
│                 LIVESTOCK TRADER                    │
├─────────────────────────────────────────────────────┤
│                                                     │
│   Market Overview           Futures Curve           │
│                                                     │
├──────────────────────────┬──────────────────────────┤
│                          │                          │
│       GEX PROFILE        │       VEX PROFILE        │
│                          │                          │
├──────────────────────────┴──────────────────────────┤
│         VOLATILITY / POSITIONING RESEARCH           │
└─────────────────────────────────────────────────────┘
```

> A real dashboard screenshot or animated preview will replace this schematic as the interface evolves.

---

# Market Coverage

The current portfolio version focuses on CME livestock futures and options:

| Market | Futures Code |
| --- | ---: |
| Lean Hogs | HE |
| Live Cattle | LE |
| Feeder Cattle | GF |

These instruments define the current **portfolio scope**, not the architectural limit of the project.

A core design requirement is to avoid embedding HE/LE/GF-specific assumptions into components that should be reusable across CME markets.

The long-term architecture is intended to support additional CME instruments through configuration rather than instrument-specific forks of the analytical engine.

---

# CME-First Data Architecture

A fundamental design principle of Livestock Trader is **data provenance**.

## CME as Source of Truth

CME is intended to become the authoritative source for exchange market data used by the platform.

The project already contains CME-oriented options collection and parsing logic.

The futures-data layer is currently undergoing migration from legacy research/fallback infrastructure toward a generic CME-first architecture.

The intended architecture is:

```text
                         CME
                          │
          ┌───────────────┼───────────────┐
          │               │               │
     FUTURES EOD       OPTIONS       MARKET DATA
          │               │               │
          └───────────────┼───────────────┘
                          │
                          ▼
                     TRANSPORT
                          │
                          ▼
                     COLLECTORS
                          │
                          ▼
                  NORMALIZATION
                          │
                          ▼
                       STORAGE
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
            GEX          VEX      FUTURES CURVE
             │            │            │
             └────────────┼────────────┘
                          │
                          ▼
                  RESEARCH DASHBOARD
```

Provider-specific transport and parsing are deliberately separated from financial analytics.

The analytical layer operates on normalized internal representations instead of knowing how or where raw data was obtained.

---

# Data Provenance Philosophy

For quantitative market research, knowing the origin and meaning of a price is as important as knowing its numerical value.

Livestock Trader explicitly distinguishes between fields such as:

```text
Open
High
Low
Close
Settlement
Volume
Open Interest
```

rather than treating every available price field as interchangeable.

This becomes particularly important when combining futures prices with options analytics.

The project is moving toward:

```text
OFFICIAL EXCHANGE DATA
          │
          ▼
 EXPLICIT PROVENANCE
          │
          ▼
  VALIDATED SCHEMA
          │
          ▼
      ANALYTICS
```

instead of allowing fallback-provider semantics to propagate into quantitative calculations.

---

# Quick Start

## 1. Clone the Repository

```bash
git clone https://github.com/Mr-SuSeL/Livestock-Trader.git
cd Livestock-Trader
```

## 2. Create a Virtual Environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks script execution for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Run the Application

```bash
python main.py
```

## 5. Run the Test Suite

```bash
pytest -q
```

---

# Project Structure

```text
Livestock-Trader