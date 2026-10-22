// Bangladesh Law Assistant UI. Plain JS, no build step, no third-party code:
// the page must work from a laptop with no internet and on a free Space alike.
"use strict";
const $ = id => document.getElementById(id);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c =>
  ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  del(k) { try { localStorage.removeItem(k); } catch (e) {} },
};
const BN_DIGITS = "০১২৩৪৫৬৭৮৯";
const toBn = s => String(s).replace(/\d/g, d => BN_DIGITS[d]);
const isBangla = s => (String(s).match(/[ঀ-৿]/g) || []).length > String(s).length * 0.15;
const MAX_CHARS = 500;

// ------------------------------------------------------------------ strings
const T = {
  en: {
    brand: "Bangladesh Law Assistant", brand2: "বাংলাদেশ আইন সহায়ক",
    h1: "Ask about Bangladeshi law, in Bangla or English",
    lead: "Ask what a section says, or describe your situation. Answers come from the text of the Acts, with every claim linked to the section it relies on.",
    qlabel: "Your question", placeholder2: "Ask another question…", placeholder: "e.g. My landlord wants to evict me without notice. What can I do?  /  দণ্ডবিধির ধারা ৩০২ কী বলে?",
    ask: "Ask", stop: "Stop", settings: "Settings", deep: "Deeper search (several lookups, slower)",
    excerpts: "Excerpts read", model: "Model", hosted: "Your question is sent to an outside provider.",
    trust1: "From the official text of Bangladeshi Acts", trust1n: n => `Searches ${n.toLocaleString("en")} sections of Bangladeshi Acts`,
    trust2: "Every claim cited to a section", trust3: "Free, no sign-up",
    examples: "Try a question", glabel: "General guidance — not from the indexed law text",
    trace: "What the deeper search did", helpful: "Helpful", nothelpful: "Not helpful", copy: "Copy",
    share: "Share", print: "Print", useful: "Was this useful?", yes: "Yes", no: "No", call: "Call",
    eyebrow: "Free · Bangla & English · Cited to the section", enterhint: "Enter to ask · Shift+Enter for a new line",
    answerlabel: "Answer", send: "Send", sources: "Sources from the law",
    aid1: "Need help with your own case?",
    aid2: "Call the government's free legal aid hotline (National Legal Aid Services Organisation), toll-free, or visit the legal aid office at your district judge's court.",
    recent: "Your recent questions", clear: "Clear", how: "How this works",
    how1: "Your question is matched against the sections of Bangladeshi Acts published on the Laws of Bangladesh website, in Bangla and English.",
    how2: "The closest sections are given to a language model, which answers only from them and cites each claim as [n].",
    how3: "Automatic checks confirm every citation points to a real excerpt. If the law text does not cover the question, it says so.",
    disclaimer: "Informational only, not legal advice. Laws change: always check the official text before relying on anything here.",
    official: "Laws of Bangladesh (official)", source: "Source code",
    s_search: "Searching the law", s_read: "Reading sections", s_write: "Writing the answer", s_check: "Re-checking citations", s_guide: "Writing general guidance",
    gnote: "Below is general guidance, not taken from the text of an Act. Check it with a lawyer or the legal aid hotline.",
    notfound: "The indexed law text doesn't answer this.", notfound2: "Try naming the Act or section, or describe the situation in more detail.",
    offtopic: "This assistant only answers questions about Bangladeshi law.",
    degraded: "The answering model is unavailable right now, so here are the sections that match your question.",
    stopped: "Stopped.", error: "Something went wrong", rate: s => `Too many questions at once. Please wait ${s} seconds and try again.`,
    toolong: n => `Please shorten your question to ${n} characters or fewer.`,
    offline: "The answering model is offline. You will still get the matching sections.",
    cited: "cited", notcited: "also retrieved, not cited", official_text: "Official text",
    amended: "amended", repealed: "repealed act", current: "✓ matches the site today", changed: "⚠ changed on the site since indexing",
    repaired: "re-checked once", cached: "instant (cached)", similar: "Answered earlier for a very similar question.",
    similar2: q => `It was: “${q}”. If that is not what you asked, add detail and ask again.`, conf: "confidence", seconds: s => `${s}s`,
    answered_on: d => `Answered on ${d}; the law may have changed since.`,
    confl: {high: "high", medium: "medium", low: "low"},
    fail: {uncited_sentences: "some sentences lack a citation", invalid_citations: "cites a missing excerpt",
           unsupported_claims: "a claim may not be in the excerpts", fabricated_quotes: "a quote is not verbatim",
           language_mismatch: "answered in the other language"},
    thanks: "Thanks, noted.", whatwrong: "What was wrong? (optional)", copied: "Copied.", linkcopied: "Link copied.",
    step: n => `step ${n}`, excerptsplus: n => ` → +${n} excerpts`, agent: (r, n) => `deeper search: ${r} · ${n} steps`,
    // Labels a screen reader announces; they follow the page language like the text.
    skip: "Skip to the question box", l_home: "Bangladesh Law Assistant, home", l_lang: "Language",
    l_theme: "Switch colour theme", l_tabs: "Example questions by area of law", l_progress: "Progress",
    l_helpful: "Helpful", l_nothelpful: "Not helpful", l_aid: "Free legal aid", l_feedback: "Feedback",
    commentlabel: "What was wrong with this answer?", l_source: n => `Source ${n}`,
  },
  bn: {
    brand: "বাংলাদেশ আইন সহায়ক", brand2: "Bangladesh Law Assistant",
    h1: "বাংলাদেশের আইন নিয়ে প্রশ্ন করুন, বাংলায় বা ইংরেজিতে",
    lead: "কোনো ধারা কী বলে জানতে চান, অথবা আপনার পরিস্থিতি লিখুন। উত্তর আসে আইনের মূল পাঠ থেকে, প্রতিটি কথার পাশে সংশ্লিষ্ট ধারার উল্লেখসহ।",
    qlabel: "আপনার প্রশ্ন", placeholder2: "আরেকটি প্রশ্ন লিখুন…", placeholder: "যেমন: বাড়িওয়ালা নোটিশ ছাড়া উচ্ছেদ করতে চায়, আমি কী করতে পারি?  /  What does section 302 of the Penal Code say?",
    ask: "জিজ্ঞাসা করুন", stop: "থামান", settings: "সেটিংস", deep: "গভীর অনুসন্ধান (একাধিক খোঁজ, সময় বেশি লাগে)",
    excerpts: "কতগুলো অংশ পড়বে", model: "মডেল", hosted: "আপনার প্রশ্ন একটি বাইরের সেবাদাতার কাছে পাঠানো হবে।",
    trust1: "বাংলাদেশের আইনের সরকারি পাঠ থেকে", trust1n: n => `বাংলাদেশের আইনের ${toBn(n.toLocaleString("en"))}টি অংশে খোঁজে`,
    trust2: "প্রতিটি কথার সঙ্গে ধারার উল্লেখ", trust3: "বিনামূল্যে, নিবন্ধন লাগে না",
    examples: "একটি প্রশ্ন দিয়ে শুরু করুন", glabel: "সাধারণ দিকনির্দেশনা — সূচিভুক্ত আইনের পাঠ থেকে নয়",
    trace: "গভীর অনুসন্ধানে কী করা হলো", helpful: "উপকারী", nothelpful: "উপকারী নয়", copy: "কপি",
    share: "শেয়ার", print: "প্রিন্ট", useful: "উত্তরটি কি কাজে লেগেছে?", yes: "হ্যাঁ", no: "না", call: "কল করুন",
    eyebrow: "বিনামূল্যে · বাংলা ও ইংরেজি · ধারাসহ উত্তর", enterhint: "Enter চাপলে প্রশ্ন যাবে · নতুন লাইনে Shift+Enter",
    answerlabel: "উত্তর", send: "পাঠান", sources: "আইনের উৎস",
    aid1: "নিজের মামলায় সাহায্য দরকার?",
    aid2: "সরকারের বিনামূল্যের আইনগত সহায়তা হটলাইনে (জাতীয় আইনগত সহায়তা প্রদান সংস্থা) টোল-ফ্রি কল করুন, অথবা আপনার জেলা জজ আদালতের লিগ্যাল এইড অফিসে যান।",
    recent: "আপনার সাম্প্রতিক প্রশ্ন", clear: "মুছুন", how: "এটি কীভাবে কাজ করে",
    how1: "আপনার প্রশ্ন Laws of Bangladesh ওয়েবসাইটে প্রকাশিত বাংলাদেশের আইনের ধারাগুলোর সঙ্গে মিলিয়ে দেখা হয়, বাংলা ও ইংরেজি দুই ভাষাতেই।",
    how2: "সবচেয়ে কাছের ধারাগুলো একটি ভাষা মডেলকে দেওয়া হয়, যা কেবল সেগুলো থেকেই উত্তর দেয় এবং প্রতিটি কথার পাশে [n] আকারে উৎস দেখায়।",
    how3: "স্বয়ংক্রিয় যাচাই নিশ্চিত করে যে প্রতিটি উল্লেখ একটি আসল অংশকে নির্দেশ করে। আইনের পাঠে উত্তর না থাকলে তা স্পষ্ট বলা হয়।",
    disclaimer: "কেবল তথ্যের জন্য, আইনি পরামর্শ নয়। আইন বদলায়: কোনো কিছুর ওপর নির্ভর করার আগে সরকারি পাঠ দেখে নিন।",
    official: "Laws of Bangladesh (সরকারি সাইট)", source: "সোর্স কোড",
    s_search: "আইনে খোঁজা হচ্ছে", s_read: "ধারা পড়া হচ্ছে", s_write: "উত্তর লেখা হচ্ছে", s_check: "উল্লেখ আবার যাচাই", s_guide: "সাধারণ দিকনির্দেশনা লেখা হচ্ছে",
    gnote: "নিচে সাধারণ দিকনির্দেশনা দেওয়া হলো, এটি কোনো আইনের পাঠ থেকে নেওয়া নয়। একজন আইনজীবী বা আইনগত সহায়তা হটলাইনে যাচাই করে নিন।",
    notfound: "সূচিভুক্ত আইনের পাঠে এই প্রশ্নের উত্তর পাওয়া যায়নি।", notfound2: "আইন বা ধারার নাম লিখে দেখুন, অথবা পরিস্থিতি আরও বিস্তারিত লিখুন।",
    offtopic: "এই সহায়ক কেবল বাংলাদেশের আইন বিষয়ক প্রশ্নের উত্তর দেয়।",
    degraded: "উত্তর লেখার মডেল এখন পাওয়া যাচ্ছে না, তাই আপনার প্রশ্নের সঙ্গে মেলে এমন ধারাগুলো দেখানো হলো।",
    stopped: "থামানো হয়েছে।", error: "কিছু একটা ভুল হয়েছে", rate: s => `একসঙ্গে অনেক প্রশ্ন এসেছে। ${toBn(s)} সেকেন্ড পর আবার চেষ্টা করুন।`,
    toolong: n => `প্রশ্নটি ${toBn(n)} অক্ষরের মধ্যে লিখুন।`,
    offline: "উত্তর লেখার মডেল এখন বন্ধ। তবু মিলে যাওয়া ধারাগুলো দেখতে পাবেন।",
    cited: "উল্লেখিত", notcited: "পাওয়া গেছে, উল্লেখ করা হয়নি", official_text: "সরকারি পাঠ",
    amended: "সংশোধিত", repealed: "রহিত আইন", current: "✓ সাইটের বর্তমান পাঠের সঙ্গে মেলে", changed: "⚠ সূচিভুক্তির পর সাইটে বদলেছে",
    repaired: "একবার পুনর্যাচাই", cached: "তাৎক্ষণিক (ক্যাশ)", similar: "খুব কাছাকাছি একটি আগের প্রশ্নের উত্তর দেখানো হচ্ছে।",
    similar2: q => `আগের প্রশ্ন: “${q}”। আপনার প্রশ্নের সঙ্গে না মিললে আরও বিস্তারিত লিখে আবার জিজ্ঞেস করুন।`, conf: "আস্থা", seconds: s => `${toBn(s)} সেকেন্ড`,
    answered_on: d => `উত্তর দেওয়া হয়েছিল ${d}; এরপর আইন বদলে থাকতে পারে।`,
    confl: {high: "উচ্চ", medium: "মাঝারি", low: "নিম্ন"},
    fail: {uncited_sentences: "কিছু বাক্যে উৎস নেই", invalid_citations: "অনুপস্থিত অংশের উল্লেখ",
           unsupported_claims: "কোনো দাবি অংশে না-ও থাকতে পারে", fabricated_quotes: "উদ্ধৃতি হুবহু নয়",
           language_mismatch: "অন্য ভাষায় উত্তর"},
    thanks: "ধন্যবাদ, জানানো হলো।", whatwrong: "কী ভুল ছিল? (ঐচ্ছিক)", copied: "কপি হয়েছে।", linkcopied: "লিংক কপি হয়েছে।",
    step: n => `ধাপ ${toBn(n)}`, excerptsplus: n => ` → +${toBn(n)}টি অংশ`, agent: (r, n) => `গভীর অনুসন্ধান: ${r} · ${toBn(n)} ধাপ`,
    skip: "প্রশ্নের ঘরে যান", l_home: "বাংলাদেশ আইন সহায়ক, প্রথম পাতা", l_lang: "ভাষা",
    l_theme: "রঙের থিম বদলান", l_tabs: "আইনের বিষয় অনুযায়ী উদাহরণ প্রশ্ন", l_progress: "অগ্রগতি",
    l_helpful: "সহায়ক", l_nothelpful: "সহায়ক নয়", l_aid: "বিনামূল্যে আইনি সহায়তা", l_feedback: "মতামত",
    commentlabel: "এই উত্তরে কী ভুল ছিল?", l_source: n => `সূত্র ${toBn(n)}`,
  },
};
let LANG = document.documentElement.lang === "bn" ? "bn" : "en";
const t = (key, ...a) => { const v = T[LANG][key] ?? T.en[key]; return typeof v === "function" ? v(...a) : v; };

