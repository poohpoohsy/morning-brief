"""Mute rules: a fake rule drops a story, and the Not-for-me link is prefilled.

No network. The button is checked by running the page's own script.
"""

import json
import shutil
import subprocess
import tempfile
import threading
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import build


ROOT = Path(__file__).resolve().parent
ENSEMBLE = {
    "title": "Project Ensemble tokenised deposits go live",
    "source": "Fintech News HK",
    "url": "https://fintechnews.hk/ensemble",
    "published": "14 Nov 09:00",
    "snippet": "HKMA sandbox for tokenised deposits.",
}
HIBOR = {
    "title": "HIBOR rises as the aggregate balance falls",
    "source": "RTHK 財經",
    "url": "https://rthk.hk/hibor",
    "published": "14 Nov 08:00",
    "snippet": "Overnight rates moved.",
}
FAKE_RULE = {
    "id": "fake-ensemble",
    "section": "Work",
    "keys": ["work"],
    "hide_section": False,
    "sources": [],
    "terms": ["ensemble", "tokenised"],
    "titles": [],
}


def check(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)


def test_fake_rule_drops_item_before_the_model():
    rules = [build.normalize_rule(FAKE_RULE)]
    collected, payload, stats = build.candidates_for_model(
        {"work": [ENSEMBLE, HIBOR]}, rules)
    titles = [item["title"] for group in collected["work"] for item in group]
    check(titles == [HIBOR["title"]], "work should keep only the HIBOR story")
    check(stats["dropped"] == 1, "one work item should be counted as muted")
    work_blob = json.dumps(payload["work"], ensure_ascii=False)
    check("Ensemble" not in work_blob, "muted story must not be in the model payload")
    check("tokenised" not in work_blob.casefold(), "muted terms must not reach the model")
    check("HIBOR" in work_blob, "the other work story is still sent")
    prompt = build.render_prompt(payload)
    check("Project Ensemble" not in prompt, "prompt text must omit the muted story")
    full = build.render_prompt({"work": [[ENSEMBLE], [HIBOR]]})
    check(len(prompt) < len(full), "dropping the story should shrink the prompt")
    # Same story in another section is not this rule's concern.
    other, _, _ = build.candidates_for_model({"juicy_hk": [ENSEMBLE]}, rules)
    juicy = [item["title"] for group in other["juicy_hk"] for item in group]
    check(juicy == [ENSEMBLE["title"]], "a Work rule must not mute Juicy")


def test_whole_section_is_hidden_and_not_sent():
    rules = [build.normalize_rule({
        "id": "fake-juicy",
        "section": "Juicy",
        "keys": ["juicy_hk", "juicy_sg"],
        "hide_section": True,
        "sources": [],
        "terms": [],
        "titles": [],
    })]
    collected, payload, stats = build.candidates_for_model(
        {"juicy_hk": [ENSEMBLE], "juicy_sg": [HIBOR], "work": [HIBOR]}, rules)
    check(collected["juicy_hk"] == [] and collected["juicy_sg"] == [], "juicy is empty")
    check("juicy_hk" not in payload and "juicy_sg" not in payload, "hidden sections are omitted")
    check("juicy_hk" in stats["hidden"] and "juicy_sg" in stats["hidden"], "hidden keys recorded")
    check(build.hidden_section_labels(rules) == ["Juicy"], "page hides the Juicy block")
    rendered = build.filter_output(
        {"juicy_hk": [{"headline": "still here", "sources": []}], "work": [{"headline": "HIBOR rises", "title": HIBOR["title"], "sources": []}]},
        rules,
    )
    check(rendered["juicy_hk"] == [], "model output for a hidden section is discarded")
    check(rendered["work"], "work output stays")
    prompt = build.render_prompt(payload, muted_keys=stats["hidden"])
    check("Do not write these muted sections: juicy_hk, juicy_sg." in prompt, "prompt names the muted sections")
    check("Ensemble" not in prompt, "hidden section text is not in the prompt")
    quiet = build.render_prompt({"work": [[{"title": "HIBOR rises"}]]}, skip_talking=True)
    check("exactly three keys" not in quiet, "a muted Talking points section stays out of the prompt")
    check("Do not include a talking_points key." in quiet, "prompt no longer asks for talking points")
    check(len(quiet) < len(build.render_prompt({"work": [[{"title": "HIBOR rises"}]]})),
          "skipping talking points should shrink the prompt")


