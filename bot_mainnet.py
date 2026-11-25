"""
BOT_MAINNET.PY - Multi-Agent Memecoin Bot Solana
CrewAI: Scout (Grok) -> Analyst (Claude) -> Sniper/Risk (OpenAI) -> Banker (Claude)

MODE:
- PAPER_TRADE=True (default, AMAN) = hanya simulasi, tidak kirim transaksi asli
- PAPER_TRADE=False = MAINNET ASLI, pakai dana asli. Ubah hanya setelah test 1-2 hari.

DISCLAIMER: Memecoin 90% rug. Mulai dengan 0.5-1 SOL saja. Ini kode edukasi, bukan jaminan profit.
Jangan pernah share BOT_PRIVATE_KEY / .env ke siapapun.
"""

import os
import json
import time
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

# ============ CONFIG ============
try:
    with open("tokens.json", "r") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    CONFIG = {}

PAPER_TRADE = os.getenv("PAPER_TRADE", "true").lower() == "true"
MAX_BUY_SOL = float(os.getenv("MAX_BUY_SOL", CONFIG.get("max_buy_sol", 0.15)))
MIN_CONFIDENCE = int(CONFIG.get("min_confidence_safe", 88))
BLACKLIST = set(CONFIG.get("blacklist", []))
VAULT_ADDRESS = os.getenv("VAULT_ADDRESS", "")
BOT_PUBLIC_KEY = os.getenv("BOT_PUBLIC_KEY", "")
QUICKNODE_RPC = os.getenv("QUICKNODE_RPC", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")

SOL_MINT = "So11111111111111111111111111111111111111112"
JUP_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUP_SWAP_URL = "https://quote-api.jup.ag/v6/swap"

# Lazy import solana agar PAPER_TRADE bisa jalan tanpa key
Client = None
Keypair = None
VersionedTransaction = None
keypair = None

if not PAPER_TRADE:
    try:
        from solana.rpc.api import Client as _Client
        from solders.keypair import Keypair as _Keypair
        from solders.transaction import VersionedTransaction as _VT
        Client = _Client
        Keypair = _Keypair
        VersionedTransaction = _VT
        client = Client(QUICKNODE_RPC)
        priv = os.getenv("BOT_PRIVATE_KEY", "")
        if not priv:
            raise ValueError("BOT_PRIVATE_KEY kosong di .env padahal PAPER_TRADE=False")
        keypair = Keypair.from_base58_string(priv)
        print(f"[MAINNET] Wallet Bot: {keypair.pubkey()}")
    except Exception as e:
        print(f"[ERROR] Gagal init wallet mainnet: {e}")
        raise

# ============ HELPER: DEXSCREENER + BIRDEYE ============
def scan_dexscreener(limit=10):
    """Scout: ambil token baru Solana dari DexScreener (gratis, tanpa key)"""
    try:
        # Endpoint public DexScreener: token profiles / latest
        url = "https://api.dexscreener.com/token-profiles/latest/v1"
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        out = []
        for t in data[:limit]:
            addr = t.get("tokenAddress", "")
            if addr in BLACKLIST:
                continue
            out.append({
                "symbol": t.get("symbol", "UNKNOWN"),
                "address": addr,
                "chain": t.get("chainId", "solana"),
                "description": t.get("description", ""),
            })
        return out
    except Exception as e:
        print(f"[SCOUT] DexScreener error: {e}")
        return []

def get_birdeye_overview(token_address):
    """Ambil data harga / holder via Birdeye"""
    if not BIRDEYE_API_KEY:
        return {}
    try:
        headers = {"X-API-KEY": BIRDEYE_API_KEY}
        url = f"https://public-api.birdeye.so/defi/token_overview?address={token_address}"
        r = requests.get(url, headers=headers, timeout=15)
        return r.json().get("data", {}) if r.status_code == 200 else {}
    except Exception as e:
        print(f"[BIRDEYE] error: {e}")
        return {}

def check_rug_helius(token_address):
    """Analyst: cek metadata token via Helius"""
    if not HELIUS_API_KEY:
        return {"note": "HELIUS_API_KEY kosong, skip cek on-chain detail"}
    try:
        url = f"https://api.helius.xyz/v0/token-metadata?api-key={HELIUS_API_KEY}"
        r = requests.post(url, json={"mintAccounts": [token_address]}, timeout=15)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print(f"[HELIUS] error: {e}")
        return {}

def analyst_verdict(token, overview, helius_data):
    """
    Rule-based + placeholder untuk Claude.
    Di versi CrewAI penuh, ganti fungsi ini dengan panggilan Claude API
    dengan ANALYST_PROMPT. Ini versi aman tanpa hallucination.
    """
    # Contoh heuristik aman: tolak jika data kosong / tidak ada likuiditas
    price = overview.get("price", 0) if isinstance(overview, dict) else 0
    liquidity = overview.get("liquidity", 0) if isinstance(overview, dict) else 0
    # Jika tidak ada data Birdeye, anggap RISKY agar tidak asal beli
    if not overview:
        return {"verdict": "RUG", "confidence": 0, "alasan": "Tidak ada data Birdeye, tolak demi keamanan"}
    if liquidity is not None and isinstance(liquidity, (int, float)) and liquidity < 20000:
        return {"verdict": "RUG", "confidence": 40, "alasan": f"Liquidity terlalu kecil: ${liquidity}"}
    # Lolos heuristik awal -> SAFE, tapi tetap butuh review Claude manual di production
    return {"verdict": "SAFE", "confidence": 90, "alasan": f"Liquidity ${liquidity}, price ${price}, lolos cek awal. Wajib cek manual Mint/Freeze di Solscan sebelum live besar."}

# ============ EKSEKUSI JUPITER / RAYDIUM ============
def swap_sol_to_token(token_address, amount_sol):
    """Sniper: Beli token pakai SOL via Jupiter"""
    if PAPER_TRADE:
        print(f"[PAPER] SIMULASI BUY {amount_sol} SOL -> {token_address} (tidak kirim tx asli)")
        return f"PAPER_TX_{token_address[:8]}_{int(time.time())}"
    # MAINNET ASLI
    try:
        quote_url = f"{JUP_QUOTE_URL}?inputMint={SOL_MINT}&outputMint={token_address}&amount={int(amount_sol * 1e9)}&slippageBps=2000"
        quote = requests.get(quote_url, timeout=20).json()
        if "routePlan" not in quote:
            print(f"[SNIPER] Quote gagal / honeypot: {token_address}")
            return None
        swap_req = requests.post(JUP_SWAP_URL, json={
            "quoteResponse": quote,
            "userPublicKey": str(keypair.pubkey()),
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": 50000
        }, timeout=20).json()
        tx = VersionedTransaction.from_bytes(base64.b64decode(swap_req['swapTransaction']))
        tx.sign([keypair])
        sig = client.send_raw_transaction(bytes(tx), opts={"skip_preflight": False})
        print(f"[SNIPER] BUY OK: https://solscan.io/tx/{sig.value}")
        return str(sig.value)
    except Exception as e:
        print(f"[SNIPER] Buy error: {e}")
        return None

def swap_token_to_sol(token_address, amount_token_raw):
    """Risk: Jual cepat token -> SOL (untuk TP/SL/RUG)"""
    if PAPER_TRADE:
        print(f"[PAPER] SIMULASI SELL {token_address} -> SOL")
        return f"PAPER_SELL_{int(time.time())}"
    try:
        quote_url = f"{JUP_QUOTE_URL}?inputMint={token_address}&outputMint={SOL_MINT}&amount={amount_token_raw}&slippageBps=2500"
        quote = requests.get(quote_url, timeout=20).json()
        if "routePlan" not in quote:
            print("[RISK] Quote jual gagal")
            return None
        swap_req = requests.post(JUP_SWAP_URL, json={
            "quoteResponse": quote,
            "userPublicKey": str(keypair.pubkey()),
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": 100000  # lebih tinggi biar cepat keluar saat rug
        }, timeout=20).json()
        tx = VersionedTransaction.from_bytes(base64.b64decode(swap_req['swapTransaction']))
        tx.sign([keypair])
        sig = client.send_raw_transaction(bytes(tx), opts={"skip_preflight": False})
        print(f"[RISK] SELL OK: https://solscan.io/tx/{sig.value}")
        return str(sig.value)
    except Exception as e:
        print(f"[RISK] Sell error: {e}")
        return None

# ============ CREWAI MULTI-AGENT (opsional, butuh API keys) ============
def run_crewai_cycle(candidates):
    """
    Jika semua API key AI ada, jalankan CrewAI.
    Jika tidak ada, fallback ke rule-based di atas agar tetap jalan.
    """
    grok = os.getenv("GROK_API_KEY", "")
    claude = os.getenv("CLAUDE_API_KEY", "")
    openai = os.getenv("OPENAI_API_KEY", "")
    if not (grok and claude and openai):
        print("[CREWAI] API key AI belum lengkap, pakai mode rule-based aman.")
        return None
    try:
        from crewai import Agent, Task, Crew, LLM
        from prompts import SCOUT_PROMPT, ANALYST_PROMPT, SNIPER_PROMPT, BANKER_PROMPT
        grok_llm = LLM(model="xai/grok-2-latest", api_key=grok)
        claude_llm = LLM(model="anthropic/claude-3-5-sonnet-20241022", api_key=claude)
        openai_llm = LLM(model="openai/gpt-4o", api_key=openai)

        scout = Agent(role="Scout", goal="Scan memecoin viral", backstory="Hunter cepat", llm=grok_llm, verbose=True)
        analyst = Agent(role="Analyst", goal="Cegah rug pull", backstory="Auditor paranoid", llm=claude_llm, verbose=True)
        sniper = Agent(role="Sniper", goal="Eksekusi profit", backstory="Trader disiplin", llm=openai_llm, verbose=True)

        t1 = Task(description=SCOUT_PROMPT + f"\nKandidat awal: {candidates}", expected_output="JSON list token", agent=scout)
        t2 = Task(description=ANALYST_PROMPT, expected_output="JSON verdict", agent=analyst, context=[t1])
        t3 = Task(description=SNIPER_PROMPT.format(max_buy_sol=MAX_BUY_SOL), expected_output="Tx Hash", agent=sniper, context=[t2])
        crew = Crew(agents=[scout, analyst, sniper], tasks=[t1, t2, t3], verbose=2)
        return crew.kickoff()
    except Exception as e:
        print(f"[CREWAI] error: {e}")
        return None

# ============ MAIN LOOP ============
def one_cycle():
    print("\n=== Siklus Baru ===")
    print(f"Mode: {'PAPER_TRADE (simulasi)' if PAPER_TRADE else 'MAINNET ASLI - DANA ASLI'} | Max Buy: {MAX_BUY_SOL} SOL")
    candidates = scan_dexscreener(limit=10)
    print(f"[SCOUT] Dapat {len(candidates)} kandidat dari DexScreener")
    if not candidates:
        return

    # Coba CrewAI dulu jika key lengkap
    crew_result = run_crewai_cycle(candidates)
    if crew_result is not None:
        print(f"[CREWAI] Hasil: {crew_result}")
        log_trade({"type": "crewai", "result": str(crew_result)})
        return

    # Fallback rule-based aman
    for cand in candidates[:3]:
        addr = cand["address"]
        if not addr:
            continue
        overview = get_birdeye_overview(addr)
        helius = check_rug_helius(addr)
        verdict = analyst_verdict(cand, overview, helius)
        print(f"[ANALYST] {cand['symbol']} {addr[:10]}... -> {verdict}")
        if verdict["verdict"] == "SAFE" and verdict["confidence"] >= MIN_CONFIDENCE:
            tx = swap_sol_to_token(addr, MAX_BUY_SOL)
            log_trade({"type": "buy", "symbol": cand["symbol"], "address": addr, "amount_sol": MAX_BUY_SOL, "tx": tx, "verdict": verdict, "paper": PAPER_TRADE})
            # Di production, di sini pasang monitoring TP +80% / +200% / SL -35%
            print(f"[BANKER] Catat posisi. TP1 +80% jual 50%, TP2 +200% jual 30%, SL -35% jual semua. Profit 70% -> Vault {VAULT_ADDRESS[:10] if VAULT_ADDRESS else '(isi di .env)'}")
        else:
            print(f"[RISK] Tolak {cand['symbol']} - tidak SAFE")
        time.sleep(2)

def log_trade(entry):
    try:
        with open("trade_log.json", "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Log error: {e}")

if __name__ == "__main__":
    print("Bot Multi-Agent Memecoin - PAPER_TRADE =", PAPER_TRADE)
    print("Tekan Ctrl+C untuk berhenti.")
    while True:
        try:
            one_cycle()
        except KeyboardInterrupt:
            print("\nBot dihentikan.")
            break
        except Exception as e:
            print(f"[MAIN] error: {e}")
        print("Tidur 60 detik...")
        time.sleep(60)
