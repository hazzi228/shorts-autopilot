// TikTok для автопилота роликов: вход владельца в TikTok и страницы для заявки на аудит приложения.
//
// Владелец пишет боту /tiktok, бот присылает одноразовую ссылку на вход. После входа TikTok
// возвращает сюда код, бот меняет его на ключ и кладёт в KV (tiktok_auth). Автопилот (tiktok.py)
// берёт ключ из KV и отправляет каждый ролик в черновики TikTok.

const AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/";
const TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/";
const SCOPES = "user.info.basic,video.upload";
const DAY = 24 * 3600;

export const callbackUrl = (request) => `${new URL(request.url).origin}/tiktok/callback`;

export async function loginLink(env, origin) {
  if (!env.TIKTOK_CLIENT_KEY) return null;
  const state = crypto.randomUUID().replace(/-/g, "");
  await env.STATE.put(`tiktok_state:${state}`, "1", { expirationTtl: 900 });
  const q = new URLSearchParams({
    client_key: env.TIKTOK_CLIENT_KEY, scope: SCOPES, response_type: "code",
    redirect_uri: `${origin}/tiktok/callback`, state,
  });
  return `${AUTH_URL}?${q}`;
}

export async function callback(request, env) {
  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  const code = url.searchParams.get("code");
  if (!code || !/^[0-9a-f]{32}$/.test(state) || !(await env.STATE.get(`tiktok_state:${state}`))) {
    return page("TikTok", "<p>Ссылка устарела. Напиши боту /tiktok ещё раз.</p>", 400);
  }
  await env.STATE.delete(`tiktok_state:${state}`);
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_key: env.TIKTOK_CLIENT_KEY, client_secret: env.TIKTOK_CLIENT_SECRET,
      code, grant_type: "authorization_code", redirect_uri: callbackUrl(request),
    }),
  });
  const json = await res.json();
  if (!json.refresh_token) {
    console.error("TikTok не выдал ключ", JSON.stringify(json).slice(0, 300));
    return page("TikTok", `<p>TikTok не выдал ключ: ${esc(json.error_description || json.error || res.status)}</p>`, 400);
  }
  await env.STATE.put("tiktok_auth", JSON.stringify({
    refresh_token: json.refresh_token,
    open_id: json.open_id,
    scope: json.scope,
    saved: new Date().toISOString(),
  }), { expirationTtl: Math.max(DAY, json.refresh_expires_in || 365 * DAY) });
  return page("TikTok подключён", "<p>Готово! Теперь каждый новый ролик будет приходить в черновики TikTok. Эту вкладку можно закрыть.</p>");
}

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function page(title, body, status = 200) {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(title)}</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:24px 16px;color:#1d1d1f;background:#fff}
h1{font-size:28px}h2{font-size:20px;margin-top:28px}a{color:#5b3df5}nav a{margin-right:16px}
@media (prefers-color-scheme: dark){body{background:#121214;color:#ececf1}a{color:#a99bff}}</style></head>
<body><nav><a href="/neznal">Home</a><a href="/neznal/privacy">Privacy Policy</a><a href="/neznal/terms">Terms of Service</a></nav>
${body}</body></html>`, { status, headers: { "content-type": "text/html; charset=utf-8" } });
}

const CONTACT = 'Telegram: <a href="https://t.me/PortfolioHazzer_bot">@PortfolioHazzer_bot</a>';

const PAGES = {
  "/neznal": ["Не знал? | IT-факты", `
<h1>Не знал? | IT-факты</h1>
<p><b>Neznal autopilot</b> is a personal tool that publishes short vertical videos about the history of technology
and surprising IT facts for the channel «Не знал? | IT-факты» (YouTube Shorts, Instagram Reels and TikTok).</p>
<p>Each video is written, voiced and edited automatically, then uploaded to the channel owner's own accounts.
For TikTok the tool uses the official Content Posting API to send each finished video to the owner's TikTok
inbox as a draft. The owner reviews the draft in the TikTok app and publishes it.</p>
<p>The tool is used only by the channel owner and does not access other people's TikTok accounts.</p>
<h2>Contact</h2><p>${CONTACT}</p>`],
  "/neznal/privacy": ["Privacy Policy", `
<h1>Privacy Policy</h1>
<p>Last updated: October 29, 2026.</p>
<p>Neznal autopilot ("the app") is operated by the owner of the channel «Не знал? | IT-факты» for publishing their own videos.</p>
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
  "/neznal/terms": ["Terms of Service", `
<h1>Terms of Service</h1>
<p>Last updated: October 29, 2026.</p>
<p>Neznal autopilot is a personal publishing tool for the channel «Не знал? | IT-факты». By connecting a TikTok account
you allow the app to upload videos to that account's inbox as drafts. Nothing is published without the account owner's
confirmation in the TikTok app.</p>
<p>The app is provided as is, free of charge, without warranties. Use of TikTok is also governed by the
<a href="https://www.tiktok.com/legal/terms-of-service">TikTok Terms of Service</a>. Access can be revoked at any time
in TikTok settings.</p>
<h2>Contact</h2><p>${CONTACT}</p>`],
};

// Файлы подтверждения адреса для TikTok (URL properties в кабинете разработчика).
const VERIFY = {
  "/neznal/tiktokBAKPcjCph3oaIsiSU3vfNTWY9jzl3jQW.txt": "tiktok-developers-site-verification=BAKPcjCph3oaIsiSU3vfNTWY9jzl3jQW",
};

export function sitePage(pathname) {
  if (VERIFY[pathname]) return new Response(VERIFY[pathname], { headers: { "content-type": "text/plain" } });
  const p = PAGES[pathname.replace(/\/$/, "")];
  return p ? page(...p) : null;
}