def test_source_rule_is_section_scoped():
    rules = [build.normalize_rule({
        "id": "fake-source",
        "section": "Small Talk",
        "keys": ["smalltalk_hk", "smalltalk_sg"],
        "hide_section": False,
        "sources": ["The Independent SG"],
        "terms": [],
        "titles": [],
    })]
    item = {"title": "MAS holds a briefing", "source": "The Independent SG", "url": "https://ex.sg/a", "snippet": ""}
    other = {"title": "MAS holds a briefing", "source": "The Independent SG", "url": "https://ex.sg/b", "snippet": ""}
    check(build.item_is_muted(item, rules, "smalltalk_sg"), "source matches in Small Talk")
    check(not build.item_is_muted(other, rules, "work"), "same source stays in Work")
    check(not build.item_is_muted(
        {"title": "Budget day", "source": "news.gov.hk", "url": "https://ex.hk", "snippet": ""},
        rules, "smalltalk_hk"), "a different source stays")


def test_deleted_issue_rule_survives():
    saved = [build.normalize_rule({
        "id": "issue:3",
        "issue": 3,
        "section": "Personal",
        "keys": ["personal_hk", "personal_sg"],
        "hide_section": False,
        "sources": ["HK01 香港01"],
        "terms": [],
        "titles": [],
    })]
    # The issue is gone. The next sync only has a new issue.
    incoming = [build.normalize_rule({
        "id": "issue:9",
        "issue": 9,
        "section": "Work",
        "keys": ["work"],
        "hide_section": False,
        "terms": ["sandbox"],
        "sources": [],
        "titles": [],
    })]
    merged = build.merge_rules(saved, incoming)
    ids = [r["id"] for r in merged]
    check(ids == ["issue:3", "issue:9"], "deleted issue 3 stays, new issue 9 is added")
    # Editing issue 9 replaces that rule and still keeps issue 3.
    updated = [dict(incoming[0], terms=["sandbox", "licence"])]
    merged = build.merge_rules(merged, updated)
    issue9 = [r for r in merged if r["id"] == "issue:9"][0]
    check(issue9["terms"] == ["sandbox", "licence"], "an edited issue updates its rule")
    check(any(r["id"] == "issue:3" for r in merged), "the saved rule is still there")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mute_rules.json"
        build.save_rules(merged, path)
        loaded = build.load_saved_rules(path)
        check([r["id"] for r in loaded] == ["issue:3", "issue:9"], "rules round-trip through the file")


def test_issue_body_parsing():
    body = "\n".join([
        "Mute this from future briefs.",
        "",
        "Section: Work",
        "Source: Fintech News HK",
        "Link: https://fintechnews.hk/ensemble",
        "Title: Project Ensemble tokenised deposits go live",
        "",
        "Key terms: ensemble, tokenised",
        "",
        "- [ ] Mute this source in this section",
        "- [ ] Mute these words",
        "- [ ] Mute the whole section",
    ])
    rule = build.normalize_rule(build.parse_mute_body(body))
    check(rule["keys"] == ["work"], "unticked issue applies to Work")
    check(rule["terms"] == ["ensemble", "tokenised"], "unticked boxes mute the key terms")
    check(rule["sources"] == [] and rule["hide_section"] is False, "unticked boxes add no extra scope")
    check(build.item_is_muted(ENSEMBLE, [rule], "work"), "that rule removes the story")
    check(not build.item_is_muted(HIBOR, [rule], "work"), "a different story stays")

    ticked = body.replace("- [ ] Mute this source", "- [x] Mute this source").replace(
        "- [ ] Mute the whole section", "- [x] Mute the whole section")
    # Words box stays unticked, and a ticked box means we do not also default to words.
    wide = build.parse_mute_body(ticked)
    check(wide["hide_section"] and wide["sources"] == ["Fintech News HK"], "ticked boxes apply")
    check(wide["terms"] == [], "an unticked words box is not added when another box is ticked")

    whole = build.parse_mute_body("\n".join([
        "Section: Talking points",
        "Source: RTHK 財經",
        "Link: https://rthk.hk/x",
        "Title: 外匯基金",
        "Key terms: 外匯基金",
        "- [x] Mute the whole section",
    ]))
    check(whole["keys"] == ["talking_points"] and whole["hide_section"], "whole section parses")
    check(build.section_hidden([build.normalize_rule(whole)], "talking_points"), "talking points hidden")

    check(build.parse_mute_body("Hello\nKey terms: bank\n- [x] Mute these words") is None,
          "an issue with no section is left alone")


