# InvestIQ AlphaModel v1

This directory contains an isolated machine-learning laboratory to train the InvestIQ AlphaModel v1.

## What the model predicts
The model predicts the probability that a specific stock will outperform the NIFTY 50 benchmark over the next 20 trading days.

## Difference between Gemini and AlphaModel
Gemini is a Large Language Model (LLM) that generates narrative summaries and textual analysis based on news and fundamental data. 
AlphaModel is a statistical Machine Learning classification model (HistGradientBoostingClassifier) trained specifically on historical price and volume data to predict numerical probabilities of outperformance.

## Required CSV format
The model requires two CSV files in `data/raw/`:

1. `prices.csv` with columns: `date,security_id,symbol,close,volume`
2. `benchmark.csv` with columns: `date,close`

## Meaning of every feature
- **1-day return**: Percentage change in closing price since the previous day.
- **5-day return**: Percentage change over the last week.
- **20-day return**: Percentage change over the last month.
- **Close divided by 5/20/50-day moving average**: Indicates short, medium, and long-term momentum by comparing current price to historical averages.
- **20-day volatility**: Standard deviation of daily returns over the last 20 days, representing risk.
- **RSI 14**: Relative Strength Index, an oscillator measuring the speed and change of price movements.
- **20-day average volume**: The mean trading volume over the past month.
- **Current volume divided by 20-day average volume**: Spikes in volume can indicate significant market events or interest.
- **NIFTY 20-day return**: The market benchmark's performance over the last month.
- **Stock 20-day return minus NIFTY 20-day return**: The stock's historical outperformance relative to the broader market.

## How labels are created
We look 20 days into the future for both the stock and the benchmark. 
If `stock_future_return > benchmark_future_return`, the label is `1`. Otherwise, it is `0`.
Any rows at the end of the dataset that do not have 20 days of future data are removed to ensure we only train on known outcomes.

## Why chronological splitting is necessary
Financial data is a time series. Randomly shuffling data would allow the model to "see the future" while predicting the past. We strictly split by time: oldest 70% for training, next 15% for validation, and the newest 15% for testing.

## What data leakage means
Data leakage occurs when information from outside the training dataset is used to create the model. In finance, using future prices to calculate current features or using the test set to tune model parameters are common forms of leakage. Chronological splitting prevents this.

## How to train the model
```powershell
cd ml_training
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-ml.txt
python -m src.train --prices data/raw/prices.csv --benchmark data/raw/benchmark.csv
```
You can also run the bundled script:
`.\train_model.ps1`

## How to inspect evaluation results
After training, check `models/investiq_alphamodel_v1.metadata.json` and `reports/evaluation.json` for detailed metrics and metadata.

## Why accuracy alone is insufficient
A model predicting that no stock outperforms the market might achieve high accuracy if outperforming stocks are rare. Metrics like Precision, Recall, F1 Score, and ROC-AUC provide a comprehensive view of how well the model handles both classes.

## Why this model is not connected to the website yet
This is an isolated, experimental laboratory designed to establish a baseline model safely. Connecting an untested predictive model to a user-facing platform can mislead users and create reputational risk.

## How it could be integrated later through a provider interface
Later, we can create a standard provider interface (similar to how we interface with Gemini) in the backend. When a user requests research, the backend can query the AlphaModel (e.g., via a saved `.joblib` model or an internal API), returning the probability score which the frontend can render alongside the LLM analysis.
