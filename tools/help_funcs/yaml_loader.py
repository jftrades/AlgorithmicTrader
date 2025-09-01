# yaml_loader.py
import yaml
import os
import csv
from typing import List, Dict, Any, Tuple


def load_params(yaml_path: str) -> Dict[str, Any]:
    """
    Lädt YAML als Dict. Leere Dateien werden als {} behandelt.
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _expand_instruments_from_path_entries(params: Dict[str, Any], yaml_path: str) -> None:
    """
    Expands instruments from CSV definitions under 'instruments_from_path'.
    Accepts either a single mapping or a list of mappings.

    Each mapping supports:
      path: <str> (relative to YAML file or absolute)
      bar_type_endings: <str | List[str]>  (suffix(es) like "-15-MINUTE-LAST-EXTERNAL")
      symbol_column: <str> (default 'symbol')
      instrument_suffix: <str> (default '-PERP')
      venue: <str> (optional override; else global params['venue'])
      Any other key/value pairs are copied into each generated instrument (e.g. trade_size_usdt, test, etc.)

    Generates instrument dicts:
      instrument_id: <SYMBOL><instrument_suffix>.<VENUE>
      bar_types: [instrument_id + ending for ending in bar_type_endings]
      + passthrough custom keys.
    """
    entries = params.get("instruments_from_path")
    if not entries:
        return
    if isinstance(entries, dict):
        entries = [entries]

    base_dir = os.path.dirname(os.path.abspath(yaml_path))
    collected: List[Dict[str, Any]] = []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise TypeError(f"instruments_from_path[{idx}] muss ein Mapping sein.")
        rel_path = entry.get("path")
        if not rel_path:
            raise ValueError(f"instruments_from_path[{idx}] fehlt 'path'.")
        abs_path = rel_path if os.path.isabs(rel_path) else os.path.join(base_dir, rel_path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"CSV nicht gefunden: {abs_path}")

        venue = entry.get("venue") or params.get("venue")
        if not venue:
            raise ValueError(f"instruments_from_path[{idx}]: 'venue' weder lokal noch global angegeben.")

        symbol_col = entry.get("symbol_column", "symbol")
        instrument_suffix = entry.get("instrument_suffix", "-PERP")
        endings_raw = entry.get("bar_type_endings") or entry.get("bar_type_ending")
        if not endings_raw:
            raise ValueError(f"instruments_from_path[{idx}]: 'bar_type_endings' (oder 'bar_type_ending') erforderlich.")
        if isinstance(endings_raw, str):
            bar_type_endings = [endings_raw]
        elif isinstance(endings_raw, list):
            bar_type_endings = endings_raw
        else:
            raise TypeError(f"instruments_from_path[{idx}].bar_type_endings muss str oder List[str] sein.")

        # Keys to exclude from passthrough
        exclude = {
            "path",
            "symbol_column",
            "instrument_suffix",
            "bar_type_endings",
            "bar_type_ending",
            "venue",
        }
        passthrough = {k: v for k, v in entry.items() if k not in exclude}

        with open(abs_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if symbol_col not in reader.fieldnames:
                raise ValueError(
                    f"CSV '{abs_path}' hat keine Spalte '{symbol_col}'. Vorhanden: {reader.fieldnames}"
                )
            for row in reader:
                symbol = row.get(symbol_col)
                if not symbol:
                    continue
                instrument_id = f"{symbol}{instrument_suffix}.{venue}"
                bar_types = [f"{instrument_id}{ending}" for ending in bar_type_endings]
                inst: Dict[str, Any] = {
                    "instrument_id": instrument_id,
                    "bar_types": bar_types,
                }
                # Merge passthrough params
                inst.update(passthrough)
                collected.append(inst)

    existing = params.get("instruments") or []
    if not isinstance(existing, list):
        raise TypeError("'instruments' muss eine Liste sein, falls vorhanden.")
    # Append generated instruments
    params["instruments"] = existing + collected


def _normalize_instruments(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Erwartet params["instruments"] als Liste von Dicts.

    Normalisiert JEDE Instrument-Definition so, dass mindestens folgende Felder
    garantiert vorhanden sind:

      - instrument_id: <str>             (PFLICHT)
      - bar_types: List[str]             (PFLICHT; mindestens 1 Element)
      - trade_size_usdt: <Any>           (optional; fällt auf globalen Wert zurück, wenn vorhanden)

    Unterstützte Eingaben je Instrument:
      - bar_type: "<...>"                          # einzelner String
      - bar_types: ["<...>", "<...>"]              # Liste von Strings
      - bar_types: [{"bar_type":"<...>"}, ...]     # Liste von Dicts mit Schlüssel "bar_type"

    Alle weiteren (benutzerdefinierten) Felder werden unverändert übernommen
    (z. B. paramXY, paramAB, ...).

    Fehlerfälle:
      - Fehlender Schlüssel 'instruments'
      - 'instruments' ist nicht Liste
      - Eintrag ist kein Mapping
      - instrument_id fehlt/ist nicht str
      - bar_type/bar_types fehlen oder ergeben nach Normalisierung leere Liste
      - bar_types-Elemente haben unbekanntes Format
    """
    if "instruments" not in params or params["instruments"] is None:
        raise KeyError("YAML fehlt Schlüssel 'instruments'. Bitte in der YAML 'instruments' spezifizieren.")

    raw_list = params["instruments"]
    if not isinstance(raw_list, list):
        raise TypeError("'instruments' muss eine Liste sein.")

    global_size = params.get("trade_size_usdt", None)

    normalized: List[Dict[str, Any]] = []
    for i, item in enumerate(raw_list):
        if not isinstance(item, dict):
            raise TypeError(f"instruments[{i}] muss ein Mapping (dict) sein, erhalten: {type(item)}")

        # --- instrument_id prüfen ---
        instr_id = item.get("instrument_id")
        if not instr_id or not isinstance(instr_id, str):
            raise ValueError(
                f"instruments[{i}]: 'instrument_id' fehlt oder ist kein String. "
                f"Bitte in der YAML angeben: instrument_id: \"<YOUR_ID>\""
            )

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
                        raise ValueError(
                            f"instruments[{i}].bar_types[{j}] hat unbekanntes Format: {e!r}. "
                            f"Erlaubt sind Strings oder Dicts mit Schlüssel 'bar_type'."
                        )
            else:
                raise TypeError(f"instruments[{i}].'bar_types' muss eine Liste sein.")
        elif "bar_type" in item and item["bar_type"] is not None:
            if isinstance(item["bar_type"], str):
                bar_types.append(item["bar_type"])
            else:
                raise TypeError(f"instruments[{i}].'bar_type' muss ein String sein.")
        else:
            raise ValueError(
                f"instruments[{i}]: Es muss mindestens ein 'bar_type' oder 'bar_types' angegeben sein. "
                f"Bitte in der YAML spezifizieren."
            )

        # Nach-Normalisierung: leere Liste verbieten
        if not bar_types:
            raise ValueError(f"instruments[{i}]: 'bar_types' ist leer nach Normalisierung. Bitte in der YAML prüfen.")

        # Duplikate stabil entfernen
        seen_bt = set()
        bar_types_dedup = []
        for bt in bar_types:
            if bt not in seen_bt:
                seen_bt.add(bt)
                bar_types_dedup.append(bt)

        # --- trade_size_usdt mit Fallback auf globalen Wert (falls vorhanden) ---
        trade_size = item.get("trade_size_usdt", global_size)

        # --- Alle benutzerdefinierten Felder übernehmen ---
        out: Dict[str, Any] = dict(item)              # flache Kopie
        out["instrument_id"] = instr_id
        out["bar_types"] = bar_types_dedup
        if trade_size is not None:
            out["trade_size_usdt"] = trade_size
        if "bar_type" in out:                          # Einzel-Schlüssel entfernen (nun vereinheitlicht)
            del out["bar_type"]
        normalized.append(out)

    return normalized


