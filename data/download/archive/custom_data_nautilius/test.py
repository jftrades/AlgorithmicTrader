import requests

url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
resp = requests.get(url).json()

symbol_target = "ALPACAUSDT"
matches = []

for s in resp["symbols"]:
    sym = s["symbol"]
    # direktes Match
    if sym == symbol_target:
        matches.append(s)
    # oder sym endet mit target: z. B. "1000PEPEUSDT"
    elif sym.endswith(symbol_target):
        matches.append(s)

print("Gefundene Symbole:", [m["symbol"] for m in matches])
for m in matches:
    print(m)
