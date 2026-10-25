"""Generate eval/queries_e26.yaml once (2026-10-25), before any E26 pick or purchase. Kept for provenance; never re-run after freezing.

Needs come from fixed lists written here, not from the catalogue, so the set is not shaped by what is for sale.
Every need has a code oracle against a free public source (family + params), graded by plumb.evaluation.grader v3.
"""
import json
import urllib.request

import yaml

COINS = [("BTC", "bitcoin"), ("BNB", "binancecoin"), ("ADA", "cardano"), ("DOGE", "dogecoin"), ("AVAX", "avalanche-2"),
         ("DOT", "polkadot"), ("LINK", "chainlink"), ("LTC", "litecoin"), ("TRX", "tron"), ("XLM", "stellar"),
         ("ATOM", "cosmos"), ("NEAR", "near"), ("UNI", "uniswap"), ("BCH", "bitcoin-cash"), ("ETC", "ethereum-classic"),
         ("FIL", "filecoin"), ("APT", "aptos"), ("ARB", "arbitrum"), ("OP", "optimism"), ("SUI", "sui"),
         ("TON", "the-open-network"), ("SHIB", "shiba-inu"), ("HBAR", "hedera-hashgraph"), ("ICP", "internet-computer"), ("AAVE", "aave")]
EUR_COINS = [("BTC", "bitcoin"), ("ETH", "ethereum"), ("XRP", "ripple"), ("SOL", "solana"), ("ADA", "cardano"),
             ("DOGE", "dogecoin"), ("LTC", "litecoin"), ("DOT", "polkadot"), ("LINK", "chainlink"), ("BNB", "binancecoin")]
FX = [("USD", "JPY"), ("EUR", "GBP"), ("USD", "CHF"), ("CAD", "USD"), ("AUD", "USD"), ("USD", "CNY"), ("USD", "INR"),
      ("EUR", "CHF"), ("GBP", "EUR"), ("USD", "MXN"), ("USD", "BRL"), ("NZD", "USD"), ("USD", "SEK"), ("USD", "NOK"),
      ("USD", "KRW"), ("EUR", "JPY"), ("USD", "SGD"), ("USD", "HKD"), ("EUR", "PLN"), ("USD", "ZAR"), ("USD", "TRY"),
      ("EUR", "CZK"), ("USD", "DKK"), ("GBP", "JPY"), ("CHF", "EUR")]
CITIES = [("Los Angeles", "KLAX", 34.0522, -118.2437), ("Seattle", "KSEA", 47.6062, -122.3321), ("Denver", "KDEN", 39.7392, -104.9903),
          ("Miami", "KMIA", 25.7617, -80.1918), ("Boston", "KBOS", 42.3601, -71.0589), ("Atlanta", "KATL", 33.749, -84.388),
          ("Phoenix", "KPHX", 33.4484, -112.074), ("Dallas", "KDFW", 32.7767, -96.797), ("Houston", "KIAH", 29.7604, -95.3698),
          ("San Francisco", "KSFO", 37.7749, -122.4194), ("Minneapolis", "KMSP", 44.9778, -93.265), ("Detroit", "KDTW", 42.3314, -83.0458),
          ("Philadelphia", "KPHL", 39.9526, -75.1652), ("Las Vegas", "KLAS", 36.1699, -115.1398), ("Washington, DC", "KDCA", 38.9072, -77.0369)]
# tolerance = about 120 s of blocks at each chain's block time
CHAINS = [("Polygon", "https://polygon-bor.publicnode.com", 60), ("BNB Smart Chain", "https://bsc-dataseed.bnbchain.org", 300),
          ("Arbitrum One", "https://arbitrum-one-rpc.publicnode.com", 500), ("Base", "https://base-rpc.publicnode.com", 60),
          ("Optimism", "https://optimism-rpc.publicnode.com", 60), ("Avalanche C-Chain", "https://avalanche-c-chain-rpc.publicnode.com", 70),
          ("Gnosis Chain", "https://gnosis-rpc.publicnode.com", 25), ("Linea", "https://linea-rpc.publicnode.com", 60),
          ("Scroll", "https://scroll-rpc.publicnode.com", 40), ("XRP Ledger", "xrpl", 35)]
