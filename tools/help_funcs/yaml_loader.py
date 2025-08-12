import yaml
from typing import List, Dict, Any, Tuple

def load_params(yaml_path: str) -> Dict[str, Any]:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _normalize_instruments(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Erwartet params["instruments"] als Liste von Dicts.
    Normalisiert jedes Instrument in Form:
      {
        "instrument_id": <str>,
        "bar_types": List[str],
        "trade_size_usdt": <float|int|str>  # unverändert bis auf Fallback
      }
    Unterstützt folgende Eingaben je Instrument:
      - bar_type: "<...>"                          # einzelner String
      - bar_types: ["<...>", "<...>"]              # Liste von Strings
      - bar_types: [{"bar_type":"<...>"}, ...]     # Liste von Dicts
    """
    if "instruments" not in params or params["instruments"] is None:
        raise KeyError("YAML fehlt Schlüssel 'instruments'. Bitte Konfiguration prüfen.")
    raw_list = params["instruments"]
    if not isinstance(raw_list, list):
        raise TypeError("'instruments' muss eine Liste sein.")

    global_size = params.get("trade_size_usdt", None)

    normalized: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise TypeError(f"instruments[{i}] muss ein Mapping sein, erhalten: {type(item)}")

        instr_id = item.get("instrument_id")
        if not instr_id or not isinstance(instr_id, str):
            raise ValueError(f"instruments[{i}]: 'instrument_id' fehlt oder ist kein String.")

        # --- bar_types normalisieren ---
        bar_types: List[str] = []
        if "bar_types" in item and item["bar_types"] is not None:
            bt = item["bar_types"]
            if isinstance(bt, list):
                for j, e in enumerate(bt):
                    if isinstance(e, str):
                        bar_types.append(e)
                    elif isinstance(e, dict) and "bar_type" in e and isinstance(e["bar_type"], str):
                        bar_types.append(e["bar_type"])
                    else:
                        raise ValueError(f"instruments[{i}].bar_types[{j}] hat unbekanntes Format: {e!r}")
            else:
                raise TypeError(f"instruments[{i}].bar_types muss eine Liste sein.")
        elif "bar_type" in item and item["bar_type"] is not None:
            if isinstance(item["bar_type"], str):
                bar_types.append(item["bar_type"])
            else:
                raise TypeError(f"instruments[{i}].bar_type muss ein String sein.")
        else:
            raise ValueError(f"instruments[{i}]: Es muss 'bar_type' oder 'bar_types' angegeben sein.")

        if not bar_types:
            raise ValueError(f"instruments[{i}]: 'bar_types' ist leer nach Normalisierung.")

        # --- trade_size_usdt mit Fallback auf globalen Wert ---
        trade_size = item.get("trade_size_usdt", global_size)

        normalized.append({
            "instrument_id": instr_id,
            "bar_types": bar_types,
            "trade_size_usdt": trade_size,
        })

    return normalized

def load_and_split_params(yaml_path: str) -> Tuple[
    Dict[str, Any], Dict[str, List[Any]], List[str], List[List[Any]], Dict[str, Any], List[str], List[str]
]:
    """
    Rückgabe:
      - params:            Original-Params mit normalisiertem 'instruments'
      - param_grid:        {key: list_of_values} nur für Keys mit Listenlänge > 1 (exkl. 'instruments')
      - keys:              Liste der Grid-Keys (Reihenfolge deterministisch nach Einfüge-Reihenfolge)
      - values:            Liste der Wertelisten (gleiche Reihenfolge wie keys)
      - static_params:     Alle übrigen Parameter (inkl. 'instruments' normalisiert), dabei
                           Single-Element-Listen zu Skalaren reduziert.
      - all_instrument_ids: Liste aller instrument_id (duplikatfrei in Reihenfolge des Auftretens)
      - all_bar_types:      Liste aller bar_type Strings (duplikatfrei)
    """
    params = load_params(yaml_path)

    # 1) instruments normalisieren
    instruments_normalized = _normalize_instruments(params)
    params["instruments"] = instruments_normalized  # optional: Original-Objekt direkt anreichen

    # 2) param_grid: nur Keys mit Listen-Länge > 1 (exkl. 'instruments')
    param_grid: Dict[str, List[Any]] = {}
    for k, v in params.items():
        if k == "instruments":
            continue
        if isinstance(v, list) and len(v) > 1:
            param_grid[k] = v

    # 3) static_params: alle Keys, die nicht im Grid sind.
    #    Zusätzlich: Single-Element-Listen in Skalare verwandeln, außer 'instruments'
    static_params: Dict[str, Any] = {}
    for k, v in params.items():
        if k in param_grid:
            continue
        if k == "instruments":
            static_params[k] = instruments_normalized
        else:
            if isinstance(v, list) and len(v) == 1:
                static_params[k] = v[0]
            else:
                static_params[k] = v

    # 4) keys/values für das Grid
    if param_grid:
        keys, values = zip(*param_grid.items())
        keys, values = list(keys), list(values)
    else:
        keys, values = [], []

    # 5) Aggregationen für IDs und BarTypes (duplikatfrei, stabil)
    seen_ids, all_instrument_ids = set(), []
    seen_bt, all_bar_types = set(), []
    for instr in instruments_normalized:
        iid = instr.get("instrument_id")
        if isinstance(iid, str) and iid not in seen_ids:
            seen_ids.add(iid)
            all_instrument_ids.append(iid)
        for bt in instr.get("bar_types", []) or []:
            if isinstance(bt, str) and bt not in seen_bt:
                seen_bt.add(bt)
                all_bar_types.append(bt)

    return params, param_grid, keys, values, static_params, all_instrument_ids, all_bar_types
