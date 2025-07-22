import pandas as pd
import numpy as np
import quantstats as qs

dummy_returns = pd.Series(np.random.normal(0, 0.01, 100), index=pd.date_range("2020-01-01", periods=100))

qs.reports.html(
    dummy_returns,
    title="Dummy Strategy Tearsheet",
    output="dummy_report.html"
)