// Бот-портфолио на Cloudflare Workers: работает круглосуточно и бесплатно.
//
// Telegram присылает каждое сообщение сюда (webhook), бот отвечает и засыпает.
// Тексты, работы и отзывы берутся из data.json при выкладке: поправил файл в GitHub,
// и через минуту бот уже показывает новое.
//
// Заявки и сообщения клиентов бот пересылает владельцу. Владелец отвечает на них
// кнопкой «Ответить» (Reply), и бот отправляет ответ клиенту от своего имени,
// поэтому спам-блок аккаунта владельца переписке не мешает.

import data from "./data.json";
import * as tiktok from "./tiktok.js";

const ORDER_KINDS = { bot: "🤖 Telegram-бот", site: "🌐 Сайт", other: "✨ Другое" };
const DAY = 24 * 3600;

export default {
  async fetch(request, env) {
    // Ролики для Instagram: автопилот кладёт файл в память на час, Instagram скачивает его отсюда.
    const { pathname, origin } = new URL(request.url);
    const reel = pathname.match(/^\/ig\/(reel-[0-9a-f]{32}\.mp4)$/);
    if (reel && request.method === "GET") {
      const video = await env.STATE.get(reel[1], { type: "arrayBuffer" });
      if (!video) return new Response("not found", { status: 404 });
      return new Response(video, { headers: { "content-type": "video/mp4", "access-control-allow-origin": "*" } });
    }
    // Сайт канала и вход в TikTok (страницы нужны для заявки на аудит приложения TikTok).
    if (request.method === "GET" && pathname === "/tiktok/callback") return tiktok.callback(request, env);
    if (request.method === "GET" && pathname === "/neznal/icon.jpg") {
      const icon = await env.ASSETS.fetch("https://assets/neznal-icon.jpg");
      return new Response(icon.body, { headers: { "content-type": "image/jpeg", "access-control-allow-origin": "*" } });
    }
    // Описание для черновика TikTok: автопилот кладёт текст в KV и просит бота прислать его владельцу.
    // Писать в KV может только автопилот, поэтому чужой запрос сюда ничего не отправит.
    const note = pathname.match(/^\/tiktok\/note\/(tt_note-[0-9a-f]{32})$/);
    if (note && request.method === "POST") {
      const text = await env.STATE.get(note[1]);
      if (!text) return new Response("not found", { status: 404 });
      await env.STATE.delete(note[1]);
      const bot = new Bot(env, origin);
      for (const owner of await bot.ownerIds()) {
        await bot.send(owner, `🎬 В TikTok пришёл новый черновик. Описание к нему (нажми на текст, чтобы скопировать):\n\n<pre>${esc(text)}</pre>`);
      }
      return new Response("ok");
    }
    // Ролик не дошёл до TikTok: автопилот кладёт ролик и описание в KV, бот присылает их владельцу для ручной загрузки.
    const fail = pathname.match(/^\/tiktok\/fail\/([0-9a-f]{32})$/);
    if (fail && request.method === "POST") {
      const meta = await env.STATE.get(`tt_fail-${fail[1]}`);
      const video = await env.STATE.get(`tt_vid-${fail[1]}`, "arrayBuffer");
      if (!meta || !video) return new Response("not found", { status: 404 });
      await env.STATE.delete(`tt_fail-${fail[1]}`);
      await env.STATE.delete(`tt_vid-${fail[1]}`);
      const { why, caption } = JSON.parse(meta);
      const bot = new Bot(env, origin);
      for (const owner of await bot.ownerIds()) {
        const form = new FormData();
        form.append("chat_id", String(owner));
        form.append("caption", `⚠️ ${why}. Загрузи ролик в TikTok вручную, описание ниже.`);
        form.append("supports_streaming", "true");
        form.append("video", new Blob([video], { type: "video/mp4" }), "tiktok.mp4");
        await bot.call("sendVideo", null, form);
        await bot.send(owner, `Описание (нажми на текст, чтобы скопировать):\n\n<pre>${esc(caption)}</pre>`);
      }
      return new Response("ok");
    }
    if (request.method === "GET") return tiktok.sitePage(pathname) || new Response("Бот работает");
    if (request.method !== "POST") return new Response("Бот работает");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== (await webhookSecret(env.BOT_TOKEN))) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    try {
      const bot = new Bot(env, origin);
      if (update.callback_query) await onButton(bot, update.callback_query);
      else if (update.message?.chat?.type === "private") await onMessage(bot, update.message);
    } catch (e) {
      console.error("Ошибка при обработке обновления", e.stack || e);
    }
    // Всегда 200, иначе Telegram будет повторять одно и то же сообщение.
    return new Response("ok");
  },

  // Расписание GitHub Actions на бесплатном тарифе почти не срабатывает, а таймер Cloudflare
  // точный. Поэтому по таймеру (wrangler.toml) бот сам запускает в GitHub ролики и поиск заказов.
  async scheduled(event, env) {
    const job = CRON_JOBS[event.cron];
    if (!job || !env.GH_DISPATCH_TOKEN) return;
    const res = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${job.workflow}/dispatches`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        accept: "application/vnd.github+json",
        "user-agent": "portfolio-bot",
      },
      body: JSON.stringify({ ref: "main", inputs: job.inputs }),
    });
    if (res.ok) return;
    const why = `${res.status} ${(await res.text()).slice(0, 200)}`;
    console.error(`Не удалось запустить ${job.workflow}: ${why}`);
    // Предупреждаем владельца не чаще раза в сутки: скорее всего, истёк или неверный токен GitHub.
    const bot = new Bot(env);
    if (await bot.kv.get("dispatch_warned")) return;
    await bot.kv.put("dispatch_warned", "1", { expirationTtl: DAY });
    for (const owner of await bot.ownerIds()) {
      await bot.send(owner, `⚠️ Не получилось запустить ${esc(job.workflow)} в GitHub (${esc(why)}). ` +
        "Скорее всего, истёк токен GH_DISPATCH_TOKEN: создай новый и замени секрет в GitHub.").catch(() => {});
    }
  },
};

const REPO = "hazzi228/shorts-autopilot";
// Время по UTC (Москва = UTC+3), строки должны совпадать с [triggers] в wrangler.toml.
const CRON_JOBS = {
  // Ролики в 8:00, 12:00 (реклама), 16:00 и 22:00 по Москве; check: true пропускает запуск, если ролик в этом слоте уже вышел.
  "5 5-7,9-11,13-15,19-21 * * *": { workflow: "autopilot.yml", inputs: { check: "true" } },
  // Поиск заказов каждый час с 8:17 до 23:17 по Москве.
  "17 5-20 * * *": { workflow: "leads.yml" },
};

export async function webhookSecret(token) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

class Bot {
  constructor(env, origin) {
    this.env = env;
    this.origin = origin;
    this.kv = env.STATE;
  }

  async call(method, params, form) {
    const url = `https://api.telegram.org/bot${this.env.BOT_TOKEN}/${method}`;
    const res = form
      ? await fetch(url, { method: "POST", body: form })
      : await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(params) });
    const json = await res.json();
    if (!json.ok) throw new Error(`${method}: ${json.description}`);
    return json.result;
  }

  send(chat_id, text, reply_markup) {
    return this.call("sendMessage", { chat_id, text, reply_markup, parse_mode: "HTML", disable_web_page_preview: true });
  }

  async sendPhoto(chat_id, image, caption, reply_markup) {
    const base = { chat_id, caption, parse_mode: "HTML", reply_markup };
    if (/^https?:\/\//.test(image)) return this.call("sendPhoto", { ...base, photo: image });
    // Файл загружается в Telegram один раз, дальше отправляем его по file_id.
    const cached = await this.kv.get(`img:${image}`);
    if (cached) return this.call("sendPhoto", { ...base, photo: cached });
    const form = new FormData();
    for (const [k, v] of Object.entries(base)) if (v !== undefined) form.append(k, typeof v === "object" ? JSON.stringify(v) : String(v));
    const file = await this.env.ASSETS.fetch(`https://assets/${encodeURIComponent(image)}`);
    if (!file.ok) throw new Error(`Нет картинки images/${image}`);
    form.append("photo", await file.blob(), image);
    const msg = await this.call("sendPhoto", null, form);
    await this.kv.put(`img:${image}`, msg.photo.at(-1).file_id);
    return msg;
  }

  // Владельцев может быть несколько: основной ник owner.telegram и дополнительные owner.extra_owners.
  // id узнаём, когда владелец впервые пишет боту, и храним в KV.
  async ownerIds(user) {
    const fixed = String(this.env.OWNER_ID || "").split(",").map((s) => Number(s.trim())).filter(Boolean);
    if (fixed.length) return fixed;
    let ids = JSON.parse((await this.kv.get("owner_ids")) || "[]");
    if (!ids.length) {
      const old = await this.kv.get("owner_id");
      if (old) ids = [Number(old)];
    }
    const nicks = [data.owner?.telegram, ...(data.owner?.extra_owners || [])]
      .map((n) => String(n || "").replace(/^@/, "").toLowerCase()).filter(Boolean);
    if (user?.username && nicks.includes(user.username.toLowerCase()) && !ids.includes(user.id)) {
      ids.push(user.id);
      await this.kv.put("owner_ids", JSON.stringify(ids));
    }
    return ids;
  }
}

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const kb = (rows) => ({ inline_keyboard: rows.map((row) => row.map(([text, btn]) => ({ text, ...btn }))) });
const backToMenu = kb([[["⬅️ В меню", { callback_data: "menu" }]]]);

