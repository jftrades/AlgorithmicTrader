import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from arch import arch_model

class GARCH:
    def __init__(self, returns: pd.Series, window: int = 500):
        self.returns = returns.dropna()
        self.window = window
        self.model = None
        self.result = None

    def fit(self, p=1, q=1):
        if len(self.returns) > self.window:
            returns_window = self.returns.iloc[-self.window:]
        else:
            returns_window = self.returns
        self.model = arch_model(returns_window, vol='Garch', p=p, q=q)
        self.result = self.model.fit(disp='off')
        return self.result

    def plot_volatility(self):
        if self.result is None:
            raise ValueError("Modell muss zuerst gefittet werden.")
        plt.figure(figsize=(12, 5))
        plt.plot(self.result.conditional_volatility, label='GARCH Volatilität')
        plt.title('Geschätzte GARCH-Volatilität')
        plt.legend()
        plt.show()

    def forecast_volatility(self, steps=5):
        if self.result is None:
            raise ValueError("Modell muss zuerst gefittet werden.")
        forecast = self.result.forecast(horizon=steps)
        return np.sqrt(forecast.variance.iloc[-1])