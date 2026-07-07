"""Resolve user ticker input to yfinance symbols (US + Euronext Amsterdam)."""

from __future__ import annotations

# Euronext Amsterdam (.AS) — AEX & common Dutch listings
NL_SYMBOL_MAP: dict[str, str] = {
    "ASML": "ASML.AS",
    "ING": "INGA.AS",
    "INGA": "INGA.AS",
    "PHIA": "PHIA.AS",
    "PHILIPS": "PHIA.AS",
    "ADYEN": "ADYEN.AS",
    "AD": "ADYEN.AS",
    "HEIA": "HEIA.AS",
    "HEINEKEN": "HEIA.AS",
    "PRX": "PRX.AS",
    "PROSUS": "PRX.AS",
    "WKL": "WKL.AS",
    "UNA": "UNA.AS",
    "UNILEVER": "UNA.AS",
    "KPN": "KPN.AS",
    "ABN": "ABN.AS",
    "ABNAMRO": "ABN.AS",
    "AKZA": "AKZA.AS",
    "IMCD": "IMCD.AS",
    "EXO": "EXO.AS",
    "ASRNL": "ASRNL.AS",
    "NN": "NN.AS",
    "RAND": "RAND.AS",
    "BESI": "BESI.AS",
    "ASM": "ASM.AS",
    "AALB": "AALB.AS",
    "REL": "REL.AS",
    "SHELL": "SHELL.AS",
    "DSM": "DSFIR.AS",
    "DSFIR": "DSFIR.AS",
    "SBMO": "SBMO.AS",
    "LIGHT": "LIGHT.AS",
    "SIGN": "SIGN.AS",
    "MT": "MT.AS",
    "ARCADIS": "ARCAD.AS",
    "ARCAD": "ARCAD.AS",
    "JDE": "JDEP.AS",
    "JDEP": "JDEP.AS",
    "FLOW": "FLOW.AS",
    "GLPG": "GLPG.AS",
    "OCI": "OCI.AS",
    "CTPNV": "CTPNV.AS",
    "TKWY": "TKWY.AS",
    "JUSTEAT": "TKWY.AS",
}


def resolve_ticker(raw: str) -> dict:
    """Return yfinance symbol, market, currency, and cache/display labels."""
    t = (raw or "").upper().strip().replace(" ", "")

    if not t:
        return {"symbol": "", "market": "US", "currency": "USD", "input": t, "cache_id": ""}

    if t.endswith(".AS"):
        return {
            "symbol": t,
            "market": "NL",
            "currency": "EUR",
            "input": t,
            "cache_id": t,
        }

    if t in NL_SYMBOL_MAP:
        sym = NL_SYMBOL_MAP[t]
        return {
            "symbol": sym,
            "market": "NL",
            "currency": "EUR",
            "input": t,
            "cache_id": sym,
        }

    return {
        "symbol": t,
        "market": "US",
        "currency": "USD",
        "input": t,
        "cache_id": t,
    }