def test_button_url_from_the_page():
    node = shutil.which("node")
    check(node, "node is required to execute the page script")
    spec = {
        "repo": "poohpoohsy/morning-brief",
        "section": "Work",
        "item": {
            "title": ENSEMBLE["title"],
            "source": ENSEMBLE["source"],
            "url": ENSEMBLE["url"],
            "sources": [{"name": ENSEMBLE["source"], "url": ENSEMBLE["url"]}],
        },
    }
    script = r'''
const fs = require("fs");
const vm = require("vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const found = html.match(/<script>([\s\S]*?)<\/script>/);
if (!found) process.exit(2);
const script = found[1].split(/\nfetch\(/)[0];
const context = {
  console, URL, URLSearchParams, Intl,
  document: { getElementById() { return { textContent: "", innerHTML: "", classList: { add() {} } }; } },
};
vm.createContext(context);
vm.runInContext(script, context);
const spec = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
if (typeof context.muteLink !== "function") process.exit(3);
const href = context.muteLink(spec.repo, spec.section, spec.item);
const terms = context.keyTerms(spec.item.title);
process.stdout.write(JSON.stringify({ href, terms }));
'''
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        proc = subprocess.run(
            [node, "-e", script, str(ROOT / "index.html"), str(spec_path)],
            check=False, capture_output=True, text=True)
    check(proc.returncode == 0, "page script failed: " + proc.stderr)
    data = json.loads(proc.stdout)
    terms = data["terms"]
    check(2 <= len(terms) <= 4, f"expected 2-4 key terms, got {terms}")
    check("ensemble" in terms and "tokenised" in terms, f"distinctive words missing: {terms}")
    href = data["href"]
    parsed = urlparse(href)
    check(parsed.scheme == "https" and parsed.netloc == "github.com", href)
    check(parsed.path == "/poohpoohsy/morning-brief/issues/new", parsed.path)
    qs = parse_qs(parsed.query)
    check(qs.get("labels") == ["mute"], f"label missing: {qs.get('labels')}")
    check(qs.get("title") == ["Mute: " + ENSEMBLE["title"]], f"title: {qs.get('title')}")
    body = qs.get("body", [""])[0]
    for line in (
        "Section: Work",
        "Source: Fintech News HK",
        "Link: https://fintechnews.hk/ensemble",
        "Title: " + ENSEMBLE["title"],
        "Key terms: " + ", ".join(terms),
        "- [ ] Mute this source in this section",
        "- [ ] Mute these words",
        "- [ ] Mute the whole section",
    ):
        check(line in body, "body missing " + line)
    lowered = href.casefold()
    check("api.github.com" not in lowered, "link must be the new-issue page, not the API")
    check("ghp_" not in lowered and "github_pat_" not in lowered and "bearer " not in lowered,
          "link must not carry a token")
    # The prefilled issue, submitted as-is, becomes the rule that drops the story.
    rule = build.normalize_rule(build.parse_mute_body(body))
    check(build.item_is_muted(ENSEMBLE, [rule], "work"), "submitting the prefilled issue mutes the story")
    check(not build.item_is_muted(HIBOR, [rule], "work"), "submitting it does not mute the neighbour")
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    check("api.github.com" not in page and "GITHUB_TOKEN" not in page, "the page must not call GitHub")
    for needle in ("muteBtn(it, \"Work\")", "muteBtn(it, \"Talking points\")",
                   "plainCard(it, \"Small Talk\")", "plainCard(it, \"Personal\")",
                   "muteBtn(it, \"Juicy\")", "muteBtn(it, section)", "Muted ("):
        check(needle in page, "page missing " + needle)


