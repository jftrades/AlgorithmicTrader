# hier drinnen ist der gleiche Kalman Filter wie im anderen, 
# nur dass dieser für Entry/Exits in unserem Fall benutzt wird und dafür für die Exits einen ZScore hat

import numpy as np
from collections import deque

class KalmanFilterRegressionWithZScore:
    def __init__(
        self,
        process_var: float = 0.00001,
        measurement_var: float = 0.01,
        window: int = 10,
        zscore_window: int = 20,
        initial_state_mean: float = None,
        initial_state_covariance: float = 1.0,
    ):
        self.process_var = process_var
        self.measurement_var = measurement_var
        self.mean = initial_state_mean
        self.var = initial_state_covariance
        self.initialized = False if initial_state_mean is None else True
        self.window = []
        self.window_size = window
        self.buffer = deque(maxlen=window)  # Für Regression
        
        # Für Z-Score vom Kalman Mean (echte Distanz)
        self.zscore_window = zscore_window
        self.kalman_distance_history = deque(maxlen=zscore_window)
        self.current_kalman_mean = None

    def update(self, value: float):
        # Initialisierung
        if not self.initialized:
            self.window.append(value)
            if len(self.window) == self.window_size:
                self.mean = np.mean(self.window)
                self.initialized = True
            return self.mean if self.initialized else None, 0.0, None

        # Prediction
        pred_mean = self.mean
        pred_var = self.var + self.process_var

        # Update
        K = pred_var / (pred_var + self.measurement_var)
        self.mean = pred_mean + K * (value - pred_mean)
        self.var = (1 - K) * pred_var
        self.current_kalman_mean = self.mean

        # Buffer für Regression aktualisieren
        self.buffer.append(self.mean)
        
        # Slope per Regression berechnen
        if len(self.buffer) >= 2:
            y = np.array(self.buffer)
            x = np.arange(len(y))
            slope = np.polyfit(x, y, 1)[0]
        else:
            slope = 0.0

        # Z-Score berechnung - EINFACHE Distanz zum Kalman Mean in Standardabweichungen
        # Z-Score = 0 wenn Preis EXAKT auf Kalman Mean ist
        zscore = None
        if self.current_kalman_mean is not None:
            # Sammle die absoluten Distanzen für Standardabweichung (ohne Vorzeichen)
            abs_distance = abs(value - self.current_kalman_mean)
            self.kalman_distance_history.append(abs_distance)
            
            # Benötigen mindestens 5 Datenpunkte für Standardabweichung
            if len(self.kalman_distance_history) >= 5:
                # Berechne die durchschnittliche absolute Distanz (Standardabweichung der Distanzen)
                distance_std = np.std(list(self.kalman_distance_history), ddof=1)
                
                if distance_std > 0.0001:  # Vermeide Division durch Null
                    # EINFACHER Z-Score: Aktuelle Distanz / Standard-Distanz
                    # Positiv wenn über Mean, Negativ wenn unter Mean
                    current_distance = value - self.current_kalman_mean
                    zscore = current_distance / distance_std
                    
                    # Begrenze extreme Werte
                    zscore = np.clip(zscore, -80.0, 80.0)
                else:
                    zscore = 0.0

        return self.mean, slope, zscore

    def reset(self):
        self.mean = None
        self.var = 1.0
        self.initialized = False
        self.window = []
        self.buffer.clear()
        self.kalman_distance_history.clear()
        self.current_kalman_mean = None

    def is_initialized(self) -> bool:
        return self.initialized

    def get_state(self):
        return self.mean, self.var

    def get_regression_slope(self):
        if len(self.buffer) >= 2:
            y = np.array(self.buffer)
            x = np.arange(len(y))
            return np.polyfit(x, y, 1)[0]
        return 0.0