function mainMenu() {
  const owner = data.owner || {};
  const text = `<b>${esc(owner.name)}</b>\n${esc(owner.greeting)}`;
  return [text, kb([
    [["📝 Заказать бота или сайт", { callback_data: "order" }]],
    [["💼 Портфолио", { callback_data: "portfolio" }]],
    [["📦 Выполненные заказы", { callback_data: "orders" }]],
    [["👤 Обо мне", { callback_data: "about" }], ["📞 Контакты", { callback_data: "contacts" }]],
  ])];
}

function listScreen(items, prefix, title) {
  if (!items?.length) return [`<b>${title}</b>\n\nПока пусто.`, backToMenu];
  const rows = items.map((item, i) => [[item.title || `#${i + 1}`, { callback_data: `${prefix}:${i}` }]]);
  rows.push([["⬅️ В меню", { callback_data: "menu" }]]);
  return [`<b>${title}</b>\n\nВыберите пункт:`, kb(rows)];
}

function portfolioText(item) {
  const parts = [`<b>${esc(item.title)}</b>`];
  if (item.description) parts.push(esc(item.description));
  if (item.tags?.length) parts.push("🏷 " + item.tags.map(esc).join(", "));
  if (item.year) parts.push(`📅 ${esc(item.year)}`);
  return parts.join("\n\n");
}

