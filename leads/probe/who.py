import sys, requests
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 Chrome/120"}
for u in sys.argv[1:]:
    try:
        s = BeautifulSoup(requests.get(f"https://t.me/{u}", headers=UA, timeout=20).text, "html.parser")
        g = lambda c: (s.select_one(c).get_text(" ", strip=True) if s.select_one(c) else "")
        print(f"{u} | {g('.tgme_page_title')[:60]!r} | {g('.tgme_page_extra')!r} | {g('.tgme_page_description')[:120]!r}")
    except Exception as e:
        print(u, "ERR", e)
