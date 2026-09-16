# Autonomous Overnight Build — InvestIQ AlphaModel v1

This document explains the autonomous work completed to set up the InvestIQ AlphaModel v1 training pipeline.

## What was built
An isolated machine learning laboratory was created inside the `ml_training` directory. It safely prepares data, builds financial features, and trains a predictive model to identify stocks likely to outperform the NIFTY 50 over a 20-trading-day horizon. Crucially, the entire pipeline operates without modifying the existing website, backend, or database.

## Changed Files
The main repository files were left entirely untouched to guarantee safety. All new files were contained within `ml_training/`:
- `src/build_features.py`: Added safe, forward-looking financial features (Moving averages, RSI, Volatility, relative returns) and removed unsafe infinite values.
- `src/build_labels.py`: Created the binary target (1 if stock outperforms NIFTY 50 over the next 20 days, else 0).
- `src/train.py`: The core orchestrator. Splits data chronologically, selects between Dummy, Logistic Regression, and HistGradientBoosting classifiers based on validation metrics, and evaluates the final choice on a held-out test set. Also runs the simple backtest simulation.
- `src/evaluate.py`: Calculates classification metrics and enforces a strict baseline derived only from training data.
- `src/predict.py`: A robust CLI prediction tool that strictly validates feature names, order, and values, returning JSON.
- `src/export_from_db.py`: Read-only database exporter to safely pull data into a CSV format.
- `src/prepare_benchmark.py`: Cleans and formats the NIFTY 50 CSV.
- `src/audit_dataset.py`: A comprehensive diagnostic script ensuring the dataset is healthy, complete, and unbiased before training starts.
- `src/backtest.py`: A module to simulate daily trading based on predictions in the test set, subtracting transaction costs.
- `train_model.ps1`, `test_model.ps1`, `export_training_data.ps1`, `audit_training_data.ps1`: Automation wrappers for Windows PowerShell.

## How Features and Labels Work
- **Features** are calculated purely from historical data up to the current date. For example, a 50-day moving average only uses the current close and the 49 preceding closes. We enforce this strictly to avoid looking into the future.
- **Labels** look 20 trading days into the future. We calculate the stock's return 20 days later and the benchmark's return 20 days later. If the stock wins, the label is 1. If not, it is 0.

## What is Data Leakage?
Data leakage occurs when information from the future accidentally "leaks" into the past during model training. This causes the model to appear highly accurate in testing but fail completely in real life. We prevent this by never backfilling data and never shuffling chronological data.

## Why the Purge Window is Required
When we divide our dataset into Training, Validation, and Testing, we must ensure they don't overlap. Since our label looks 20 days into the future, a stock record on the last day of the Training set contains information about the next 20 days. If the Validation set starts immediately the next day, it would share 19 overlapping days of "future" market reality with the Training set. The 20-day purge (or embargo) window forces a gap of 20 trading days between datasets, ensuring complete independence.

## How Chronological Splitting Works
Instead of randomly picking 80% of rows for training (which destroys the arrow of time), we sort all data by date. The oldest chunk becomes Training. The next chunk becomes Validation. The newest chunk becomes Testing.

## How Model Selection Works
We train several models (a simple Baseline, Logistic Regression, and a Gradient Booster) on the Training set. We then test their performance on the Validation set (using a metric called ROC-AUC). We pick the one that scores best on Validation. Finally, we evaluate that chosen model exactly once on the Testing set to see how it performs on completely unseen data.

## Difference between Gemini and AlphaModel
Gemini is a Large Language Model (LLM) connected to the internet. It reads news, digests text, and explains financial concepts using natural language. 
AlphaModel is a supervised classification algorithm. It has no internet access, no understanding of language, and only looks at pure historical numbers (prices and volumes) to predict a binary mathematical outcome. They serve entirely different purposes.

## Did Genuine Training Happen?
No. The system accurately recognized that the required genuine historical data (`prices.csv` and `benchmark.csv`) was missing. It gracefully aborted the training process and reported `MODEL NOT TRAINED` rather than faking a result or exposing the system to external scraping risks.

## Exact Metrics
(Not applicable since genuine training did not occur).

## Why the Model is Still Not Connected
To strictly enforce the safety barrier, AlphaModel is isolated. Connecting it to the live website right now would risk breaking the functional Phase 2 MVP. Integration is a distinct engineering phase that should only happen after a model is fully trained, evaluated, and deemed safe to present.

## Remaining Limitations and Risks
- The model relies purely on technical price patterns; it cannot perceive real-world news, earnings reports, or fundamental shifts.
- If unadjusted data is exported, the model will mistake artificial stock splits for massive price crashes, completely destroying its accuracy.

## Next Commands for the Owner
1. Review the data readiness: `.\audit_training_data.ps1` (after providing CSVs or exporting from the DB).
2. Prepare the dataset: `.\export_training_data.ps1`
3. Execute the pipeline: `.\train_model.ps1`

---
## Self-Check Questions for the Owner
1. Why do we drop 20 days of data between the Training and Validation sets?
2. Why is random shuffling extremely dangerous for financial machine learning?
3. What is the fundamental difference between what Gemini does and what AlphaModel does?
4. If a stock undergoes a 2-for-1 split and the database contains unadjusted prices, what will the 1-day return look like to the model?
5. Why must the baseline metrics be calculated using only the Training set?
