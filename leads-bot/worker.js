// Бот заявок: помощник для переписки с заказчиком.
//
// Заявки с откликами присылает leads/finder.py. Когда заказчик ответил, жмёшь под откликом
// «💬 Мне ответили» (или просто присылаешь сюда свой отклик), потом присылаешь ответ заказчика,
// и бот через бесплатный Gemini предлагает, что написать дальше. Можно продолжать диалог:
// каждый новый ответ заказчика сюда, и бот учитывает всю переписку.

const DAY = 24 * 3600;
const GEMINI_API = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions";
const MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.8-flash"];

const HELP =
  "Я помогаю отвечать заказчикам.\n\n" +
  "1. Под каждым откликом есть кнопка «💬 Мне ответили». Нажми её, когда заказчик ответит.\n" +
  "   Или просто пришли сюда текст своего отклика.\n" +
  "2. Пришли, что ответил заказчик: скопируй текст или перешли его сообщения.\n" +
  "3. Я предложу ответ. Нажми на текст, чтобы скопировать, поправь под себя и отправь.\n\n" +
  "Заказчик написал ещё? Просто пришли его новое сообщение, я помню переписку.\n" +
  "/new начать новый диалог.\n\n" +
  "Чтобы Telegram не дал спам-блок: пиши первым не больше 10-15 новым людям в день, " +
  "не отправляй один и тот же текст всем, ссылки и @бота давай только после ответа заказчика.";

const ANSWER_BUTTONS = {
  inline_keyboard: [[
    { text: "🔄 Другой вариант", callback_data: "again" },
    { text: "🆕 Новый диалог", callback_data: "new" },
  ]],
};

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("Бот заявок работает");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== (await webhookSecret(env.BOT_TOKEN))) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    // Ответ Gemini может занять десяток секунд: Telegram отвечаем сразу, работу доделываем в фоне.
    ctx.waitUntil(handle(env, update).catch((e) => console.error("Ошибка", e.stack || e)));
    return new Response("ok");
  },
};

async function handle(env, update) {
  const owners = String(env.OWNER_ID || "").split(",").map((s) => s.trim()).filter(Boolean);
  const from = update.callback_query?.from || update.message?.from;
  if (!from || !owners.includes(String(from.id))) return;
  const tg = (method, params) => call(env, method, params);
  if (update.callback_query) return onButton(env, tg, update.callback_query);
  const msg = update.message;
  if (msg?.chat?.type === "private" && (msg.text || msg.caption)) return onMessage(env, tg, msg);
}

const key = (chat) => `dlg:${chat}`;
async function load(env, chat) {
  return JSON.parse((await env.STATE.get(key(chat))) || "null") || { history: [] };
}
function save(env, chat, dlg) {
  dlg.history = dlg.history.slice(-30);
  return env.STATE.put(key(chat), JSON.stringify(dlg), { expirationTtl: 14 * DAY });
}

async function onButton(env, tg, q) {
  const chat = q.message.chat.id;
  await tg("answerCallbackQuery", { callback_query_id: q.id }).catch(() => {});
  if (q.data === "answered") {
    // Текст отклика берём прямо из сообщения, под которым нажата кнопка.
    const mine = (q.message.text || "").trim();
    await save(env, chat, { history: [{ who: "me", text: mine }] });
    return send(tg, chat, "Пришли, что ответил заказчик: скопируй его текст или перешли сообщения сюда.");
  }
  if (q.data === "new") {
    await env.STATE.delete(key(chat));
    return send(tg, chat, "Новый диалог. Пришли свой первый отклик (или нажми «💬 Мне ответили» под откликом).");
  }
  if (q.data === "again" || q.data === "suggest") {
    const dlg = await load(env, chat);
    if (!dlg.history.some((m) => m.who === "client")) {
      return send(tg, chat, "Сначала пришли, что ответил заказчик.");
    }
    if (q.data === "again") dlg.avoid = [...(dlg.avoid || []), dlg.pending].filter(Boolean).slice(-3);
    return suggest(env, tg, chat, dlg);
  }
}