function orderText(item) {
  const parts = [`<b>${esc(item.title)}</b>`];
  const fields = [["👤 Заказчик", "client"], ["📅 Дата", "date"], ["🛠 Что сделано", "description"],
    ["💰 Стоимость", "price"], ["⭐️ Отзыв", "review"]];
  for (const [label, key] of fields) if (item[key]) parts.push(`${label}: ${esc(item[key])}`);
  return parts.join("\n\n");
}

function itemKeyboard(item, back) {
  const rows = [];
  if (item.link) rows.push([["🔗 Открыть", { url: item.link }]]);
  rows.push([["⬅️ Назад", { callback_data: back }], ["🏠 Меню", { callback_data: "menu" }]]);
  return kb(rows);
}

// Показывает экран: редактирует текущее сообщение или шлёт новое, если нужна картинка.
async function show(bot, chatId, message, text, markup, image) {
  const hasImage = Boolean(image);
  if (message && !hasImage && message.text !== undefined) {
    try {
      return await bot.call("editMessageText", { chat_id: chatId, message_id: message.message_id, text,
        reply_markup: markup, parse_mode: "HTML", disable_web_page_preview: true });
    } catch (e) {
      if (/not modified/i.test(e.message)) return;
    }
  }
  // Сообщение с фото нельзя превратить в текстовое, поэтому удаляем старое и шлём новое.
  if (message) await bot.call("deleteMessage", { chat_id: chatId, message_id: message.message_id }).catch(() => {});
  if (hasImage) {
    const caption = text.length <= 1024 ? text : text.slice(0, 1020) + "…";
    try {
      return await bot.sendPhoto(chatId, image, caption, markup);
    } catch (e) {
      console.warn("Картинка не отправилась, показываю без неё:", e.message);
    }
  }
  return bot.send(chatId, text, markup);
}