def test_rendered_card_uses_the_same_rule():
    rules = [build.normalize_rule(FAKE_RULE)]
    cards = [
        {"title": ENSEMBLE["title"], "zh": ["Project Ensemble", "", ""],
         "en": "Tokenised deposits.", "sources": [{"name": "Fintech News HK", "url": ENSEMBLE["url"]}]},
        {"title": HIBOR["title"], "zh": ["HIBOR", "", ""], "en": "Rates.",
         "sources": [{"name": "RTHK 財經", "url": HIBOR["url"]}]},
    ]
    kept = build.filter_output({"work": cards}, rules)["work"]
    check(len(kept) == 1 and kept[0]["title"] == HIBOR["title"], "rendered ensemble card is removed")


class _MuteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag != "a":
            return
        got = dict(attrs)
        if "mute" in (got.get("class") or "").split():
            self.hrefs.append(got.get("href") or "")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1


def _serve(directory):
    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


_DUMP_DOM = r'''
const {spawn} = require("child_process");
const crypto = require("crypto");
const http = require("http");
const net = require("net");
const chromePath = process.argv[1];
const pageUrl = process.argv[2];
const port = 9300 + Math.floor(Math.random() * 600);

function request(url, method) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, {method: method || "GET"}, res => {
      let body = "";
      res.on("data", chunk => body += chunk);
      res.on("end", () => resolve(body));
    });
    req.on("error", reject);
    req.end();
  });
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Chrome's debugger port is a WebSocket. Node 20 has no global WebSocket, so
// this speaks the handshake and frames with net and crypto.
function connectSocket(url) {
  const parsed = new URL(url);
  const socket = net.connect(Number(parsed.port) || 80, parsed.hostname);
  socket.setNoDelay(true);
  const listeners = {open: [], message: []};
  let buffer = Buffer.alloc(0);
  let opened = false;
  let closing = false;
  let parts = [];
  let op = 0;
  const key = crypto.randomBytes(16).toString("base64");
  const accept = crypto.createHash("sha1")
    .update(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
    .digest("base64");

  function emit(type, ev) {
    for (const fn of listeners[type] || []) fn(ev);
  }
  function fail(err) {
    if (closing) return;
    console.error(err);
    process.exit(1);
  }
  function encodeFrame(opcode, payload) {
    const body = Buffer.isBuffer(payload) ? payload : Buffer.from(String(payload));
    const mask = crypto.randomBytes(4);
    const masked = Buffer.alloc(body.length);
    for (let i = 0; i < body.length; i++) masked[i] = body[i] ^ mask[i & 3];
    let head;
    if (body.length < 126) {
      head = Buffer.from([0x80 | opcode, 0x80 | body.length]);
    } else if (body.length < 65536) {
      head = Buffer.alloc(4);
      head[0] = 0x80 | opcode;
      head[1] = 0x80 | 126;
      head.writeUInt16BE(body.length, 2);
    } else {
      head = Buffer.alloc(10);
      head[0] = 0x80 | opcode;
      head[1] = 0x80 | 127;
      head.writeBigUInt64BE(BigInt(body.length), 2);
    }
    return Buffer.concat([head, mask, masked]);
  }
  function headerValue(head, name) {
    const want = name.toLowerCase();
    for (const line of head.split("\r\n").slice(1)) {
      const idx = line.indexOf(":");
      if (idx > 0 && line.slice(0, idx).trim().toLowerCase() === want) {
        return line.slice(idx + 1).trim();
      }
    }
    return "";
  }
  function takeFrames() {
    while (buffer.length >= 2) {
      const b0 = buffer[0];
      const b1 = buffer[1];
      let len = b1 & 127;
      let off = 2;
      if (len === 126) {
        if (buffer.length < 4) return;
        len = buffer.readUInt16BE(2);
        off = 4;
      } else if (len === 127) {
        if (buffer.length < 10) return;
        const big = buffer.readBigUInt64BE(2);
        if (big > 0x7fffffffn) return fail(new Error("websocket frame too large"));
        len = Number(big);
        off = 10;
      }
      const maskLen = (b1 & 128) ? 4 : 0;
      if (buffer.length < off + maskLen + len) return;
      let payload = Buffer.from(buffer.subarray(off + maskLen, off + maskLen + len));
      if (maskLen) {
        const mask = buffer.subarray(off, off + 4);
        for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
      }
      buffer = buffer.subarray(off + maskLen + len);
      const opcode = b0 & 15;
      const fin = (b0 & 128) !== 0;
      if (opcode === 8) { socket.end(); return; }
      if (opcode === 9) { socket.write(encodeFrame(0xA, payload)); continue; }
      if (opcode === 10) continue;
      if (opcode === 1 || opcode === 2 || opcode === 0) {
        if (opcode !== 0) { parts = [payload]; op = opcode; }
        else parts.push(payload);
        if (!fin) continue;
        const msg = Buffer.concat(parts);
        parts = [];
        if (op === 1) emit("message", {data: msg.toString("utf8")});
        op = 0;
      }
    }
  }
  function consume() {
    if (!opened) {
      const end = buffer.indexOf("\r\n\r\n");
      if (end < 0) return;
      const head = buffer.slice(0, end).toString("latin1");
      buffer = buffer.subarray(end + 4);
      if (!/^HTTP\/1\.1 101\b/.test(head) || headerValue(head, "sec-websocket-accept") !== accept) {
        return fail(new Error("websocket upgrade failed: " + head.split("\r\n")[0]));
      }
      opened = true;
      emit("open", {});
    }
    takeFrames();
  }

  socket.on("connect", () => {
    const path = (parsed.pathname || "/") + parsed.search;
    socket.write(
      `GET ${path} HTTP/1.1\r\n` +
      `Host: ${parsed.host}\r\n` +
      `Upgrade: websocket\r\n` +
      `Connection: Upgrade\r\n` +
      `Sec-WebSocket-Key: ${key}\r\n` +
      `Sec-WebSocket-Version: 13\r\n` +
      `\r\n`);
  });
  socket.on("data", chunk => { buffer = Buffer.concat([buffer, chunk]); consume(); });
  socket.on("error", fail);
  socket.on("end", () => {
    if (!opened) fail(new Error("chrome debugger socket closed before the handshake"));
  });

  return {
    addEventListener(type, fn) { (listeners[type] || (listeners[type] = [])).push(fn); },
    removeEventListener(type, fn) {
      const list = listeners[type] || [];
      const i = list.indexOf(fn);
      if (i >= 0) list.splice(i, 1);
    },
    send(text) { socket.write(encodeFrame(1, text)); },
    close() { closing = true; socket.end(); },
  };
}

(async () => {
  const userData = `/tmp/morning-brief-chrome-${port}`;
  const child = spawn(chromePath, [
    "--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
    `--user-data-dir=${userData}`,
    `--remote-debugging-port=${port}`, "--remote-allow-origins=*", "about:blank",
  ], {stdio: "ignore"});
  let ready = false;
  for (let i = 0; i < 50 && !ready; i++) {
    try { await request(`http://127.0.0.1:${port}/json/version`); ready = true; }
    catch (e) { await sleep(100); }
  }
  if (!ready) { child.kill(); process.exit(2); }
  const tab = JSON.parse(await request(`http://127.0.0.1:${port}/json/new?${pageUrl}`, "PUT"));
  const ws = connectSocket(tab.webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener("open", resolve));
  let id = 0;
  function send(method, params) {
    const msgId = ++id;
    return new Promise(resolve => {
      function onMsg(ev) {
        const data = JSON.parse(ev.data);
        if (data.id === msgId) {
          ws.removeEventListener("message", onMsg);
          resolve(data.result);
        }
      }
      ws.addEventListener("message", onMsg);
      ws.send(JSON.stringify({id: msgId, method, params}));
    });
  }
  let html = "";
  const started = Date.now();
  while (Date.now() - started < 8000) {
    const result = await send("Runtime.evaluate", {
      // The script source already contains class="mute" and "Could not load".
      // Wait until that link is actually in the document, or the error is shown.
      expression: `(function () {
        var link = document.querySelector("a.mute");
        var sub = document.getElementById("sub");
        var failed = sub && sub.textContent.indexOf("Could not load") !== -1;
        if (!link && !failed) return "";
        return document.documentElement.outerHTML;
      })()`,
      returnByValue: true,
    });
    html = (result && result.result && result.result.value) || "";
    if (html) break;
    await sleep(100);
  }
  process.stdout.write(html);
  ws.close();
  child.kill();
})().catch(err => { console.error(err); process.exit(1); });
'''