async function onMessage(env, tg, msg) {
  const chat = msg.chat.id;
  const text = (msg.text || msg.caption || "").trim();
  if (/^\/(start|help)\b/.test(text)) return send(tg, chat, HELP);
  if (/^\/new\b/.test(text)) {
    await env.STATE.delete(key(chat));
    return send(tg, chat, "Новый диалог. Пришли свой первый отклик.");
  }
  if (text.startsWith("/")) return send(tg, chat, HELP);

  const dlg = await load(env, chat);
  // Пересланные сообщения: свои считаем моими репликами, чужие репликами заказчика.
  const origin = msg.forward_origin;
  if (origin) {
    const mine = origin.type === "user" && String(origin.sender_user?.id) === String(msg.from.id);
    commitPending(dlg, mine);
    dlg.history.push({ who: mine ? "me" : "client", text });
    // Пересылка приходит пачкой отдельных сообщений: не отвечаем на каждое, а обновляем одно.
    const n = dlg.history.length;
    const note = `В переписке ${n} ${plural(n)}. Перешли ещё или нажми кнопку.`;
    const markup = { inline_keyboard: [[{ text: "✍️ Подобрать ответ", callback_data: "suggest" }]] };
    if (dlg.status) {
      const ok = await tg("editMessageText", { chat_id: chat, message_id: dlg.status, text: note, reply_markup: markup })
        .then(() => true).catch(() => false);
      if (ok) return save(env, chat, dlg);
    }
    const sent = await tg("sendMessage", { chat_id: chat, text: note, reply_markup: markup });
    dlg.status = sent.message_id;
    return save(env, chat, dlg);
  }
  dlg.status = null;
  if (!dlg.history.length) {
    // Диалога ещё нет: это мой отклик, ждём ответ заказчика.
    await save(env, chat, { history: [{ who: "me", text }] });
    return send(tg, chat, "Запомнил твой отклик. Теперь пришли, что ответил заказчик.");
  }
  // Диалог идёт: это новое сообщение заказчика. Предложенный раньше ответ считаем отправленным.
  commitPending(dlg, false);
  dlg.history.push({ who: "client", text });
  return suggest(env, tg, chat, dlg);
}

function commitPending(dlg, mineNext) {
  // Если я сам пересылаю свою реплику, она точнее предложенного варианта.
  if (dlg.pending && !mineNext) dlg.history.push({ who: "me", text: dlg.pending });
  dlg.pending = null;
  dlg.avoid = [];
}

async function suggest(env, tg, chat, dlg) {
  await tg("sendChatAction", { chat_id: chat, action: "typing" }).catch(() => {});
  const answer = await ask(env, dlg);
  if (!answer) {
    await save(env, chat, dlg);
    return send(tg, chat, "Gemini сейчас не ответил. Нажми «🔄 Другой вариант» через минуту.",
      { inline_keyboard: [[{ text: "🔄 Другой вариант", callback_data: "again" }]] });
  }
  dlg.pending = answer.reply;
  dlg.status = null;
  await save(env, chat, dlg);
  let out = `Ответ заказчику (нажми, чтобы скопировать):\n\n<code>${esc(answer.reply)}</code>`;
  if (answer.warn) out += `\n\n⚠️ ${esc(answer.warn)}`;
  if (/\[[^\]]+\]/.test(answer.reply)) out += "\n\n✏️ Впиши свои данные вместо [квадратных скобок].";
  return send(tg, chat, out, ANSWER_BUTTONS);
}

const FACTS =
  "Я Hazzer, фрилансер: делаю Telegram-ботов (оплата через СБП, карту, крипту; личный кабинет; админка в боте; " +
  "рассылки; статистика) и сайты, лендинги (адаптив, формы заявок, оплата, заявки в Telegram). " +
  "Сделал два бота для продажи VPN-подписок с автовыдачей доступа, заказчики поставили 5 звёзд. " +
  "Делаю ботов для онлайн-школ: оплата и выдача доступа в закрытый канал. " +
  "Примеры работ и отзывы собраны в боте @PortfolioHazzer_bot.";