async function onButton(bot, query) {
  await bot.call("answerCallbackQuery", { callback_query_id: query.id }).catch(() => {});
  const chatId = query.message?.chat.id ?? query.from.id;
  const msg = query.message;
  const action = query.data || "menu";

  if (action === "menu") return show(bot, chatId, msg, ...mainMenu());
  if (action === "order") {
    const rows = Object.entries(ORDER_KINDS).map(([key, title]) => [[title, { callback_data: `kind:${key}` }]]);
    rows.push([["⬅️ В меню", { callback_data: "menu" }]]);
    return show(bot, chatId, msg, "<b>📝 Заявка</b>\n\nЧто нужно сделать?", kb(rows));
  }
  if (action.startsWith("kind:")) {
    await bot.kv.put(`kind:${query.from.id}`, action.slice(5), { expirationTtl: DAY });
    return show(bot, chatId, msg,
      "<b>📝 Опишите задачу одним сообщением</b>\n\n• что должен уметь бот или сайт;\n" +
      "• есть ли пример, на что похоже;\n• сроки и примерный бюджет, если есть.\n\n" +
      "Можно приложить файл или скриншот. Ответ придёт сюда, в этот бот.", backToMenu);
  }
  if (action === "portfolio") return show(bot, chatId, msg, ...listScreen(data.portfolio, "p", "💼 Портфолио"));
  if (action === "orders") return show(bot, chatId, msg, ...listScreen(data.orders, "o", "📦 Выполненные заказы"));
  if (action === "about") return show(bot, chatId, msg, esc(data.about) || "Информация скоро появится.", backToMenu);
  if (action === "contacts") {
    const rows = (data.contacts || []).filter((c) => c.url).map((c) => [[c.title, { url: c.url }]]);
    rows.push([["⬅️ В меню", { callback_data: "menu" }]]);
    return show(bot, chatId, msg, "<b>📞 Контакты</b>\n\nНапишите мне удобным способом:", kb(rows));
  }
  const [prefix, idx] = action.split(":");
  const item = (prefix === "p" ? data.portfolio : data.orders)?.[Number(idx)];
  if (!item) return show(bot, chatId, msg, "Этот пункт удалён или изменён.", backToMenu);
  if (prefix === "p") return show(bot, chatId, msg, portfolioText(item), itemKeyboard(item, "portfolio"), item.image);
  return show(bot, chatId, msg, orderText(item), itemKeyboard(item, "orders"), item.image);
}

function clientLabel(user) {
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || "Без имени";
  const nick = user.username ? ` (@${esc(user.username)})` : "";
  return `<a href="tg://user?id=${user.id}">${esc(name)}</a>${nick}`;
}