def load_and_split_params(yaml_path: str) -> Tuple[
    Dict[str, Any],                # params (inkl. normalisiertem 'instruments')
    Dict[str, List[Any]],          # param_grid
    List[str],                     # keys
    List[List[Any]],               # values
    Dict[str, Any],                # static_params
    List[str],                     # all_instrument_ids
    List[str],                     # all_bar_types
]:
    """
    Lädt YAML, expandiert instruments_from_path, normalisiert instruments
    und splittet restliche Parameter in Grid- und Static-Teile.
    """
    params = load_params(yaml_path)

    # CSV-basierte Instrumente zuerst hinzufügen (falls definiert)
    _expand_instruments_from_path_entries(params, yaml_path)

    # instruments normalisieren
    instruments_normalized = _normalize_instruments(params)
    params["instruments"] = instruments_normalized

    # param_grid bestimmen (nur Keys mit Liste Länge >1, exkl. instruments)
    param_grid: Dict[str, List[Any]] = {}
    for k, v in params.items():
        if k == "instruments":
            continue
        if isinstance(v, list) and len(v) > 1:
            param_grid[k] = v

    # static_params (inkl. Reduktion von Single-Listen)
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

    # keys / values für Grid
    if param_grid:
        keys, values = zip(*param_grid.items())
        keys, values = list(keys), list(values)
    else:
        keys, values = [], []

    # Aggregation Instrument-IDs & BarTypes (stabil, duplikatfrei)
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

    return (
        params,
        param_grid,
        keys,
        values,
        static_params,
        all_instrument_ids,
        all_bar_types,
    )
