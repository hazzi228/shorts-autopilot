import sys, requests
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 Chrome/120"}
for u in sys.argv[1:]:
    s = BeautifulSoup(requests.get(f"https://t.me/{u}", headers=UA, timeout=20).text, "html.parser")
    g = lambda c: (s.select_one(c).get_text(" ", strip=True) if s.select_one(c) else "")
    print(f"=== {u} | title={g('.tgme_page_title')!r} | extra={g('.tgme_page_extra')!r} | desc={g('.tgme_page_description')[:200]!r} | btn={g('.tgme_action_button_new')!r}")