def _dump_dom(chrome, url):
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "-e", _DUMP_DOM, chrome, url],
        check=False, capture_output=True, text=True, timeout=30)
    check(proc.returncode == 0, "chrome failed: " + (proc.stderr or "")[-800:])
    check(proc.stdout, "chrome returned an empty page")
    return proc.stdout


def test_page_hides_the_item_and_links_to_github():
    """Render the real page with a fake rule already applied, the way the build would."""
    chrome = "/usr/bin/google-chrome-stable" if Path("/usr/bin/google-chrome-stable").exists() else (
        shutil.which("google-chrome-stable") or shutil.which("google-chrome"))
    if not chrome:
        print("chrome not installed — skipped the rendered-page check")
        return
    rules = [build.normalize_rule(FAKE_RULE)]
    juicy = {
        "headline": "A juicy story that must stay hidden",
        "body": "Whole section is muted.",
        "sources": [{"name": "Example", "url": "https://example.com/juicy"}],
    }
    brief = {
        "report_date": "Saturday, 14 November 2026",
        "generated_at": "14 Nov 2026 09:00 HKT",
        "generated_iso": "2026-11-14T09:00:00+08:00",
        "repo": "poohpoohsy/morning-brief",
        "weather": {"available": False},
        "talking_points": {
            "mode": "rss",
            "audiences": [{
                "id": "ceo",
                "label": "CEO",
                "blurb": "Strategy.",
                "items": [{
                    "point": "Virtual bank licence talks continue",
                    "so_what": "Worth a sentence with the CEO.",
                    "sources": [{"name": "HKMA", "url": "https://example.com/talk"}],
                }],
            }],
        },
        "rates": {"rows": []},
        "sections": {
            "work": [
                {"zh": ["HIBOR stays put today", "", ""], "en": "Rates were unchanged.",
                 "title": HIBOR["title"],
                 "sources": [{"name": "RTHK 財經", "url": HIBOR["url"]}]},
            ],
            "smalltalk_hk": [{
                "headline": "A Hong Kong merger closes",
                "body": "Two firms combined.",
                "sources": [{"name": "Ming Pao", "url": "https://example.com/hk"}],
            }],
            "smalltalk_sg": [{
                "headline": "Singapore budget briefing",
                "body": "Ministers spoke.",
                "sources": [{"name": "The Independent SG", "url": "https://example.com/sg"}],
            }],
            "personal_hk": [{
                "headline": "週末市集開放",
                "body": "一條民生消息。",
                "sources": [{"name": "HK01", "url": "https://example.com/life"}],
            }],
            "personal_sg": [{
                "headline": "New estate opening hours",
                "body": "A government notice.",
                "sources": [{"name": "gov.sg", "url": "https://example.com/gov"}],
            }],
            "juicy_hk": [juicy],
            "juicy_sg": [],
        },
        "hidden_sections": ["Juicy"],
        "mutes": build.mute_summaries(rules) + build.mute_summaries([build.normalize_rule({
            "id": "fake-juicy",
            "section": "Juicy",
            "keys": ["juicy_hk", "juicy_sg"],
            "hide_section": True,
            "sources": [],
            "terms": [],
            "titles": [],
        })]),
    }
    # The ensemble card was removed before this file was written.
    check(all(not build.item_is_muted(it, rules, "work") for it in brief["sections"]["work"]),
          "fixture still contains a muted work card")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data").mkdir()
        (root / "index.html").write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
        (root / "data" / "brief.json").write_text(
            json.dumps(brief, ensure_ascii=False), encoding="utf-8")
        httpd = _serve(str(root))
        try:
            dom = _dump_dom(chrome, f"http://127.0.0.1:{httpd.server_address[1]}/index.html")
        finally:
            httpd.shutdown()
    check("Project Ensemble" not in dom, "the muted story is still on the page")
    check("HIBOR stays put today" in dom, "the kept work card disappeared")
    check("A juicy story that must stay hidden" not in dom, "a hidden section is still rendered")
    check("A Hong Kong merger closes" in dom, "Small Talk card missing")
    check("週末市集開放" in dom, "Personal card missing")
    check("Virtual bank licence talks continue" in dom, "Talking points card missing")
    check("Muted (2)" in dom, "muted footer missing")
    check("Work — words: ensemble, tokenised" in dom, "footer does not list the fake rule")
    check("Juicy — whole section" in dom, "footer does not list the hidden section")
    parser = _MuteLinks()
    parser.feed(dom)
    # Work, talking points, two small-talk, two personal. Juicy is hidden.
    check(len(parser.hrefs) == 6, f"expected 6 mute buttons, found {len(parser.hrefs)}")
    work = next(href for href in parser.hrefs if "Section%3A+Work" in href or "Section:+Work" in href)
    qs = parse_qs(urlparse(work).query)
    check(qs.get("labels") == ["mute"], f"button label: {qs.get('labels')}")
    check(qs.get("title") == ["Mute: " + HIBOR["title"]], f"button title: {qs.get('title')}")
    body = qs.get("body", [""])[0]
    check("Section: Work" in body, "button body missing the section")
    check("Source: RTHK 財經" in body, "button body missing the source")
    check("Link: " + HIBOR["url"] in body, "button body missing the link")
    check("Title: " + HIBOR["title"] in body, "button body missing the title")
    check("Key terms:" in body, "button body missing key terms")
    check(body.count("- [ ] Mute ") == 3, "button body missing the three checkboxes")
    sections = []
    for href in parser.hrefs:
        text = parse_qs(urlparse(href).query).get("body", [""])[0]
        for name in ("Work", "Talking points", "Small Talk", "Personal", "Juicy"):
            if f"Section: {name}" in text:
                sections.append(name)
    check(sections.count("Work") == 1, sections)
    check(sections.count("Talking points") == 1, sections)
    check(sections.count("Small Talk") == 2, sections)
    check(sections.count("Personal") == 2, sections)
    check("Juicy" not in sections, "hidden Juicy still has a mute button")


def main():
    test_fake_rule_drops_item_before_the_model()
    test_whole_section_is_hidden_and_not_sent()
    test_source_rule_is_section_scoped()
    test_deleted_issue_rule_survives()
    test_issue_body_parsing()
    test_rendered_card_uses_the_same_rule()
    test_button_url_from_the_page()
    test_page_hides_the_item_and_links_to_github()
    print("mute tests passed")


if __name__ == "__main__":
    main()