COUNTRIES = [("Germany", "DE"), ("United Kingdom", "GB"), ("France", "FR"), ("Japan", "JP"), ("Canada", "CA"), ("Australia", "AU"),
             ("Brazil", "BR"), ("Italy", "IT"), ("Spain", "ES"), ("Netherlands", "NL"), ("Mexico", "MX"), ("South Korea", "KR"),
             ("New Zealand", "NZ"), ("Sweden", "SE"), ("Switzerland", "CH")]
FIRST_DAY = "2026-10-26"


def holiday(cc):
    """The first nationwide public holiday on or after FIRST_DAY (nager.date), fixed into the YAML at generation time."""
    with urllib.request.urlopen(f"https://date.nager.at/api/v3/PublicHolidays/2026/{cc}", timeout=20) as r:
        hs = json.load(r)
    return next(h for h in hs if h["date"] >= FIRST_DAY and h.get("global"))


def main():
    q = []
    for t, cg in COINS:
        q.append({"family": "crypto_usd", "need": f"Current {t} price in USD", "inputs": {"asset": t, "quote": "USD"},
                  "must_include": [f"{t} price in USD, as a number"], "freshness": "15m",
                  "oracle": {"kind": "price", "coin": cg, "vs": "usd", "tol": 0.02}})
    for t, cg in EUR_COINS:
        q.append({"family": "crypto_eur", "need": f"Current {t} price in EUR", "inputs": {"asset": t, "quote": "EUR"},
                  "must_include": [f"{t} price in EUR, as a number"], "freshness": "15m",
                  "oracle": {"kind": "price", "coin": cg, "vs": "eur", "tol": 0.02}})
    for a, b in FX:
        q.append({"family": "fx", "need": f"Convert 100 {a} to {b} at the latest exchange rate", "inputs": {"amount": "100", "from": a, "to": b},
                  "must_include": [f"{a} to {b} exchange rate"], "freshness": "3d",
                  "oracle": {"kind": "fx", "from": a, "to": b, "amount": 100, "tol": 0.01}})
    for city, st, lat, lon in CITIES:
        q.append({"family": "weather", "need": f"Current weather in {city}", "inputs": {"location": city, "lat": str(lat), "lon": str(lon)},
                  "must_include": ["current temperature", "current conditions"], "freshness": "3h",
                  "oracle": {"kind": "weather", "station": st, "tol_c": 4}})
    for name, rpc, tol in CHAINS:
        q.append({"family": "block", "need": f"Latest block number on {name}", "inputs": {"chain": name},
                  "must_include": ["latest block number"], "freshness": "10m",
                  "oracle": {"kind": "block", "rpc": rpc, "tol": tol}})
    for country, cc in COUNTRIES:
        h = holiday(cc)
        q.append({"family": "holiday", "need": f"Is {h['date']} a public holiday in {country}? If so, name it", "inputs": {"date": h["date"], "country": cc},
                  "must_include": [f"whether {h['date']} is a public holiday in {country}", "its name"], "freshness": "n/a",
                  "oracle": {"kind": "holiday", "date": h["date"], "names": sorted({h["name"], h["localName"]})}})
    for i, x in enumerate(q, 1):
        x["id"] = f"f{i:03d}"
    doc = {"version": 1, "status": "frozen", "frozen_on": "2026-10-25", "defaults": {"max_price_rlusd": "0.05"},
           "queries": [{"id": x.pop("id"), **x} for x in q]}
    with open("eval/queries_e26.yaml", "w") as fh:
        fh.write("# E26 powered needs. FROZEN 2026-10-25 by eval/gen_e26.py, before any E26 pick or purchase.\n")
        yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True, width=200)


if __name__ == "__main__":
    main()
