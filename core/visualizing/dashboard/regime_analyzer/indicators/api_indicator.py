import pandas as pd
import requests

# 1) Daten von finhacker (manueller Export oder CSV-Download)
fh = pd.read_csv("finhacker_fng_2011_2017.csv", parse_dates=["date"])
fh = fh.rename(columns={"value": "fng_value"})

# 2) Daten von Alternative.me API (ab 2018)
url = "https://api.alternative.me/fng/?limit=0&format=csv&date_format=world"
r = requests.get(url)
with open("alt_fng.csv", "wb") as f:
    f.write(r.content)
alt = pd.read_csv("alt_fng.csv", parse_dates=["date"])
alt = alt.rename(columns={"value": "fng_value"})

# 3) Daten zusammenführen
df = pd.concat([fh, alt]).sort_values("date").reset_index(drop=True)

# 4) Beispiel: Plot
import matplotlib.pyplot as plt
plt.figure(figsize=(12,6))
plt.plot(df["date"], df["fng_value"], label="Fear & Greed Index")
plt.xlabel("Datum")
plt.ylabel("Index-Wert")
plt.title("Fear & Greed Index (2011–2025)")
plt.legend()
plt.show()