// Grouped by area of law, so a first-time visitor sees what the corpus covers.
const EXAMPLES = [
  {ico: "🧭", area: {en: "Your situation", bn: "আপনার পরিস্থিতি"}, qs: [
    "My employer has not paid my wages for two months. What can I do?",
    "বাড়িওয়ালা নোটিশ ছাড়া আমাকে উচ্ছেদ করতে চায়, আমি কী করতে পারি?",
    "কেউ আদালতের আদেশ ছাড়া আমার জমি দখল করেছে, আমি কী করব?",
    "Someone is posting lies about me on Facebook. Is that a crime?"]},
  {ico: "⚖️", area: {en: "Criminal", bn: "ফৌজদারি"}, qs: [
    "দণ্ডবিধির ধারা ৩০২ কী বলে?", "When can the police arrest without a warrant?",
    "What is the punishment for theft?", "জামিনযোগ্য অপরাধ কাকে বলে?"]},
  {ico: "👪", area: {en: "Family", bn: "পারিবারিক"}, qs: [
    "যৌতুকের জন্য স্বামী মারধর করলে কী শাস্তি?", "What are a wife's rights to maintenance?",
    "বাল্যবিবাহের শাস্তি কী?", "What protection does the domestic violence law give?"]},
  {ico: "🛠️", area: {en: "Work", bn: "শ্রম"}, qs: [
    "শ্রমিকের দৈনিক কর্মঘণ্টা কত?", "How much maternity leave does a worker get?",
    "Can my employer fire me without notice?", "ওভারটাইমের মজুরি কীভাবে হিসাব হয়?"]},
  {ico: "🛒", area: {en: "Money & consumers", bn: "অর্থ ও ভোক্তা"}, qs: [
    "What happens if a cheque bounces?", "ত্রুটিপূর্ণ পণ্য বিক্রি করলে ভোক্তা কী করতে পারেন?",
    "A shop charged me more than the printed price. Where do I complain?", "ভেজাল খাদ্য বিক্রির শাস্তি কী?"]},
  {ico: "🛡️", area: {en: "Rights & police", bn: "অধিকার ও পুলিশ"}, qs: [
    "What does Article 27 of the Constitution say?", "গ্রেফতারের পর কতক্ষণের মধ্যে ম্যাজিস্ট্রেটের কাছে হাজির করতে হয়?",
    "How do I request information from a government office?", "সংবিধানে বাকস্বাধীনতা সম্পর্কে কী বলা আছে?"]},
];