// Пересылает сообщение клиента владельцу и запоминает, кому отвечать.
async function toOwner(bot, msg, header) {
  const owners = await bot.ownerIds();
  if (!owners.length) {
    console.warn("Пришла заявка, но владелец ещё не нажимал /start в боте, переслать некуда");
    return false;
  }
  const remember = (m) => bot.kv.put(`relay:${m.chat.id}:${m.message_id}`, String(msg.chat.id), { expirationTtl: 90 * DAY });
  for (const owner of owners) {
    await remember(await bot.send(owner, header));
    // Текст уже стоит в заголовке, а фото, файлы и голосовые пересылаем отдельно.
    if (!msg.text) {
      await remember(await bot.call("copyMessage", { chat_id: owner, from_chat_id: msg.chat.id, message_id: msg.message_id }));
    }
  }
  return true;
}

const REPLY_HINT = "\n\n<i>Ответь на это сообщение (Reply), и ответ уйдёт клиенту.</i>";

async function onMessage(bot, msg) {
  const user = msg.from;
  const isCommand = msg.text?.startsWith("/");

  if ((await bot.ownerIds(user)).includes(user.id)) {
    if (msg.text === "/tiktok") {
      const link = await tiktok.loginLink(bot.env, bot.origin);
      return bot.send(msg.chat.id, link
        ? `Чтобы ролики приходили в черновики TikTok, войди в аккаунт канала по ссылке (действует 15 минут):\n${esc(link)}`
        : "TikTok ещё не настроен: нет секрета TIKTOK_CLIENT_KEY.");
    }
    if (isCommand) {
      await bot.send(msg.chat.id, "👋 Ты владелец бота. Сюда будут приходить заявки и сообщения клиентов. " +
        "Чтобы ответить, нажми на сообщение → «Ответить».");
      return show(bot, msg.chat.id, null, ...mainMenu(), data.owner?.photo);
    }
    const replied = msg.reply_to_message?.message_id;
    // Старые заявки (до нескольких владельцев) записаны без номера чата.
    const client = replied && ((await bot.kv.get(`relay:${msg.chat.id}:${replied}`)) || (await bot.kv.get(`relay:${replied}`)));
    if (!client) return bot.send(msg.chat.id, "Чтобы ответить клиенту, нажми на его сообщение → «Ответить» и напиши текст.");
    await bot.call("copyMessage", { chat_id: Number(client), from_chat_id: msg.chat.id, message_id: msg.message_id });
    await bot.kv.put(`relay:${msg.chat.id}:${msg.message_id}`, client, { expirationTtl: 90 * DAY });
    return bot.send(msg.chat.id, "✅ Отправлено клиенту");
  }

  if (isCommand) return show(bot, msg.chat.id, null, ...mainMenu(), data.owner?.photo);

  const kind = await bot.kv.get(`kind:${user.id}`);
  if (kind) {
    await bot.kv.delete(`kind:${user.id}`);
    const text = esc(msg.text || msg.caption || "(вложение)");
    const ok = await toOwner(bot, msg,
      `📝 <b>Новая заявка: ${ORDER_KINDS[kind] || esc(kind)}</b>\nОт: ${clientLabel(user)}\n\n${text}${REPLY_HINT}`);
    return bot.send(msg.chat.id, ok
      ? `Спасибо! Заявка отправлена. ${esc(data.owner?.name)} ответит прямо здесь, в этом боте, обычно в течение дня. ` +
        "Если захотите что-то добавить, просто напишите сюда."
      : "Спасибо! Сейчас не получилось передать заявку. Напишите, пожалуйста, ещё раз чуть позже.", backToMenu);
  }

  const header = `💬 Сообщение от ${clientLabel(user)}:` + (msg.text ? `\n\n${esc(msg.text)}` : "") + REPLY_HINT;
  if (await toOwner(bot, msg, header)) return bot.send(msg.chat.id, "Сообщение передано, ответ придёт сюда.");
}
