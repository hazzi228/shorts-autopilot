# Временная проверка Kwork (удалить после).
import json, requests, sys
sys.path.insert(0, "leads")
import finder
H = {**finder.UA, "X-Requested-With": "XMLHttpRequest"}
for c in ["11", "41", "37", "38", "79", "255", ""]:
    data = {"page": 1}
    if c: data["c"] = c
    r = requests.post("https://kwork.ru/projects", headers=H, data=data, timeout=20)
    try:
        j = r.json()
    except Exception:
        print("C", c, r.status_code, r.text[:200]); continue
    p = (j.get("data") or {}).get("pagination") or {}
    items = p.get("data") or []
    print("C", c, r.status_code, "items", len(items), "total", p.get("total"), "last_page", p.get("last_page"))
    if c == "11" and items:
        w = items[0]
        print("KEYS", sorted(w.keys()))
        print(json.dumps({k: w[k] for k in w if not isinstance(w[k], (dict, list))}, ensure_ascii=False)[:1500])
    for w in items[:6]:
        print("   ", w.get("category_id"), "|", (w.get("name") or "")[:90], "|", w.get("priceLimit"), w.get("date_create") or w.get("dateCreate"))