// ------------------------------------------------------------------ language
function applyLang(lang) {
  LANG = lang === "bn" ? "bn" : "en";
  document.documentElement.lang = LANG;
  store.set("bdrag-lang", LANG);
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (key === "trust1" && CORPUS) el.textContent = t("trust1n", CORPUS);
    else el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-label]").forEach(el => el.setAttribute("aria-label", t(el.dataset.i18nLabel)));
  $("q").placeholder = t(document.body.classList.contains("answered") ? "placeholder2" : "placeholder");
  document.querySelectorAll(".seg [data-lang]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === LANG)));
  renderTabs();
  renderHistory();
  if (LAST) render(LAST.data, LAST.opts);
}
document.querySelectorAll(".seg [data-lang]").forEach(b => { b.onclick = () => applyLang(b.dataset.lang); });

const isDark = () => document.documentElement.dataset.theme
  ? document.documentElement.dataset.theme === "dark"
  : matchMedia("(prefers-color-scheme: dark)").matches;
$("theme").setAttribute("aria-pressed", String(isDark()));
$("theme").onclick = () => {
  document.documentElement.dataset.theme = isDark() ? "light" : "dark";
  store.set("bdrag-theme", document.documentElement.dataset.theme);
  $("theme").setAttribute("aria-pressed", String(isDark()));
};

