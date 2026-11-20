"""Какие контакты повторяются в постах каналов (признак спама)."""
import re, json, requests
from collections import defaultdict
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 Chrome/120"}
seen = defaultdict(set)
for ch in json.load(open("leads/sources.json"))["telegram"]:
    url = f"https://t.me/s/{ch}"
    for _ in range(5):
        s = BeautifulSoup(requests.get(url, headers=UA, timeout=25).text, "html.parser")
        ms = s.select("div.tgme_widget_message[data-post]")
        if not ms: break
        for m in ms:
            b = m.select_one(".tgme_widget_message_text")
            if not b: continue
            for c in set(re.findall(r"@([A-Za-z][A-Za-z0-9_]{4,31})", b.get_text(" "))):
                seen[c.lower()].add(m["data-post"])
        url = f"https://t.me/s/{ch}?before=" + ms[0]["data-post"].split("/")[-1]
for c, posts in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:40]:
    print(len(posts), c, sorted(posts)[:4])
print("svetik:", sorted(seen.get("svetik_moonlike", [])))
