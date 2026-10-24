# Временная проверка источников (удалить после).
import re, sys, json, time
from datetime import datetime, timezone
sys.path.insert(0, "leads")
import finder
import requests
from bs4 import BeautifulSoup

cands = """programming_jobs php_jobs it_orders mobile_dev_jobs freelance_jobs_ru freelance_orders freelance_birzha
freelancebaraholka it_freelance python_jobs_ru frontend_freelance backend_orders wordpress_freelance tilda_freelance
web_design_orders freelancetavern freelance_ru workathome freelancechoice zakaz_freelance remote_ru freelance_jobs_tg
easy_freelance theyseeku worklis novobranez workzavr tolokaSeek bina_Znaet allgigs remote_w0rk freelansim_ru FreelanceBay
textmoney naudalenkebro normrabota Getitrussia freelance_bot_orders zakazy_it it_zakazy frilans_it devfreelance
freelance_dev python_freelance webdev_freelance zakazy_programmistam botfreelance tgbots_orders""".split()
now = datetime.now(timezone.utc)
rows = []
for ch in cands:
    try:
        items = list(finder.from_telegram(ch))
    except Exception as e:
        rows.append((ch, "ERR " + type(e).__name__)); continue
    if not items:
        rows.append((ch, "0 posts")); continue
    days = (now - items[0]["date"]).total_seconds() / 86400
    span = max((items[-1]["date"] - items[0]["date"]).total_seconds() / 86400, 0.01)
    hits = [i for i in items if finder.classify(i["text"])]
    rows.append((ch, f"{len(items)} posts / {span:.1f}d, last {(now-items[-1]['date']).total_seconds()/3600:.0f}h ago, hits {len(hits)}"))
    for h in hits[:3]:
        print(f"   [{ch}] {finder.classify(h['text'])}: {h['text'][:160]}")
    time.sleep(0.7)
for r in rows: print("TG", *r)

UA = finder.UA
for c in range(1, 45):
    try:
        x = requests.get(f"https://www.fl.ru/rss/all.xml?category={c}", headers=UA, timeout=20).text
        t = re.search(r"<title>([^<]*)</title>", x)
        n = x.count("<item>")
        print("FL", c, n, t.group(1) if t else "")
    except Exception as e:
        print("FL", c, "ERR", e)
for url in ["https://kwork.ru/projects?c=41", "https://kwork.ru/projects?c=37"]:
    h = requests.get(url, headers=UA, timeout=20).text
    print("KW", url, len(h), "wants" in h, h.count('"want_id"'), h.count("wantsListData"), re.findall(r'"name":"([^"]{10,80})"', h)[:5])
    for k in ["window.stateData", "wants\":", "projects-list", "want-card", "data-id"]:
        print("   ", k, h.count(k))
try:
    r = requests.post("https://kwork.ru/projects", headers={**UA, "X-Requested-With": "XMLHttpRequest"}, data={"c": "41", "page": 1}, timeout=20)
    print("KW POST", r.status_code, r.headers.get("content-type"), r.text[:600])
except Exception as e:
    print("KW POST ERR", e)