// ------------------------------------------------------------------ examples
let TAB = 0;
function renderTabs() {
  // One tab stop for the whole list; arrow keys move between tabs (WAI-ARIA tabs pattern).
  $("tabs").innerHTML = EXAMPLES.map((g, i) =>
    `<button type="button" class="tab" role="tab" id="tab-${i}" aria-controls="exlist" aria-selected="${i === TAB}" tabindex="${i === TAB ? 0 : -1}" data-i="${i}"><span class="ico" aria-hidden="true">${g.ico}</span>${esc(g.area[LANG])}</button>`).join("");
  $("exlist").setAttribute("aria-labelledby", "tab-" + TAB);
  $("exlist").innerHTML = EXAMPLES[TAB].qs.map(q =>
    `<button type="button" class="ex" data-q="${esc(q)}">${esc(q)}</button>`).join("");
}
$("tabs").onclick = e => { const b = e.target.closest("[data-i]"); if (b) { TAB = +b.dataset.i; renderTabs(); } };
$("tabs").addEventListener("keydown", e => {
  const moves = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1};
  let next = null;
  if (e.key in moves) next = (TAB + moves[e.key] + EXAMPLES.length) % EXAMPLES.length;
  else if (e.key === "Home") next = 0;
  else if (e.key === "End") next = EXAMPLES.length - 1;
  if (next === null) return;
  e.preventDefault();
  TAB = next; renderTabs(); $("tab-" + TAB).focus();
});
$("exlist").onclick = e => { const b = e.target.closest("[data-q]"); if (b) { $("q").value = b.dataset.q; grow(); submit(); } };

// ------------------------------------------------------------------ ask box
const box = $("q");
function grow() {
  box.style.height = "auto";
  box.style.height = Math.min(box.scrollHeight, 240) + "px";
  const n = box.value.length;
  $("count").textContent = n > MAX_CHARS - 100 ? `${LANG === "bn" ? toBn(n) : n} / ${LANG === "bn" ? toBn(MAX_CHARS) : MAX_CHARS}` : "";
  $("count").classList.toggle("over", n > MAX_CHARS);
}
box.addEventListener("input", grow);
box.addEventListener("keydown", e => {
  // isComposing: a Bangla IME (Avro, Google input) uses Enter to pick a word.
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); submit(); }
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== box && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
    e.preventDefault(); box.focus();
  }
});
$("f").onsubmit = e => { e.preventDefault(); submit(); };
// The settings popover closes on asking, on Escape and on a click outside it.
document.addEventListener("click", e => { if (!e.target.closest("#settings")) $("settings").open = false; });
document.addEventListener("keydown", e => { if (e.key === "Escape") $("settings").open = false; });