async function ask(env, dlg) {
  if (!env.GEMINI_API_KEY) return null;
  const portfolioSent = dlg.history.some((m) => m.who === "me" && m.text.includes("@PortfolioHazzer_bot"));
  const chatLog = dlg.history.map((m) => `${m.who === "me" ? "Я" : "Заказчик"}: ${m.text}`).join("\n\n");
  const avoid = (dlg.avoid || []).length
    ? `\n\nНе повторяй эти варианты, напиши по-другому:\n${dlg.avoid.join("\n---\n")}` : "";
  const prompt =
    "Помоги фрилансеру ответить заказчику в личке Telegram. Ниже факты обо мне и переписка. " +
    "Напиши мой следующий ответ на последнее сообщение заказчика.\n" +
    "Правила: по-русски, на «вы», коротко (1-4 предложения), как пишет живой вежливый человек, без канцелярита, " +
    "без эмодзи, без давления и рекламных слов. Отвечай по сути на вопросы заказчика. " +
    "О себе только факты ниже, ничего не выдумывай. Цены и сроки не придумывай: если заказчик их спрашивает, " +
    "а данных не хватает, задай 1-2 уточняющих вопроса или поставь заготовку в квадратных скобках, например [цена] или [срок]. " +
    (portfolioSent ? "Ссылку на портфолио уже давал, не повторяй её. "
      : "Если уместно, один раз предложи посмотреть работы и отзывы в @PortfolioHazzer_bot. ") +
    "Других ссылок и @ не добавляй. Предоплату или работу без оплаты не обещай.\n" +
    "Формат ответа: только текст сообщения. Если в переписке есть признаки обмана (просят заплатить тебе, " +
    "скачать файл, перейти на сомнительный сайт, сделать бесплатное «тестовое» целиком), добавь в конце " +
    "отдельную строку, начинающуюся с «⚠️», с коротким предупреждением для меня.\n\n" +
    `Факты обо мне: ${FACTS}\n\nПереписка:\n${chatLog.slice(-6000)}${avoid}`;
  for (const model of MODELS) {
    for (const wait of [0, 2000]) {
      if (wait) await new Promise((r) => setTimeout(r, wait));
      try {
        const res = await fetch(GEMINI_API, {
          method: "POST",
          headers: { authorization: `Bearer ${env.GEMINI_API_KEY}`, "content-type": "application/json" },
          body: JSON.stringify({ model, temperature: 0.8, max_tokens: 1000, messages: [{ role: "user", content: prompt }] }),
        });
        if (!res.ok) {
          console.error(`${model}: ${res.status} ${(await res.text()).slice(0, 200)}`);
          if (![429, 500, 502, 503, 504].includes(res.status)) break;
          continue;
        }
        const raw = ((await res.json()).choices?.[0]?.message?.content || "").trim();
        const lines = raw.split("\n");
        const warnAt = lines.findIndex((l) => l.trim().startsWith("⚠️"));
        const warn = warnAt >= 0 ? lines.slice(warnAt).join(" ").replace(/^\s*⚠️\s*/, "").trim() : "";
        let reply = (warnAt >= 0 ? lines.slice(0, warnAt) : lines).join("\n").trim().replace(/^["«]|["»]$/g, "");
        // Лишние ссылки и чужие @ в ответе: перегенерируем следующей моделью.
        const mentions = (reply.match(/@\w+/g) || []).filter((m) => m !== "@PortfolioHazzer_bot");
        if (reply.length < 10 || reply.length > 1200 || mentions.length || /https?:|t\.me\//.test(reply)) break;
        return { reply, warn };
      } catch (e) {
        console.error(`${model}: ${e}`);
      }
    }
  }
  return null;
}

function send(tg, chat_id, text, reply_markup) {
  return tg("sendMessage", { chat_id, text, reply_markup, parse_mode: "HTML", disable_web_page_preview: true });
}

async function call(env, method, params) {
  const res = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  const json = await res.json();
  if (!json.ok) throw new Error(`${method}: ${json.description}`);
  return json.result;
}

function plural(n) {
  const d = n % 10, h = n % 100;
  if (d === 1 && h !== 11) return "сообщение";
  if (d >= 2 && d <= 4 && (h < 12 || h > 14)) return "сообщения";
  return "сообщений";
}

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function webhookSecret(token) {
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}
