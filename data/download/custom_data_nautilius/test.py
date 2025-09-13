import websocket
import json

def on_message(ws, message):
    data = json.loads(message)
    print("\n📥 Raw JSON:")
    print(json.dumps(data, indent=2))  # schön formatiert

def on_error(ws, error):
    print("❌ Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("🔌 Connection closed")

def on_open(ws):
    params = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@depth10@100ms"],  # du kannst auch depth20 nehmen
        "id": 1
    }
    ws.send(json.dumps(params))

if __name__ == "__main__":
    url = "wss://fstream.binance.com/ws"
    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()