// Model picker: only shown when the server offers more than one answering model.
let MODELS = [];
(async () => {
  try {
    const d = await (await fetch("/models")).json();
    MODELS = d.models || [];
    if (MODELS.length < 2) return;
    $("model").innerHTML = MODELS.map(m => `<option value="${esc(m.id)}">${esc(m.label)}</option>`).join("");
    const saved = store.get("bdrag-model");
    if (saved && MODELS.some(m => m.id === saved)) $("model").value = saved;
    $("modelwrap").hidden = false;
    showHosted();
  } catch (e) { /* older server without /models */ }
})();
function showHosted() {
  const m = MODELS.find(x => x.id === $("model").value);
  $("hosted").hidden = !m || m.local;
}
$("model").onchange = () => { store.set("bdrag-model", $("model").value); showHosted(); };
const chosenModel = () => $("modelwrap").hidden ? undefined : $("model").value;

// What is loaded: corpus size for the trust line, and a banner when the model is down.
let CORPUS = null;
(async () => {
  try {
    const r = await fetch("/health");
    const d = await r.json();
    if (d.chunks) { CORPUS = d.chunks; $("corpusline").textContent = t("trust1n", CORPUS); }
    if (d.status !== "ok" || d.llm_reachable === false) {
      $("banner").innerHTML = `<div class="notice warn">${esc(t("offline"))}</div>`;
      $("banner").hidden = false;
    }
  } catch (e) {}
})();

// ------------------------------------------------------------------ rendering
// Everything below is data from the corpus or the model: escape before it
// touches innerHTML (a section title or a model's output must never become markup).
const safeUrl = u => /^https?:\/\//i.test(u || "") ? esc(u) : "";

function inline(s, bn) {
  return s
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s.,;:)।]|$)/g, "$1<em>$2</em>")
    .replace(/\[([0-9০-৯]{1,2})\]/g, (_, n) => {
      const num = String(n).replace(/[০-৯]/g, d => BN_DIGITS.indexOf(d));
      return `<button type="button" class="cite" data-n="${num}" aria-label="${esc(t("l_source", num))}">${bn ? toBn(num) : num}</button>`;
    });
}

