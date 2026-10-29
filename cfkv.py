"""Память бота-портфолио (Cloudflare Workers KV), через которую автопилот общается с ботом:
ролики для Instagram лежат там час, ключ TikTok хранится постоянно."""
import os

NAMESPACE = "portfolio-bot-state"


class KV:
    def __init__(self):
        import requests
        self.http = requests
        acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        self.ok = bool(acc and token)
        if not self.ok:
            return
        self.base = "https://api.cloudflare.com/client/v4/accounts/" + acc
        self.auth = {"Authorization": "Bearer " + token}
        ns = self.http.get(self.base + "/storage/kv/namespaces", params={"per_page": 100},
                           headers=self.auth, timeout=60).json()
        self.ns = next((n["id"] for n in ns.get("result") or [] if n["title"] == NAMESPACE), None)
        self.ok = bool(self.ns)

    def _url(self, key):
        return "%s/storage/kv/namespaces/%s/values/%s" % (self.base, self.ns, key)

    def get(self, key):
        r = self.http.get(self._url(key), headers=self.auth, timeout=60)
        return r.content if r.ok else None

    def put(self, key, value, ttl=None):
        params = {"expiration_ttl": ttl} if ttl else None
        r = self.http.put(self._url(key), params=params, data=value, headers=self.auth, timeout=300)
        return r.ok

    def delete(self, key):
        self.http.delete(self._url(key), headers=self.auth, timeout=60)

    def bot_url(self):
        """Адрес бота вида https://portfolio-bot.<имя>.workers.dev."""
        sub = (self.http.get(self.base + "/workers/subdomain", headers=self.auth, timeout=60)
               .json().get("result") or {}).get("subdomain")
        return "https://portfolio-bot.%s.workers.dev" % sub if sub else None
