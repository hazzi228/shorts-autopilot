// Сайт приложения Neznal для проверки TikTok: имя приложения, заголовок сайта и адрес должны совпадать.
// Отдельный воркер neznal.<имя>.workers.dev, выкладывает .github/workflows/neznal-site.yml.
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function page(title, body) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(title)}</title>
<link rel="icon" href="/icon.jpg">
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:24px 16px;color:#1d1d1f;background:#fff}
h1{font-size:28px}h2{font-size:20px;margin-top:28px}a{color:#5b3df5}nav a{margin-right:16px}
@media (prefers-color-scheme: dark){body{background:#121214;color:#ececf1}a{color:#a99bff}}</style></head>
<body><nav><b style="margin-right:16px">Neznal</b><a href="/">Home</a><a href="/privacy">Privacy Policy</a><a href="/terms">Terms of Service</a></nav>
${body}</body></html>`, { headers: { "content-type": "text/html; charset=utf-8" } });
}

const CONTACT = 'Telegram: <a href="https://t.me/PortfolioHazzer_reserv_bot">@PortfolioHazzer_reserv_bot</a>';

const PAGES = {
  "": ["Neznal", `
<img src="/icon.jpg" alt="" width="96" height="96" style="border-radius:20px">
<h1>Neznal</h1>
<p><b>Neznal</b> is a personal tool that publishes short vertical videos about the history of technology
and surprising IT facts for the channel «Не знал? | IT-факты» (YouTube Shorts, Instagram Reels and TikTok).</p>
<p>Each video is written, voiced and edited automatically, then uploaded to the channel owner's own accounts.
For TikTok the tool uses the official Content Posting API to send each finished video to the owner's TikTok
inbox as a draft. The owner reviews the draft in the TikTok app and publishes it.</p>
<p>The tool is used only by the channel owner and does not access other people's TikTok accounts.</p>
<h2>Contact</h2><p>${CONTACT}</p>`],
  "/privacy": ["Neznal – Privacy Policy", `
<h1>Privacy Policy</h1>
<p>Last updated: November 17, 2026.</p>
<p>Neznal ("the app") is operated by the owner of the channel «Не знал? | IT-факты» for publishing their own videos.</p>
<h2>What we collect</h2>
<p>When the owner connects their TikTok account, the app receives an access token, a refresh token and the account's
open ID from TikTok (scopes <code>user.info.basic</code> and <code>video.upload</code>). No other data is collected.
The app does not collect data from viewers or from any other TikTok users.</p>
<h2>How we use it</h2>
<p>The tokens are used only to upload the owner's own videos to the owner's TikTok inbox as drafts.</p>
<h2>Storage and sharing</h2>
<p>Tokens are stored in private, access-controlled storage (Cloudflare Workers KV) and are never sold or shared
with third parties. Videos are hosted temporarily only for the time needed to upload them.</p>
<h2>Deleting data</h2>
<p>The owner can revoke access at any time in TikTok settings (Security → Manage app permissions); the stored tokens
then stop working and are deleted. You can also ask for deletion via the contact below.</p>
<h2>Contact</h2><p>${CONTACT}</p>`],
  "/terms": ["Neznal – Terms of Service", `
<h1>Terms of Service</h1>
<p>Last updated: November 17, 2026.</p>
<p>Neznal is a personal publishing tool for the channel «Не знал? | IT-факты». By connecting a TikTok account
you allow the app to upload videos to that account's inbox as drafts. Nothing is published without the account owner's
confirmation in the TikTok app.</p>
<p>The app is provided as is, free of charge, without warranties. Use of TikTok is also governed by the
<a href="https://www.tiktok.com/legal/terms-of-service">TikTok Terms of Service</a>. Access can be revoked at any time
in TikTok settings.</p>
<h2>Contact</h2><p>${CONTACT}</p>`],
};

// Файл подтверждения адреса для TikTok (URL properties): /tiktok<код>.txt -> "tiktok-developers-site-verification=<код>".
const VERIFY = /^\/tiktok([A-Za-z0-9]{16,64})\.txt$/;

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.replace(/\/$/, "");
    const v = path.match(VERIFY);
    if (v) return new Response(`tiktok-developers-site-verification=${v[1]}`, { headers: { "content-type": "text/plain" } });
    const p = PAGES[path];
    if (p) return page(...p);
    return env.ASSETS.fetch(request);
  },
};