// A small, safe subset of Markdown: what models actually write in answers
// (paragraphs, bullet and numbered lists, bold, headings). Input is escaped first.
function md(text) {
  const bn = isBangla(text);
  const lines = esc(text).replace(/\r/g, "").split("\n");
  let html = "", list = null, para = [];
  const flushPara = () => { if (para.length) { html += `<p>${inline(para.join("<br>"), bn)}</p>`; para = []; } };
  const flushList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if (!line.trim()) { flushPara(); flushList(); continue; }
    if ((m = line.match(/^\s*#{1,4}\s+(.*)$/))) { flushPara(); flushList(); html += `<h3>${inline(m[1], bn)}</h3>`; continue; }
    if ((m = line.match(/^\s*(?:[-*•‣]|–)\s+(.*)$/))) {
      flushPara(); if (list !== "ul") { flushList(); html += "<ul>"; list = "ul"; }
      html += `<li>${inline(m[1], bn)}</li>`; continue;
    }
    if ((m = line.match(/^\s*[0-9০-৯]{1,2}[.)]\s+(.*)$/))) {
      flushPara(); if (list !== "ol") { flushList(); html += "<ol>"; list = "ol"; }
      html += `<li>${inline(m[1], bn)}</li>`; continue;
    }
    if ((m = line.match(/^\s*&gt;\s?(.*)$/))) { flushPara(); flushList(); html += `<blockquote>${inline(m[1], bn)}</blockquote>`; continue; }
    flushList(); para.push(line);
  }
  flushPara(); flushList();
  return html;
}

const STEPS = ["s_search", "s_read", "s_write", "s_check", "s_guide"];
let stepState = {};
function steps(active, done = []) {
  stepState = {active, done};
  const optional = s => s === "s_check" || s === "s_guide";
  const show = active === "s_guide" ? ["s_search", "s_guide"]
    : STEPS.filter(s => !optional(s) || active === s || done.includes(s));
  // Only the current step is visible (CSS); the rest stay in the list for screen readers.
  $("steps").innerHTML = active === null ? "" : show.map(s =>
    `<li class="${done.includes(s) ? "done" : s === active ? "on" : ""}">${esc(t(s))}</li>`).join("");
}

function setNotice(kind, title, body = "") {
  const icon = kind === "bad"
    ? '<svg class="ni" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-2h2zm0-4h-2V7h2z"/></svg>'
    : '<svg class="ni" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z"/></svg>';
  $("notice").innerHTML = title ? `<div class="notice ${kind}" role="status">${icon}<div><b>${esc(title)}</b>${body ? esc(body.trim()) : ""}</div></div>` : "";
}

let SOURCES = new Map();    // n -> source card, as streamed; final marks which are cited
function renderSources(cited = null) {
  const list = [...SOURCES.values()].sort((a, b) =>
    (cited ? (cited.has(b.n) - cited.has(a.n)) : 0) || a.n - b.n);
  $("result").classList.toggle("nosources", !list.length);
  if (!list.length) { $("srcwrap").hidden = true; return; }
  $("srcwrap").hidden = false;
  $("srccount").textContent = LANG === "bn" ? toBn(list.length) : list.length;
  const num = n => LANG === "bn" ? toBn(n) : n;
  $("sources").innerHTML = list.map(s => {
    const uncited = cited && !cited.has(s.n);
    const badges = [
      s.amended ? `<span class="badge warn" title="This section has been changed by a later act; the text shown is the amended one.">${esc(LANG === "bn" ? s.amended.replace("amended", t("amended")).replace("latest", "সর্বশেষ") : s.amended)}</span>` : "",
      s.repealed ? `<span class="badge bad">${esc(t("repealed"))}</span>` : "",
      s.live_check === "current" ? `<span class="badge ok">${esc(t("current"))}</span>` :
        s.live_check === "changed" ? `<span class="badge warn">${esc(t("changed"))}</span>` : "",
    ].join("");
    // "The Penal Code, 1860, section 304A" -> act on a small line, section as the title.
    const cite = String(s.citation || "");
    const act = s.act_title || "";
    const sec = act && cite.startsWith(act) ? cite.slice(act.length).replace(/^[\s,،]+/, "") : cite;
    return `<li><details class="src${uncited ? " uncited" : ""}" id="src-${esc(s.n)}">
      <summary><span class="num">${esc(num(s.n))}</span>
        <span class="meta">${act && sec !== cite ? `<span class="act">${esc(act)}</span>` : ""}
        <span class="cit">${esc(sec || cite)}${s.section_title ? " — " + esc(s.section_title) : ""}</span>
        <span class="tags">${uncited ? `<span class="badge">${esc(t("notcited"))}</span>` : ""}${badges}</span></span>
        <svg class="chev" width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m9 6 6 6-6 6-1.4-1.4L12.2 12 7.6 7.4z"/></svg></summary>
      <div class="body">${s.text ? `<div class="excerpt">${esc(s.text)}</div>` : ""}
        ${safeUrl(s.url) ? `<div class="links"><a href="${safeUrl(s.url)}" target="_blank" rel="noopener">${esc(t("official_text"))} ↗</a></div>` : ""}
      </div></details></li>`;
  }).join("");
}

function openSource(n, focus = false) {
  const el = $("src-" + n);
  if (!el) return;
  // From the keyboard (Enter or Space on a citation), focus follows to the source.
  if (focus) el.querySelector("summary").focus({preventScroll: true});
  el.open = true;
  const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  const col = $("srcwrap");
  if (getComputedStyle(col).position === "sticky") {
    // Side-by-side layout: scroll the sources column only, keep the answer in view.
    col.scrollTo({top: Math.max(0, el.offsetTop - 44), behavior});
  } else {
    el.scrollIntoView({behavior, block: "start"});
  }
  el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
}
document.addEventListener("click", e => { const c = e.target.closest(".cite"); if (c) openSource(c.dataset.n, e.detail === 0); });

function badge(text, cls = "", title = "") {
  const b = document.createElement("span");
  b.className = "badge " + cls; b.textContent = text; if (title) b.title = title;
  $("badges").appendChild(b);
}

let LAST = null, currentId = null;
const refusalText = s => String(s || "").replace(/^NOT_FOUND:\s*/, "");

function render(d, opts = {}) {
  LAST = {data: d, opts};
  $("skeleton").hidden = true;
  $("answer").classList.remove("caret");
  setNotice("", "");
  if (d.degraded) {
    setNotice("bad", t("degraded"));
    $("answer").innerHTML = "";
    SOURCES = new Map((d.sources || []).map(s => [s.n, s]));
    renderSources();
    document.querySelectorAll(".src").forEach((el, i) => { if (i < 2) el.open = true; });
  } else if (d.refused) {
    const off = d.abstained && !(d.sources || []).length && /outside the corpus|সংগ্রহের বাইরে/.test(d.answer || "");
    setNotice("warn", off ? t("offtopic") : t("notfound"), off ? "" : " " + t("notfound2"));
    const why = refusalText(d.answer);
    $("answer").innerHTML = why && !off ? `<p class="refusal">${esc(why)}</p>` : "";
  } else if (d.general_guidance) {
    // Nothing in the indexed law matched, so the server wrote general guidance
    // instead: keep it visibly apart from cited answers.
    setNotice("warn", t("notfound"), " " + t("gnote"));
    $("answer").innerHTML = "";
  } else if (d.answer || d.error) {
    $("answer").innerHTML = md(d.answer || d.error || "");
    // Served from the paraphrase cache: say which question it answered.
    if (d.cache_match) setNotice("warn", t("similar"), " " + t("similar2", d.cache_match.question));
  }
  $("guidance").hidden = !d.general_guidance;
  $("gtext").innerHTML = d.general_guidance ? md(d.answer || "") : "";

  if (!d.degraded) {
    const cited = new Set((d.sources || []).map(s => s.n));
    (d.sources || []).forEach(s => SOURCES.set(s.n, {...(SOURCES.get(s.n) || {}), ...s}));
    if ((d.refused || d.general_guidance) && !(d.sources || []).length) SOURCES = new Map();
    renderSources(cited.size ? cited : null);
  }
  steps(null);                 // finished: the badges below say what happened

  $("badges").innerHTML = "";
  if (d.repaired) badge(t("repaired"), "warn");
  (d.failures || []).forEach(f => badge(t("fail")[f] || f.replace(/_/g, " "), "bad"));
  if (d.cached && !opts.fromPermalink) badge(t("cached"));
  if (opts.fromPermalink && d.created) {
    // A shared answer quotes the law as it stood that day: say which day.
    const day = new Date(d.created * 1000).toLocaleDateString(LANG === "bn" ? "bn-BD" : "en-GB",
      {year: "numeric", month: "long", day: "numeric"});
    badge(t("answered_on", day), "warn");
  }
  if (d.stop_reason) badge(t("agent", d.stop_reason, (d.trace || []).length));
  if (d.latency_s && !d.cached) badge(t("seconds", Math.round(d.latency_s * 10) / 10));
  if (d.confidence) {
    const c = d.confidence.label;
    badge(`${t("conf")}: ${(T[LANG].confl || {})[c] || c}`, c === "high" ? "ok" : c === "medium" ? "warn" : "bad",
          (d.confidence.why || []).join("; "));
  }
  if (d.trace && d.trace.length) {
    $("tracewrap").hidden = false;
    $("trace").innerHTML = d.trace.map(x =>
      `<li>${esc(t("step", x.step))}: ${esc(x.tool || x.type)}${x.parallel > 1 ? " ×" + esc(x.parallel) : ""}` +
      `${x.new_excerpts != null ? esc(t("excerptsplus", x.new_excerpts)) : ""}</li>`).join("");
  } else { $("tracewrap").hidden = true; }
  currentId = d.id || null;
  $("actions").hidden = !(d.answer || d.degraded);
  $("fbup").hidden = $("fbdown").hidden = !currentId;
  $("share").hidden = !currentId;
  if (currentId && !opts.fromPermalink && location.pathname !== "/a/" + currentId) {
    try { history.replaceState(null, "", "/a/" + currentId); } catch (e) {}
  }
}

// ------------------------------------------------------------------ asking
let controller = null;

function busy(on) {
  // A screen reader waits for the whole answer instead of reading each streamed token.
  document.querySelector(".answercard").setAttribute("aria-busy", String(on));
  $("go").disabled = on;
  $("stop").hidden = !on;
}

function startView(question) {
  $("settings").open = false;
  document.body.classList.add("answered");
  // The question moves to the heading above the answer; the box is free for the next one.
  box.value = ""; grow(); box.placeholder = t("placeholder2");
  $("result").hidden = false;
  $("qecho").textContent = question;
  $("answer").innerHTML = "";
  $("guidance").hidden = true; $("gtext").innerHTML = "";
  $("badges").innerHTML = ""; $("tracewrap").hidden = true;
  $("actions").hidden = true; $("fbform").hidden = true; $("fbmsg").textContent = "";
  $("fbup").setAttribute("aria-pressed", "false"); $("fbdown").setAttribute("aria-pressed", "false");
  setNotice("", "");
  SOURCES = new Map(); renderSources();
  $("skeleton").hidden = false;
  steps("s_search");
  LAST = null; currentId = null;
}

async function failed(r) {
  let d = {};
  try { d = await r.json(); } catch (e) {}
  if (r.status === 429 && d.retry_after_s != null) return t("rate", Math.ceil(d.retry_after_s));
  return d.error || `${t("error")} (${r.status})`;
}

async function submit() {
  const question = box.value.trim();
  if (!question || $("go").disabled) return;
  if (question.length > MAX_CHARS) {
    startView(question); box.value = question; grow();      // keep the text so it can be shortened
    steps(null); $("skeleton").hidden = true; setNotice("warn", t("toolong", MAX_CHARS)); return;
  }
  startView(question);
  rememberQ(question);
  busy(true);
  controller = new AbortController();
  const useAgent = $("agent").checked, k = +$("k").value || 5;
  try {
    // The agent makes several calls and has nothing to stream in between, so it
    // uses the plain endpoint; single-shot answers stream token by token.
    if (useAgent) {
      steps("s_search");
      const r = await fetch("/ask", {method: "POST", headers: {"content-type": "application/json"}, signal: controller.signal,
        body: JSON.stringify({question, k, agent: true, model: chosenModel()})});
      if (!r.ok && r.status !== 503) { $("skeleton").hidden = true; steps(null); setNotice("bad", await failed(r)); }
      else render(await r.json());
    } else {
      await stream(question, k);
    }
  } catch (e) {
    $("skeleton").hidden = true; $("answer").classList.remove("caret");
    if (e.name === "AbortError") { setNotice("warn", t("stopped")); steps(null); }
    else { setNotice("bad", t("error"), ": " + e.message); steps(null); }
  }
  busy(false);
  controller = null;
}
$("stop").onclick = () => { if (controller) controller.abort(); };

async function stream(question, k) {
  const r = await fetch("/ask/stream", {method: "POST", headers: {"content-type": "application/json"},
    signal: controller.signal, body: JSON.stringify({question, k, model: chosenModel()})});
  if (!r.ok) {
    if (r.status === 503) { render(await r.json()); return; }
    $("skeleton").hidden = true; steps(null); setNotice("bad", await failed(r)); return;
  }
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "", text = "", frame = 0;
  const paint = () => { frame = 0; $("answer").innerHTML = md(text); };
  // A frame still queued from streamed tokens must not repaint over a repair or the final answer.
  const cancelPaint = () => { if (frame) cancelAnimationFrame(frame); frame = 0; };
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += dec.decode(value, {stream: true});
    const parts = buf.split("\n\n"); buf = parts.pop();
    for (const part of parts) {
      const ev = (part.match(/^event: (.*)$/m) || [])[1];
      let data = {};
      try { data = JSON.parse((part.match(/^data: (.*)$/m) || [, "{}"])[1]); } catch (e) { continue; }
      if (ev === "status") {
        if (data.stage === "retrieving") steps("s_search");
        else if (data.stage === "answering") steps("s_write", ["s_search", "s_read"]);
        else if (data.stage === "repairing") { steps("s_check", ["s_search", "s_read", "s_write"]); cancelPaint(); text = ""; paint(); }
        else if (data.stage === "general_guidance") {
          // The streamed draft was a "not found"; the guidance replaces it in "final".
          cancelPaint(); text = ""; paint(); $("skeleton").hidden = false;
          steps("s_guide", ["s_search"]);
        }
      } else if (ev === "sources") {
        steps("s_read", ["s_search"]);
        (data.sources || []).forEach(s => SOURCES.set(s.n, s));
        renderSources();
      } else if (ev === "token") {
        $("skeleton").hidden = true; $("answer").classList.add("caret");
        text += data.text || "";
        if (!frame) frame = requestAnimationFrame(paint);
      } else if (ev === "final") {
        cancelPaint();
        render(data);
      } else if (ev === "error") {
        $("skeleton").hidden = true; steps(null); setNotice("bad", t("error"), ": " + (data.error || ""));
      }
    }
  }
}

