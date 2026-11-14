"""Mute rules: a fake rule drops a story, and the Not-for-me link is prefilled.

No network. The button is checked by running the page's own script.
"""

import json
import shutil
import subprocess
import sys
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


def _item_body(section, source, link, title, terms, ticks=()):
    lines = [
        f"Section: {section}",
        f"Source: {source}",
    ]
    if link is not None:
        lines.append(f"Link: {link}")
    lines.extend([
        f"Title: {title}",
        "",
        "Key terms: " + ", ".join(terms),
        "",
        "- [" + ("x" if "source" in ticks else " ") + "] Mute this source in this section",
        "- [" + ("x" if "terms" in ticks else " ") + "] Mute these words",
        "- [" + ("x" if "section" in ticks else " ") + "] Mute the whole section",
    ])
    return "\n".join(lines)


def test_one_issue_can_list_many_items():
    work = _item_body(
        "Work", "Fintech News HK", "https://fintechnews.hk/ensemble",
        ENSEMBLE["title"], ["ensemble", "tokenised"])
    talk = _item_body(
        "Talking points", "RTHK 財經", "https://rthk.hk/hibor",
        HIBOR["title"], ["hibor", "aggregate"])
    dashed = _item_body(
        "Small Talk", "Ming Pao", "https://example.com/dash",
        "The vote --- a surprise result", ["vote", "surprise"])
    check(len(build.parse_mute_items(dashed)) == 1, "dashes inside a title are not a separator")
    check(build.parse_mute_items(dashed)[0]["example_title"] == "The vote --- a surprise result",
          "the dashed title is kept")
    check(len(build.parse_mute_items(work + "\n\n---\n")) == 1, "a trailing separator adds no item")

    intro = "\n".join([
        "Mute these from future briefs. Edit the key terms if they are off, then submit.",
        "If you leave the boxes unticked, those key terms are muted in that section.",
        "",
        work,
        "",
        "---",
        "",
        talk,
    ])
    items = build.parse_mute_items(intro)
    check(len(items) == 2, f"expected 2 items, got {len(items)}")
    check(build.parse_mute_body(intro)["keys"] == ["work"], "the legacy helper still returns the first item")
    first, second = [build.normalize_rule(it) for it in items]
    check(first["terms"] == ["ensemble", "tokenised"] and first["sources"] == [], first)
    check(first["hide_section"] is False, "unticked boxes do not hide the section")
    check(build.item_is_muted(ENSEMBLE, [first], "work"), "the first item mutes its story")
    check(not build.item_is_muted(HIBOR, [first], "work"), "the first item leaves the neighbour")
    check(second["terms"] == ["hibor", "aggregate"] and second["keys"] == ["talking_points"], second)
    check(build.item_is_muted(HIBOR, [second], "talking_points"), "the second item mutes its own story")
    check(not build.item_is_muted(ENSEMBLE, [second], "work"), "the second item stays in its section")

    mixed = build.parse_mute_items("\n\n---\n\n".join([
        _item_body("Work", "Fintech News HK", "https://fintechnews.hk/ensemble",
                   ENSEMBLE["title"], ["ensemble", "tokenised"], ticks=("source",)),
        _item_body("Small Talk", "The Independent SG", "https://ex.sg/a",
                   "MAS holds a briefing", ["holds", "briefing"]),
    ]))
    check(mixed[0]["sources"] == ["Fintech News HK"] and mixed[0]["terms"] == [], mixed[0])
    check(mixed[1]["terms"] == ["holds", "briefing"] and mixed[1]["sources"] == [], mixed[1])
    check(mixed[1]["hide_section"] is False, "an unticked item stays a word mute")

    hidden = build.parse_mute_items(work + "\n\n---\n\n" + _item_body(
        "Juicy", "Example", "https://example.com/j", "A juicy story", ["juicy", "story"],
        ticks=("section",)))
    check(hidden[0]["hide_section"] is False and hidden[0]["terms"], "item boxes do not leak backwards")
    check(hidden[1]["hide_section"] is True and hidden[1]["terms"] == [], hidden[1])
    check(build.section_hidden([build.normalize_rule(hidden[1])], "juicy_hk"), "the juicy block is hidden")

    no_link = build.parse_mute_items(_item_body("Personal", "HK01", None, "週末市集", ["週末市集"]))
    check(no_link[0]["terms"] == ["週末市集"] and no_link[0]["example_url"] == "", no_link)
    crlf = (work + "\n\n---\n\n" + talk).replace("\n", "\r\n")
    check(len(build.parse_mute_items(crlf)) == 2, "Windows newlines still separate items")
    skipped = build.parse_mute_items("Please mute these.\n\n---\n\n" + work + "\n\n---\n\nNot an item\n")
    check(len(skipped) == 1 and skipped[0]["keys"] == ["work"], "blocks without a section are ignored")

    rules = build.rules_from_issue({"number": 12, "body": intro})
    check([r["id"] for r in rules] == ["issue:12:0", "issue:12:1"], [r["id"] for r in rules])
    check(all(r["issue"] == 12 for r in rules), "both rules remember the issue number")
    single = build.rules_from_issue({"number": 4, "body": work})
    check([r["id"] for r in single] == ["issue:4"], "a one-item issue keeps the old id")
    # Issue 12 shrinks to one item. Issue 4 is no longer on GitHub and must stay.
    edited = build.rules_from_issue({"number": 12, "body": work})
    extra = build.rules_from_issue({"number": 9, "body": talk})
    merged = build.replace_issue_rules(rules + single, edited + extra)
    check([r["id"] for r in merged] == ["issue:4", "issue:9", "issue:12"],
          [r["id"] for r in merged])
    kept = [r for r in merged if r["issue"] == 12]
    check(len(kept) == 1 and kept[0]["terms"] == ["ensemble", "tokenised"], kept)


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
        "other": {
            "point": "HIBOR rises as the aggregate balance falls",
            "sources": [{"name": "RTHK 財經", "url": "https://rthk.hk/hibor"}],
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
if (typeof context.planMuteSubmissions !== "function") process.exit(4);
const href = context.muteLink(spec.repo, spec.section, spec.item);
const terms = context.keyTerms(spec.item.title);
const one = context.itemRecord(spec.section, spec.item);
const two = context.planMuteSubmissions(spec.repo, [
  one,
  context.itemRecord("Talking points", spec.other),
]);
function story(i, linkLen, titleLen) {
  return {
    key: "k" + i,
    section: i % 2 ? "Work" : "Small Talk",
    source: "Example News",
    link: "https://example.com/" + String(i) + "/" + "a".repeat(linkLen),
    title: "Distinctive headline " + i + " " + "word".repeat(titleLen),
    terms: ["distinctive", "headline"],
  };
}
let drop = null;
for (let n = 2; n <= 30 && !drop; n++) {
  const items = [];
  for (let i = 0; i < n; i++) items.push(story(i, 280, 8));
  const withLinks = context.muteIssueUrl(spec.repo, items, true).length;
  const noLinks = context.muteIssueUrl(spec.repo, items, false).length;
  if (withLinks > 7000 && noLinks <= 7000) {
    drop = context.planMuteSubmissions(spec.repo, items);
  }
}
let split = null;
for (let n = 2; n <= 40 && !split; n++) {
  const items = [];
  for (let i = 0; i < n; i++) items.push(story(i, 40, 80));
  if (context.muteIssueUrl(spec.repo, items, false).length > 7000) {
    split = context.planMuteSubmissions(spec.repo, items);
  }
}
const huge = context.planMuteSubmissions(spec.repo, [{
  key: "huge",
  section: "Work",
  source: "Example News",
  link: "https://example.com/" + "b".repeat(8000),
  title: "Y".repeat(8000),
  terms: ["yyyy"],
}]);
const pack = (plan) => (plan || []).map(part => ({
  label: part.label,
  includeLink: part.includeLink,
  url: part.url,
  count: part.items.length,
}));
process.stdout.write(JSON.stringify({ href, terms, two: pack(two), drop: pack(drop), split: pack(split), huge: pack(huge) }));
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
    check(qs.get("title") == ["Mute: 1 item"], f"title: {qs.get('title')}")
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
    check(len(href) <= 7000, f"one story should fit, length {len(href)}")

    def decoded_body(url):
        return parse_qs(urlparse(url).query).get("body", [""])[0]

    two = data["two"]
    check(len(two) == 1 and two[0]["label"] == "Submit muted (2)", two)
    check(two[0]["includeLink"] is True, "short batches keep the link lines")
    check(len(two[0]["url"]) <= 7000, len(two[0]["url"]))
    two_qs = parse_qs(urlparse(two[0]["url"]).query)
    check(two_qs.get("labels") == ["mute"], two_qs.get("labels"))
    check(two_qs.get("title") == ["Mute: 2 items"], two_qs.get("title"))
    two_body = two_qs.get("body", [""])[0]
    check("\n---\n" in two_body, "items are separated by ---")
    check(two_body.count("- [ ] Mute this source in this section") == 2, "each item has its own boxes")
    parsed_two = [build.normalize_rule(it) for it in build.parse_mute_items(two_body)]
    check(len(parsed_two) == 2, parsed_two)
    check(build.item_is_muted(ENSEMBLE, [parsed_two[0]], "work"), "batch item mutes the work story")
    check(build.item_is_muted(
        {"title": HIBOR["title"], "source": "RTHK 財經", "url": HIBOR["url"], "snippet": ""},
        [parsed_two[1]], "talking_points"), "batch item mutes the talking point")
    check(not build.item_is_muted(ENSEMBLE, [parsed_two[1]], "work"), "the second rule stays in its section")

    drop = data["drop"]
    check(drop and len(drop) == 1 and drop[0]["includeLink"] is False, drop)
    check(drop[0]["label"] == f"Submit muted ({drop[0]['count']})", drop[0]["label"])
    check(len(drop[0]["url"]) <= 7000, len(drop[0]["url"]))
    drop_body = decoded_body(drop[0]["url"])
    check("Link:" not in drop_body, "links are dropped before the batch is split")
    drop_items = build.parse_mute_items(drop_body)
    check(len(drop_items) == drop[0]["count"], (len(drop_items), drop[0]["count"]))
    check(all(it["terms"] == ["distinctive", "headline"] for it in drop_items), drop_items[0])

    split = data["split"]
    check(split and len(split) >= 2, split)
    for index, part in enumerate(split, start=1):
        check(part["label"] == f"Submit part {index} of {len(split)}", part["label"])
        check(part["includeLink"] is False, part)
        check(len(part["url"]) <= 7000, len(part["url"]))
        part_body = decoded_body(part["url"])
        check("Link:" not in part_body, "a split batch has already dropped links")
        check(len(build.parse_mute_items(part_body)) == part["count"], part["label"])
    check(sum(part["count"] for part in split) > split[0]["count"], "the split keeps every story")

    huge = data["huge"]
    check(len(huge) == 1 and len(huge[0]["url"]) <= 7000, huge and len(huge[0]["url"]))
    check(build.parse_mute_items(decoded_body(huge[0]["url"])), "a shortened story still parses")

    page = (ROOT / "index.html").read_text(encoding="utf-8")
    check("morning-brief-mute-marks" in page, "marks need a localStorage key")
    check('id="mutebar"' in page and "Submit muted (" in page and "Submit part " in page, "bar copy missing")
    check("viewport-fit=cover" in page and "env(safe-area-inset-bottom" in page, "safe area missing")
    check('<a class="mute"' not in page, "the story control must not navigate away")
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


class _MuteButtons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.payloads = []
        self.links = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        got = dict(attrs)
        classes = (got.get("class") or "").split()
        if "mute" not in classes:
            return
        if tag == "a":
            self.links.append(got.get("href") or "")
        if tag == "button":
            self.payloads.append(got.get("data-mute") or "")

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
    "--headless=new", "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    `--user-data-dir=${userData}`,
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`, "--remote-allow-origins=*",
    "about:blank",
  ], {stdio: ["ignore", "ignore", "pipe"], detached: true});
  let chromeErr = "";
  child.stderr.on("data", chunk => {
    chromeErr += chunk.toString();
    if (chromeErr.length > 6000) chromeErr = chromeErr.slice(-6000);
  });
  function stopChrome() {
    try { process.kill(-child.pid, "SIGKILL"); }
    catch (e) { try { child.kill("SIGKILL"); } catch (e2) {} }
  }
  let ready = false;
  for (let i = 0; i < 100 && !ready; i++) {
    try { await request(`http://127.0.0.1:${port}/json/version`); ready = true; }
    catch (e) { await sleep(100); }
  }
  if (!ready) {
    console.error("chrome debugger port never opened\n" + chromeErr.slice(-800));
    stopChrome();
    process.exit(2);
  }
  const tab = JSON.parse(await request(`http://127.0.0.1:${port}/json/new?about:blank`, "PUT"));
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
      ws.send(JSON.stringify({id: msgId, method, params: params || {}}));
    });
  }
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Page.navigate", {url: pageUrl});
  const errors = [];
  ws.addEventListener("message", ev => {
    const data = JSON.parse(ev.data);
    if (data.method === "Runtime.exceptionThrown") {
      const details = data.params && data.params.exceptionDetails;
      errors.push(details && (details.text || details.exception && details.exception.description) || "exception");
    }
  });
  let html = "";
  const started = Date.now();
  while (Date.now() - started < 8000) {
    const result = await send("Runtime.evaluate", {
      // The script source already contains class="mute" and "Could not load".
      // Wait until a mute button is actually in the document, or the error is shown.
      expression: `(function () {
        var button = document.querySelector("button.mute");
        var sub = document.getElementById("sub");
        var failed = sub && sub.textContent.indexOf("Could not load") !== -1;
        if (!button && !failed) return "";
        return document.documentElement.outerHTML;
      })()`,
      returnByValue: true,
    });
    html = (result && result.result && result.result.value) || "";
    if (html) break;
    await sleep(100);
  }
  if (errors.length) html += "\n<!-- page-error: " + errors.join(" | ") + " -->";
  process.stdout.write(html);
  ws.close();
  stopChrome();
})().catch(err => { console.error(err); process.exit(1); });
'''


def _dump_dom(chrome, url):
    node = shutil.which("node")
    proc = subprocess.run(
        [node, "-e", _DUMP_DOM, chrome, url],
        check=False, capture_output=True, text=True, timeout=30)
    detail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    check(proc.returncode == 0,
          "chrome failed: " + (detail or f"exit {proc.returncode} with no output")[-800:])
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
    check("HIBOR stays put today" in dom, "the kept work card disappeared " + dom[-500:])
    check("A juicy story that must stay hidden" not in dom, "a hidden section is still rendered")
    check("A Hong Kong merger closes" in dom, "Small Talk card missing")
    check("週末市集開放" in dom, "Personal card missing")
    check("Virtual bank licence talks continue" in dom, "Talking points card missing")
    check("Muted (2)" in dom, "muted footer missing")
    check("Work — words: ensemble, tokenised" in dom, "footer does not list the fake rule")
    check("Juicy — whole section" in dom, "footer does not list the hidden section")
    parser = _MuteButtons()
    parser.feed(dom)
    # Work, talking points, two small-talk, two personal. Juicy is hidden.
    check(parser.links == [], "a mute control must not be a link")
    check(len(parser.payloads) == 6, f"expected 6 mute buttons, found {len(parser.payloads)}")
    check('id="mutebar"' in dom and "mute-bar" in dom, "the submit bar is missing")
    records = [json.loads(raw) for raw in parser.payloads]
    work = next(rec for rec in records if rec["section"] == "Work")
    check(work["title"] == HIBOR["title"], work["title"])
    check(work["source"] == "RTHK 財經", work["source"])
    check(work["link"] == HIBOR["url"], work["link"])
    check(2 <= len(work["terms"]) <= 4, work["terms"])
    sections = [rec["section"] for rec in records]
    check(sections.count("Work") == 1, sections)
    check(sections.count("Talking points") == 1, sections)
    check(sections.count("Small Talk") == 2, sections)
    check(sections.count("Personal") == 2, sections)
    check("Juicy" not in sections, "hidden Juicy still has a mute button")
    check("issues/new" not in "".join(parser.payloads), "the button must not carry an issue URL")


_MOBILE_PROBE = r'''
const {spawn} = require("child_process");
const crypto = require("crypto");
const http = require("http");
const net = require("net");
const chromePath = process.argv[1];
const pageUrl = process.argv[2];
const port = 9400 + Math.floor(Math.random() * 500);

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
  const userData = `/tmp/morning-brief-mobile-${port}`;
  const child = spawn(chromePath, [
    "--headless=new", "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu",
    "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    `--user-data-dir=${userData}`,
    "--remote-debugging-address=127.0.0.1",
    `--remote-debugging-port=${port}`, "--remote-allow-origins=*",
    "about:blank",
  ], {stdio: ["ignore", "ignore", "pipe"], detached: true});
  let chromeErr = "";
  child.stderr.on("data", chunk => {
    chromeErr += chunk.toString();
    if (chromeErr.length > 6000) chromeErr = chromeErr.slice(-6000);
  });
  function stopChrome() {
    try { process.kill(-child.pid, "SIGKILL"); }
    catch (e) { try { child.kill("SIGKILL"); } catch (e2) {} }
  }
  let ready = false;
  for (let i = 0; i < 100 && !ready; i++) {
    try { await request(`http://127.0.0.1:${port}/json/version`); ready = true; }
    catch (e) { await sleep(100); }
  }
  if (!ready) {
    console.error("chrome debugger port never opened\n" + chromeErr.slice(-800));
    stopChrome();
    process.exit(2);
  }
  const tab = JSON.parse(await request(`http://127.0.0.1:${port}/json/new?about:blank`, "PUT"));
  const ws = connectSocket(tab.webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener("open", resolve));
  let id = 0;
  function send(method, params) {
    const msgId = ++id;
    return new Promise((resolve, reject) => {
      function onMsg(ev) {
        const data = JSON.parse(ev.data);
        if (data.id !== msgId) return;
        ws.removeEventListener("message", onMsg);
        if (data.error) reject(new Error(data.error.message || JSON.stringify(data.error)));
        else resolve(data.result || {});
      }
      ws.addEventListener("message", onMsg);
      ws.send(JSON.stringify({id: msgId, method, params: params || {}}));
    });
  }
  async function evalJson(expression) {
    let last = "no result";
    for (let attempt = 0; attempt < 25; attempt++) {
      try {
        const result = await send("Runtime.evaluate", {
          expression, returnByValue: true, awaitPromise: true,
        });
        if (result.exceptionDetails) {
          const text = JSON.stringify(result.exceptionDetails);
          if (/context|destroyed|navigation|target/i.test(text)) {
            await sleep(100);
            last = text;
            continue;
          }
          throw new Error(text);
        }
        return result.result ? result.result.value : null;
      } catch (err) {
        last = String(err);
        await sleep(100);
      }
    }
    throw new Error(last);
  }
  async function phone() {
    await send("Emulation.setDeviceMetricsOverride", {
      width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
    });
  }
  let safeArea = false;
  await phone();
  try {
    await send("Emulation.setSafeAreaInsetsOverride", {
      insets: {top: 47, left: 0, bottom: 34, right: 0},
    });
    safeArea = true;
  } catch (err) {
    safeArea = false;
  }
  await send("Page.enable");
  await send("Page.navigate", {url: pageUrl});
  let buttonCount = 0;
  for (let i = 0; i < 50; i++) {
    buttonCount = await evalJson("document.querySelectorAll('button.mute').length") || 0;
    if (buttonCount >= 4) break;
    await sleep(100);
  }
  if (buttonCount < 4) throw new Error("mute buttons missing: " + buttonCount);
  await evalJson(`(() => {
    const buttons = [...document.querySelectorAll('button.mute')];
    buttons[0].click();
    buttons[1].click();
    return buttons.length;
  })()`);
  await sleep(40);
  const marked = await evalJson(`(() => {
    const bar = document.getElementById('mutebar');
    const submits = [...document.querySelectorAll('a.mute-submit')].map(a => a.textContent.trim());
    const clear = (document.getElementById('mute-clear') || {}).textContent || '';
    const cards = [...document.querySelectorAll('article.marked')];
    const struck = cards.map(card => {
      const el = card.querySelector('.zh3, .headline');
      const line = getComputedStyle(el).textDecorationLine || '';
      return line.includes('line-through');
    });
    const undo = [...document.querySelectorAll('button.mute')].filter(b => b.textContent.trim() === 'Undo').length;
    window.scrollTo(0, document.documentElement.scrollHeight);
    const foot = document.getElementById('foot').getBoundingClientRect();
    const barBox = bar.getBoundingClientRect();
    const doc = document.documentElement;
    const boxes = [...document.querySelectorAll('button.mute, a.mute-submit, #mute-clear, #mutebar')].map(el => {
      const r = el.getBoundingClientRect();
      return {left: r.left, right: r.right};
    });
    return {
      hidden: bar.hidden,
      submits, clear, struck, undo,
      marked: cards.length,
      pad: parseFloat(getComputedStyle(document.querySelector('.wrap')).paddingBottom),
      barH: bar.offsetHeight,
      barPad: parseFloat(getComputedStyle(bar).paddingBottom),
      footBottom: foot.bottom,
      barTop: barBox.top,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
      stored: JSON.parse(localStorage.getItem('morning-brief-mute-marks') || '[]').length,
      boxes,
      href: (document.querySelector('a.mute-submit') || {}).href || '',
    };
  })()`);
  await evalJson("document.querySelectorAll('button.mute')[1].click()");
  await sleep(30);
  const undone = await evalJson(`(() => ({
    marked: document.querySelectorAll('article.marked').length,
    label: ((document.querySelector('a.mute-submit') || {}).textContent || '').trim(),
  }))()`);
  await evalJson("document.querySelectorAll('button.mute')[1].click()");
  await sleep(30);
  await phone();
  await send("Page.reload", {ignoreCache: true});
  let reloaded = {marked: 0, label: '', stored: 0};
  for (let i = 0; i < 50; i++) {
    reloaded = await evalJson(`(() => ({
      marked: document.querySelectorAll('article.marked').length,
      label: ((document.querySelector('a.mute-submit') || {}).textContent || '').trim(),
      stored: JSON.parse(localStorage.getItem('morning-brief-mute-marks') || '[]').length,
      buttons: document.querySelectorAll('button.mute').length,
    }))()`) || reloaded;
    if (reloaded && reloaded.buttons >= 4 && reloaded.marked >= 2) break;
    await sleep(100);
  }
  const href = await evalJson(`(() => {
    const link = document.querySelector('a.mute-submit');
    if (!link) return '';
    link.addEventListener('click', (event) => event.preventDefault());
    link.click();
    return link.href;
  })()`);
  await sleep(80);
  const submitted = await evalJson(`(() => ({
    stored: JSON.parse(localStorage.getItem('morning-brief-mute-marks') || '[]').length,
    hidden: document.getElementById('mutebar').hidden,
    marked: document.querySelectorAll('article.marked').length,
    title: document.title,
  }))()`);
  const splitPlan = await evalJson(`(() => {
    const items = [];
    let plan = [];
    for (let n = 1; n <= 40; n++) {
      items.push({
        key: 'split-' + n,
        section: n % 2 ? 'Work' : 'Personal',
        source: 'Example News',
        link: 'https://example.com/' + 'a'.repeat(500),
        title: ('Long headline about markets ' + n + ' ').repeat(12).trim(),
        terms: ['headline', 'markets'],
      });
      plan = planMuteSubmissions('poohpoohsy/morning-brief', items);
      if (plan.length >= 2) break;
    }
    localStorage.setItem('morning-brief-mute-marks', JSON.stringify(items));
    return {
      count: items.length,
      parts: plan.length,
      labels: plan.map(p => p.label),
      lens: plan.map(p => p.url.length),
    };
  })()`);
  await phone();
  await send("Page.reload", {ignoreCache: true});
  let splitUi = null;
  for (let i = 0; i < 50; i++) {
    splitUi = await evalJson(`(() => {
      const links = [...document.querySelectorAll('a.mute-submit')];
      if (links.length < 2) return null;
      window.scrollTo(0, document.documentElement.scrollHeight);
      const bar = document.getElementById('mutebar');
      const foot = document.getElementById('foot').getBoundingClientRect();
      const barBox = bar.getBoundingClientRect();
      const doc = document.documentElement;
      return {
        submits: links.map(a => ({
          text: a.textContent.trim(),
          len: a.href.length,
          left: a.getBoundingClientRect().left,
          right: a.getBoundingClientRect().right,
        })),
        clear: document.getElementById('mute-clear').textContent.trim(),
        pad: parseFloat(getComputedStyle(document.querySelector('.wrap')).paddingBottom),
        barH: bar.offsetHeight,
        footBottom: foot.bottom,
        barTop: barBox.top,
        scrollWidth: doc.scrollWidth,
        clientWidth: doc.clientWidth,
        innerWidth: window.innerWidth,
      };
    })()`);
    if (splitUi) break;
    await sleep(100);
  }
  await evalJson("document.getElementById('mute-clear').click()");
  await sleep(30);
  const cleared = await evalJson(`(() => ({
    hidden: document.getElementById('mutebar').hidden,
    stored: localStorage.getItem('morning-brief-mute-marks'),
  }))()`);
  process.stdout.write(JSON.stringify({
    safeArea, marked, undone, reloaded, href, submitted, splitPlan, splitUi, cleared,
  }));
  ws.close();
  stopChrome();
})().catch(err => { console.error(err); process.exit(1); });
'''


def _within(box, width):
    return box["left"] >= -1 and box["right"] <= width + 1


def test_mobile_viewport_marks_and_submits_together():
    """390px-wide page: marks stay, the bar does not cover the footer, one issue lists both."""
    chrome = "/usr/bin/google-chrome-stable" if Path("/usr/bin/google-chrome-stable").exists() else (
        shutil.which("google-chrome-stable") or shutil.which("google-chrome"))
    if not chrome:
        print("chrome not installed — skipped the mobile viewport check")
        return
    node = shutil.which("node")
    check(node, "node is required")
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
                "items": [{
                    "point": "Virtual bank licence talks continue",
                    "so_what": "Worth a sentence with the CEO.",
                    "sources": [{"name": "HKMA", "url": "https://example.com/talk"}],
                }],
            }],
        },
        "rates": {"rows": []},
        "sections": {
            "work": [{
                "zh": ["HIBOR stays put today", "", ""],
                "en": "Rates were unchanged.",
                "title": HIBOR["title"],
                "sources": [{"name": "RTHK 財經", "url": HIBOR["url"]}],
            }],
            "smalltalk_hk": [{
                "headline": "A Hong Kong merger closes",
                "body": "Two firms combined.",
                "sources": [{"name": "Ming Pao", "url": "https://example.com/hk"}],
            }],
            "smalltalk_sg": [],
            "personal_hk": [{
                "headline": "週末市集開放",
                "body": "一條民生消息。",
                "sources": [{"name": "HK01", "url": "https://example.com/life"}],
            }],
            "personal_sg": [],
            "juicy_hk": [],
            "juicy_sg": [],
        },
        "hidden_sections": [],
        "mutes": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data").mkdir()
        (root / "index.html").write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
        (root / "data" / "brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
        httpd = _serve(str(root))
        try:
            proc = subprocess.run(
                [node, "-e", _MOBILE_PROBE, chrome, f"http://127.0.0.1:{httpd.server_address[1]}/index.html"],
                check=False, capture_output=True, text=True, timeout=60)
        finally:
            httpd.shutdown()
    check(proc.returncode == 0, "mobile probe failed: " + (proc.stderr or proc.stdout or "")[-1200:])
    report = json.loads(proc.stdout)
    marked = report["marked"]
    check(380 <= marked["innerWidth"] <= 400, marked["innerWidth"])
    check(marked["stored"] == 2 and marked["marked"] == 2, marked)
    check(marked["submits"] == ["Submit muted (2)"], marked["submits"])
    check(marked["clear"] == "Clear", marked["clear"])
    check(marked["hidden"] is False, "the bar should be visible")
    check(marked["struck"] == [True, True], marked["struck"])
    check(marked["undo"] == 2, marked["undo"])
    check(marked["pad"] + 1 >= marked["barH"], (marked["pad"], marked["barH"]))
    check(marked["footBottom"] <= marked["barTop"] + 1, (marked["footBottom"], marked["barTop"]))
    check(marked["scrollWidth"] <= marked["clientWidth"] + 1, (marked["scrollWidth"], marked["clientWidth"]))
    check(all(_within(box, marked["innerWidth"]) for box in marked["boxes"]), marked["boxes"])
    if report["safeArea"]:
        check(marked["barPad"] >= 30, marked["barPad"])
    check(report["undone"]["marked"] == 1, report["undone"])
    check(report["undone"]["label"] == "Submit muted (1)", report["undone"])
    check(report["reloaded"]["marked"] == 2, report["reloaded"])
    check(report["reloaded"]["stored"] == 2, report["reloaded"])
    check(report["reloaded"]["label"] == "Submit muted (2)", report["reloaded"])
    href = report["href"]
    parsed = urlparse(href)
    check(parsed.path == "/poohpoohsy/morning-brief/issues/new", parsed.path)
    qs = parse_qs(parsed.query)
    check(qs.get("labels") == ["mute"] and qs.get("title") == ["Mute: 2 items"], qs)
    body = qs.get("body", [""])[0]
    check("\n---\n" in body, "the issue should list both stories")
    check("Section: Work" in body and "Section: Talking points" in body, body)
    check(body.count("- [ ] Mute ") == 6, "each story keeps its three boxes")
    check(len(href) <= 7000, len(href))
    rules = [build.normalize_rule(it) for it in build.parse_mute_items(body)]
    check(len(rules) == 2, rules)
    work_rule = next(rule for rule in rules if "work" in rule["keys"])
    check(build.item_is_muted(HIBOR, [work_rule], "work"), "submitting mutes the work story")
    check(not build.item_is_muted(HIBOR, [work_rule], "talking_points"), "the work mute stays in Work")
    check(report["submitted"]["stored"] == 0, report["submitted"])
    check(report["submitted"]["hidden"] is True and report["submitted"]["marked"] == 0, report["submitted"])
    check(report["submitted"]["title"] == "Morning Brief", "submit should leave this page open")
    plan = report["splitPlan"]
    check(plan["parts"] >= 2, plan)
    ui = report["splitUi"]
    check(ui, "split buttons did not render")
    check(380 <= ui["innerWidth"] <= 400, ui["innerWidth"])
    check([part["text"] for part in ui["submits"]] == [
        f"Submit part {i} of {len(ui['submits'])}" for i in range(1, len(ui["submits"]) + 1)
    ], ui["submits"])
    check(all(part["len"] <= 7000 for part in ui["submits"]), ui["submits"])
    check(ui["clear"] == "Clear", ui["clear"])
    check(ui["pad"] + 1 >= ui["barH"], (ui["pad"], ui["barH"]))
    check(ui["footBottom"] <= ui["barTop"] + 1, (ui["footBottom"], ui["barTop"]))
    check(ui["scrollWidth"] <= ui["clientWidth"] + 1, (ui["scrollWidth"], ui["clientWidth"]))
    check(all(_within(part, ui["innerWidth"]) for part in ui["submits"]), ui["submits"])
    check(report["cleared"]["hidden"] is True, report["cleared"])
    check(report["cleared"]["stored"] in (None, "[]"), report["cleared"])


def test_fallback_is_capped_and_ranked():
    """A model outage must not dump the feed. Best keyword hits stay, and the page stays short."""
    # Unrelated stems. A shared prefix makes cluster() treat them as one story.
    stems = [
        "Harbour fog delays the dawn ferry",
        "Violin shop on Wellington Street closes Friday",
        "New bus lane opens beside the stadium",
        "Library extends evening hours in Kowloon",
        "Tea auction sets an unusual price",
        "Footbridge mural painted overnight",
        "Reservoir path reopens after repairs",
        "Choir rehearses in the old post office",
        "Night market moves two streets east",
        "School roof garden harvests its first crop",
        "Tram bell replaced on route six",
        "Bookstore hosts a midnight reading",
        "Pier kiosk starts selling maps",
        "Community oven shared by three bakeries",
        "Hill path lights switched to warmer bulbs",
        "Ferry timetable printed on yellow paper",
        "Clock tower scaffold comes down Monday",
        "Wet market fishmonger retires",
        "Lantern workshop teaches a weekend class",
        "Post boxes repainted dark green",
        "Rooftop bees moved to a park hive",
        "Stone steps repaired near the temple",
        "Radio play recorded in a stairwell",
        "Canvas awning replaced on the cafe",
        "Fountain cleaned before the holiday",
    ]
    fetched = {}
    for key, sec in build.CFG["sections"].items():
        words = list(sec.get("include") or [])
        rows = []
        for i, stem in enumerate(stems):
            hit = ""
            if words:
                hit = " ".join(words[:4]) if i == 0 else words[min(i, len(words) - 1)]
            rows.append({
                "title": f"{stem}. {hit}".strip(),
                "source": "Example",
                "url": f"https://example.com/{key}/{i}",
                "snippet": f"{stem} remains the whole of the note. {hit}".strip(),
                "published": "14 Nov 08:00",
            })
        fetched[key] = rows
    collected, payload, _ = build.candidates_for_model(fetched, [])
    for key, groups in payload.items():
        check(len(groups) <= build.CFG["model_candidates"], f"{key} sent {len(groups)} candidates")
    digest = build.rss_digest(collected)
    total = sum(len(v) for v in digest.values())
    check(total <= build.CFG["page_cap"], f"page has {total}")
    for key, rows in digest.items():
        check(len(rows) <= build.CFG["section_cap"], f"{key} has {len(rows)}")
    lead = (digest["work"][0].get("title") or "").lower()
    check(build.CFG["sections"]["work"]["include"][0].lower() in lead, lead)
    thin = {key: (list(rows[:1]) if rows else []) for key, rows in digest.items()}
    topped = build.top_up(thin, collected)
    topped_total = 0
    for key, rows in topped.items():
        topped_total += len(rows)
        check(len(rows) <= build.CFG["section_cap"], f"{key} topped to {len(rows)}")
        if len(collected.get(key) or []) >= build.CFG["section_floor"]:
            check(build.CFG["section_floor"] <= len(rows) <= build.CFG["section_floor"],
                  f"{key} should sit on the floor, has {len(rows)}")
    check(topped_total <= build.CFG["page_cap"], topped_total)


def test_rates_show_verified_figures_only():
    """Placeholder prints must not come back, and an unread bank has no number."""
    from datetime import datetime
    table = build.rate_table()
    by_key = {row["key"]: row for row in table["rows"]}
    check(len(by_key) == len(build.BANKS["banks"]), len(by_key))
    check(by_key["livi Bank"]["rate_label"] == "3.00", by_key["livi Bank"])
    check(by_key["Citi"]["rate_label"] == "3.20", by_key["Citi"])
    check(by_key["ZA Bank"]["rate_label"] == "0.51", by_key["ZA Bank"])
    check(by_key["Hang Seng"]["board_only"] is True, by_key["Hang Seng"])
    check(by_key["Hang Seng"]["rate_label"] == "0.125", by_key["Hang Seng"])
    check(by_key["Hang Seng"]["rate"] == 0.125, by_key["Hang Seng"])
    check(by_key["Hang Seng"]["rank"] is None, "board rate is not ranked against promos")
    today = datetime.now(build.HK).date().isoformat()
    for key, row in by_key.items():
        check(str(row.get("source_url") or "").startswith("https://"), key)
        if row["rate"] is None:
            check(row["status"] == "not_checked", row)
            check(row["stale"] is False, row)
            check(row["rate_label"] is None, row)
        else:
            check(row["stale"] is build.rate_is_stale(row["as_of_date"] or row["read_on"], today), row)
    for name in ("WeLab Bank", "Ant Bank", "PAObank", "Fusion Bank"):
        check(by_key[name]["rate"] is None, by_key[name])
    shown = {row["rate"] for row in table["rows"] if row["rate"] is not None}
    for fake in (4.2, 4.05, 3.98, 3.9, 3.8, 3.72, 3.68, 3.55, 3.5, 3.4, 3.15, 3.1):
        check(fake not in shown, fake)
    check(table["placeholders"] == 0, table["placeholders"])
    check(table["unchecked"] == 4, table["unchecked"])
    check("not checked" in build.INDEX_HTML and "rate-list" in build.INDEX_HTML, "rate layout missing")
    check("placeholder value" not in build.INDEX_HTML, "placeholder copy still on the page")
    check(build.rate_is_stale("2026-11-09", "2026-11-14") is True, "9 Nov is stale on 14 Nov")
    check(build.rate_is_stale("2026-11-13", "2026-11-14") is False, "13 Nov is one day old")
    check(build.rate_is_stale("2026-08-04", "2026-11-14") is True, "4 Aug is stale")
    check(build.rate_is_stale(None, "2026-11-14") is False, "a missing date is not stale")


def main():
    args = [a for a in sys.argv[1:] if a.startswith("-")]
    run_unit = not args or "--unit" in args
    run_ui = not args or "--ui" in args
    if run_unit:
        test_fake_rule_drops_item_before_the_model()
        test_whole_section_is_hidden_and_not_sent()
        test_source_rule_is_section_scoped()
        test_deleted_issue_rule_survives()
        test_issue_body_parsing()
        test_one_issue_can_list_many_items()
        test_rendered_card_uses_the_same_rule()
        test_button_url_from_the_page()
        test_fallback_is_capped_and_ranked()
        test_rates_show_verified_figures_only()
        print("mute unit tests passed")
    if run_ui:
        test_page_hides_the_item_and_links_to_github()
        test_mobile_viewport_marks_and_submits_together()
        print("mute ui tests passed")


if __name__ == "__main__":
    main()
