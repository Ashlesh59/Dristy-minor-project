import pandas as pd
import numpy as np

def run_backtest(test_df, model, feature_cols, transaction_cost=0.001):
    report = {
        "status": "NOT RUN",
        "reason": "",
        "metrics": {}
    }
    
    if test_df.empty:
        report["reason"] = "Test dataset is empty."
        return report
        
    dates = np.sort(test_df["date"].unique())
    if len(dates) < 2:
        report["reason"] = "Not enough dates in test set for a backtest."
        return report
        
    preds = model.predict_proba(test_df[feature_cols])[:, 1]
    
    backtest_df = test_df[["date", "security_id", "stock_future_return", "benchmark_future_return"]].copy()
    backtest_df["prob_1"] = preds
    
    # Simple strategy: Every day, pick the top 5 stocks with highest probability > 0.6
    # Calculate their average future return, compare to benchmark.
    
    daily_results = []
    
    for d in dates:
        day_data = backtest_df[backtest_df["date"] == d]
        bench_ret = day_data["benchmark_future_return"].iloc[0] if not day_data.empty else np.nan
        
        candidates = day_data[day_data["prob_1"] > 0.55].sort_values("prob_1", ascending=False).head(5)
        
        if candidates.empty:
            continue
            
        avg_stock_ret = candidates["stock_future_return"].mean()
        # Gross return
        gross_excess = avg_stock_ret - bench_ret
        # Net return (assuming buy and sell costs)
        net_stock_ret = avg_stock_ret - (2 * transaction_cost)
        net_excess = net_stock_ret - bench_ret
        
        daily_results.append({
            "date": d,
            "num_stocks": len(candidates),
            "gross_excess": gross_excess,
            "net_excess": net_excess,
            "win": 1 if net_excess > 0 else 0
        })
        
    if not daily_results:
        report["reason"] = "No days had confident predictions to trade."
        return report
        
    results_df = pd.DataFrame(daily_results)
    
    report["status"] = "SUCCESS"
    report["reason"] = "Experimental historical simulation, not evidence of future profitability"
    report["metrics"] = {
        "prediction_periods": int(len(results_df)),
        "average_gross_excess_return": float(results_df["gross_excess"].mean()),
        "average_net_excess_return": float(results_df["net_excess"].mean()),
        "win_rate": float(results_df["win"].mean()),
        "transaction_cost_assumption": float(transaction_cost)
    }
    
    return report