// ------------------------------------------------------------------ actions
async function sendFeedback(rating, comment = "") {
  if (!currentId) return;
  try {
    await fetch("/feedback", {method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({id: currentId, rating, comment})});
    $("fbmsg").textContent = t("thanks");
  } catch (e) {}
}
$("fbup").onclick = () => {
  $("fbup").setAttribute("aria-pressed", "true"); $("fbdown").setAttribute("aria-pressed", "false");
  $("fbform").hidden = true; sendFeedback("up");
};
$("fbdown").onclick = () => {
  $("fbdown").setAttribute("aria-pressed", "true"); $("fbup").setAttribute("aria-pressed", "false");
  $("fbcomment").placeholder = t("whatwrong"); $("fbform").hidden = false; $("fbcomment").focus();
};
$("fbform").onsubmit = e => { e.preventDefault(); $("fbform").hidden = true; sendFeedback("down", $("fbcomment").value.trim()); };

async function copy(text, msg) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
    ta.select(); try { document.execCommand("copy"); } catch (e2) {} ta.remove();
  }
  $("fbmsg").textContent = msg;
}
$("copytext").onclick = () => {
  const cited = [...SOURCES.values()].filter(s => !LAST || (LAST.data.sources || []).some(x => x.n === s.n))
    .map(s => `[${s.n}] ${s.citation}${s.url ? " " + s.url : ""}`).join("\n");
  const body = [$("qecho").textContent, $("answer").innerText.trim(), $("guidance").hidden ? "" : $("gtext").innerText.trim(), cited,
    t("disclaimer")].filter(Boolean).join("\n\n");
  copy(body, t("copied"));
};
$("share").onclick = async () => {
  if (!currentId) return;
  const url = location.origin + "/a/" + currentId;
  if (navigator.share) { try { await navigator.share({title: $("qecho").textContent, url}); return; } catch (e) { if (e.name === "AbortError") return; } }
  copy(url, t("linkcopied"));
};
$("print").onclick = () => window.print();

