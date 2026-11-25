# Memecoin Bot Multi-Agent - Mainnet Beta

## Isi Paket
- bot_mainnet.py - Bot utama (Scout -> Analyst -> Sniper/Risk -> Banker)
- prompts.py - Prompt optimasi Grok/Claude/OpenAI
- requirements.txt
- tokens.json - Config blacklist, TP/SL, slippage
- .env.example - Template API Key (copy jadi .env)
- .gitignore - Agar .env tidak ke-push ke Github

## Cara Pakai di Laptop / PC
1. Copy .env.example jadi .env, isi API key
   cp .env.example .env   (di Windows: copy .env.example .env)
2. Install:
   pip install -r requirements.txt
3. Test PAPER TRADE dulu (default PAPER_TRADE=true):
   python bot_mainnet.py
4. Jika sudah 1-2 hari stabil, baru ubah di .env: PAPER_TRADE=false
   DAN pastikan BOT_PRIVATE_KEY adalah Wallet Panas (max 1 SOL, bukan wallet utama)

## Deploy ke Biznet Gio VPS
sudo apt update && sudo apt install python3 python3-pip git -y
git clone https://github.com/USERNAME/bot-memecoin.git
cd bot-memecoin
pip install -r requirements.txt
nano .env  (paste API key asli)
pip install pm2  # atau pakai nohup
pm2 start bot_mainnet.py --name memebot-mainnet --interpreter python3
pm2 logs memebot-mainnet
pm2 save

## Deploy ke Github (AMAN)
echo ".env" >> .gitignore  (sudah ada di paket ini)
git init
git add .
git commit -m "bot mainnet v1"
git remote add origin https://github.com/USERNAME/bot-memecoin.git
git push -u origin main
JANGAN PERNAH push file .env yang berisi private key!

## Urutan Trading Aman
1. Isi 0.5-1 SOL ke Wallet Panas dari Gate.io (Network Solana)
2. PAPER_TRADE=true 1 hari
3. PAPER_TRADE=false, buy 0.05 SOL test
4. Naik ke 0.15 SOL, max 3 trade/hari
5. TP +80% jual 50%, +200% jual 30%, SL -35% jual semua
6. Profit 70% kirim manual ke Vault (Wallet Dingin)

## Peringatan
Memecoin 90% rug. Bot ini edukasi, bukan jaminan profit. Jangan pakai uang pinjaman / uang dapur.
