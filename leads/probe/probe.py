"""Временная проверка каналов: кто и как пишет посты."""
import re, sys, json
from collections import Counter
from datetime import datetime, timezone
import requests
sys.path.insert(0, "leads")
import finder
from bs4 import BeautifulSoup
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
EXCH = re.compile(r"kwork|fl\.ru|freelance\.ru|habr\.com/freelance|freelance\.habr|weblancer|youdo|workzilla|freelancehunt|pchel|profi\.ru|hh\.ru|superjob|avito", re.I)
for ch in sys.argv[1:]:
    try:
        html = requests.get(f"https://t.me/s/{ch}", headers=UA, timeout=25).text
        s = BeautifulSoup(html, "html.parser")
        for _ in range(3):
            first = s.select("div.tgme_widget_message[data-post]")
            if not first: break
            before = first[0]["data-post"].split("/")[-1]
            more = BeautifulSoup(requests.get(f"https://t.me/s/{ch}?before={before}", headers=UA, timeout=25).text, "html.parser")
            ms = more.select("div.tgme_widget_message[data-post]")
            if not ms: break
            for m in reversed(ms):
                first[0].insert_before(m)
    except Exception as e:
        print(f"=== {ch}: ERR {e}"); continue
    title = s.select_one(".tgme_channel_info_header_title")
    desc = s.select_one(".tgme_channel_info_description")
    subs = [c.get_text(" ") for c in s.select(".tgme_channel_info_counter")]
    msgs = s.select("div.tgme_widget_message[data-post]")
    print(f"\n=== {ch} | {title.get_text(' ').strip() if title else '-'} | {subs} | posts={len(msgs)}")
    if not msgs:
        print("   (нет превью: чат/закрыт/не существует)"); continue
    print("   DESC:", (desc.get_text(' ') if desc else '')[:250].replace("\n", " "))
    dates, exch, via, authors, btns = [], 0, Counter(), Counter(), 0
    texts = []
    hits = []
    for m in msgs:
        t = m.select_one("time[datetime]")
        if t: dates.append(datetime.fromisoformat(t["datetime"]))
        body = m.select_one(".tgme_widget_message_text")
        txt = body.get_text(" ") if body else ""
        links = " ".join(a.get("href", "") for a in (body.select("a[href]") if body else []))
        if EXCH.search(txt + " " + links): exch += 1
        v = m.select_one(".tgme_widget_message_via_bot")
        if v: via[v.get_text(" ")] += 1
        a = m.select_one(".tgme_widget_message_from_author")
        if a: authors[a.get_text(" ")] += 1
        f = m.select_one(".tgme_widget_message_forwarded_from_name")
        if f: authors["fwd:" + f.get_text(" ")] += 1
        if m.select_one(".tgme_widget_message_inline_keyboard"): btns += 1
        texts.append(re.sub(r"\s+", " ", txt))
        k = finder.classify(finder.clean(txt)) if txt else None
        if k: hits.append(re.sub(r"\s+", " ", txt)[:200])
    span = (max(dates) - min(dates)).total_seconds() / 3600 if len(dates) > 1 else 0
    last = (datetime.now(timezone.utc) - max(dates)).total_seconds() / 3600 if dates else -1
    print(f"   span={span:.1f}h last={last:.1f}h ago exchange_links={exch}/{len(msgs)} via={dict(via)} authors={dict(authors.most_common(4))} buttons={btns}")
    print(f"   HITS={len(hits)}/{len(msgs)}")
    for t in hits[-8:]:
        print("   +", t)
    for t in texts[-2:]:
        print("   -", t[:200])