// ------------------------------------------------------------------ history
function getHistory() { try { return JSON.parse(store.get("bdrag-history", "[]")) || []; } catch (e) { return []; } }
function rememberQ(q) {
  const h = [q, ...getHistory().filter(x => x !== q)].slice(0, 8);
  store.set("bdrag-history", JSON.stringify(h));
  renderHistory();
}
function renderHistory() {
  const h = getHistory();
  $("history").hidden = !h.length;
  $("hlist").innerHTML = h.map(q => `<li><button type="button" class="q" data-q="${esc(q)}" title="${esc(q)}">${esc(q)}</button></li>`).join("");
}
$("hlist").onclick = e => { const b = e.target.closest("[data-q]"); if (b) { box.value = b.dataset.q; grow(); window.scrollTo({top: 0}); submit(); } };
$("hclear").onclick = () => { store.del("bdrag-history"); renderHistory(); };

// ------------------------------------------------------------------ start
applyLang(LANG);
grow();

// Open a permalink directly: /a/<id> renders that stored answer.
(async () => {
  const m = location.pathname.match(/^\/a\/(\w+)/);
  if (!m) { if (matchMedia("(min-width: 700px)").matches) box.focus(); return; }
  try {
    const r = await fetch("/a/" + m[1] + "?format=json", {headers: {accept: "application/json"}});
    if (!r.ok) { history.replaceState(null, "", "/"); return; }
    const d = await r.json();
    startView(d.question || "");
    render(d, {fromPermalink: true});
  } catch (e) {}
})();
