"""Hearth's card, drawn in APL for an Echo Show.

Hearth returns its card as `structuredContent.card` on every visual tool
result: {pattern, tone, eyebrow, title, body, items[{label, detail, meta,
status}], footer}. The MCP App view (`ui://hearth/card-….html`) draws it as
HTML for an Alexa+ host; a classic skill cannot host HTML, so this draws the
same data as the same label (design/DESIGN.md, direction C) in APL. The data
is passed through untouched as the document's datasource, plus the few values
APL cannot work out for itself: which label it is, the header, the sticker
and each row's mark. The layout is all here.

Two labels, one system: a dose is a medicine label (solid black header, the
person and the drug); everything else is a household label (outlined header,
blue "For the family"). Red is only ever a refusal.
"""
from __future__ import annotations

import re

TOKEN = "hearthCard"

# design/DESIGN.md tokens, light set.
PAPER, RULE, INK, INK2, INK3 = "#FFFFFF", "#111111", "#0B0B0B", "#3A3A3A", "#595954"
RED, ON_RED, RED_TINT = "#C8201A", "#FFFFFF", "#FCE9E7"
YELLOW, ON_YELLOW = "#FFD43B", "#0B0B0B"
BLUE, ON_BLUE, GREEN, ON_GREEN = "#1F4FB5", "#FFFFFF", "#006B47", "#FFFFFF"

TONES = {"stop": RED, "ok": GREEN, "warn": INK, "info": BLUE}
STICKERS = {"red": (RED, ON_RED, RED), "green": (GREEN, ON_GREEN, GREEN),
            "blue": (BLUE, ON_BLUE, BLUE), "yel": (YELLOW, ON_YELLOW, YELLOW),
            "out": (PAPER, INK, RULE)}

# The record names tools; a family reads what was done.
DID = {"remember": "Remembered", "whats_true": "Checked a rule", "did": "Reported",
       "why": "Explained", "stand_down": "Stood down", "end_context": "Ended",
       "household": "Household", "check_dose": "Dose question", "give_dose": "Dose",
       "arrange": "Arranged", "reorder": "Priced an order", "handover": "Handover",
       "shopping_list": "Shopping list", "catch_up": "Catch-up", "record": "The record",
       "checkout.complete": "Paid", "checkout.create": "Checkout",
       "checkout.cancel": "Cancelled"}

# Row marks, as AVG so they draw the same on every Echo Show.
_SQ = {"type": "path", "pathData": "M1.5,1.5 L22.5,1.5 L22.5,22.5 L1.5,22.5 Z",
       "stroke": RULE, "strokeWidth": 2}
GRAPHICS = {
    "done": {"type": "AVG", "version": "1.2", "width": 24, "height": 24, "items": [
        {"type": "path", "pathData": "M0,0 L24,0 L24,24 L0,24 Z", "fill": GREEN},
        {"type": "path", "pathData": "M6,12.5 L10,16.5 L18,8", "stroke": ON_GREEN,
         "strokeWidth": 2.8}]},
    "refused": {"type": "AVG", "version": "1.2", "width": 24, "height": 24, "items": [
        {"type": "path", "pathData": "M0,0 L24,0 L24,24 L0,24 Z", "fill": RED},
        {"type": "path", "pathData": "M7.5,7.5 L16.5,16.5 M16.5,7.5 L7.5,16.5",
         "stroke": ON_RED, "strokeWidth": 2.8}]},
    "attention": {"type": "AVG", "version": "1.2", "width": 24, "height": 24, "items": [
        _SQ, {"type": "path", "pathData": "M12,6.5 L12,13.5", "stroke": INK, "strokeWidth": 2.8},
        {"type": "path", "pathData": "M10.6,15.6 L13.4,15.6 L13.4,18.4 L10.6,18.4 Z", "fill": INK}]},
    "info": {"type": "AVG", "version": "1.2", "width": 24, "height": 24, "items": [
        _SQ, {"type": "path", "pathData": "M9.5,9.5 L14.5,9.5 L14.5,14.5 L9.5,14.5 Z",
              "fill": INK}]},
    "over": {"type": "AVG", "version": "1.2", "width": 24, "height": 24, "items": [
        _SQ, {"type": "path", "pathData": "M7,12 L17,12", "stroke": INK3, "strokeWidth": 2.4}]},
}

_ROW = {
    "type": "Container", "direction": "row", "paddingTop": "1.6vh", "paddingBottom": "1.6vh",
    "items": [
        {"type": "VectorGraphic", "source": "${data.mark}", "width": "3.4vw",
         "height": "3.4vw", "scale": "best-fit"},
        {"type": "Text", "text": "${data.label}", "width": "26vw", "paddingLeft": "1.6vw",
         "paddingRight": "1.6vw", "fontSize": "22dp", "fontWeight": "bold", "color": INK,
         "fontFamily": "Amazon Ember Display"},
        {"type": "Container", "grow": 1, "shrink": 1, "items": [
            {"type": "Text", "text": "${data.detail}", "fontSize": "22dp", "color": "${data.detailColor}",
             "maxLines": 2, "fontFamily": "Amazon Ember Display"},
            {"type": "Text", "text": "${data.meta}", "when": "${data.meta}", "fontSize": "18dp",
             "color": INK3, "maxLines": 1}]}]}

DOCUMENT = {
    "type": "APL",
    "version": "2023.3",
    "theme": "light",
    "graphics": GRAPHICS,
    "mainTemplate": {
        "parameters": ["payload"],
        "items": [{
            "type": "Frame", "width": "100vw", "height": "100vh",
            "backgroundColor": PAPER, "borderWidth": "3dp", "borderColor": RULE,
            "item": {"type": "Container", "width": "100%", "height": "100%", "items": [
                # The header: solid for medicine, outlined for the household.
                {"type": "Frame", "width": "100%", "backgroundColor": "${payload.card.headBg}",
                 "item": {"type": "Container", "direction": "row", "width": "100%",
                 "paddingLeft": "3vw", "paddingRight": "3vw", "paddingTop": "1.4vh",
                 "paddingBottom": "1.4vh",
                 "items": [
                     {"type": "Text", "text": "${payload.card.headLeft}", "grow": 1,
                      "fontSize": "18dp", "fontWeight": "bold", "letterSpacing": "1dp",
                      "color": "${payload.card.headColor}"},
                     {"type": "Text", "text": "${payload.card.headRight}",
                      "fontSize": "18dp", "fontWeight": "bold", "letterSpacing": "1dp",
                      "color": "${payload.card.headColor}"}]}},
                {"type": "Frame", "width": "100%", "height": "3dp", "backgroundColor": RULE},
                {"type": "ScrollView", "width": "100vw", "grow": 1, "item": {
                    "type": "Container", "paddingLeft": "3vw", "paddingRight": "3vw",
                    "paddingTop": "2.4vh", "paddingBottom": "2vh",
                    "items": [
                        {"type": "Container", "direction": "row", "items": [
                            {"type": "Text", "text": "${payload.card.title}", "grow": 1,
                             "shrink": 1, "fontSize": "46dp", "fontWeight": "bold",
                             "color": "${payload.card.titleColor}"},
                            {"type": "Frame", "backgroundColor": "${payload.card.sticker.bg}",
                             "borderWidth": "2dp", "borderColor": "${payload.card.sticker.border}",
                             "alignSelf": "start", "marginLeft": "2vw", "marginTop": "1vh",
                             "item": {"type": "Text", "text": "${payload.card.sticker.text}",
                                      "fontSize": "18dp", "fontWeight": "bold",
                                      "letterSpacing": "1dp", "paddingLeft": "1.4vw",
                                      "paddingRight": "1.4vw", "paddingTop": "0.8vh",
                                      "paddingBottom": "0.8vh",
                                      "color": "${payload.card.sticker.color}"}}]},
                        {"type": "Text", "text": "${payload.card.body}",
                         "when": "${payload.card.body}", "fontSize": "24dp", "color": INK2,
                         "paddingTop": "0.8vh"},
                        {"type": "Container", "paddingTop": "2vh",
                         "data": "${payload.card.items}",
                         "items": [{"type": "Container", "items": [
                             {"type": "Frame", "width": "100%", "height": "2dp",
                              "backgroundColor": RULE},
                             {"type": "Frame", "backgroundColor": "${data.rowBg}",
                              "item": _ROW}]}]}]}},
                {"type": "Frame", "width": "100%", "height": "2dp", "backgroundColor": RULE},
                {"type": "Container", "direction": "row", "paddingLeft": "3vw",
                 "paddingRight": "3vw", "paddingTop": "1vh", "paddingBottom": "1.2vh",
                 "items": [
                     {"type": "Text", "text": "${payload.card.footer}", "grow": 1, "shrink": 1,
                      "maxLines": 1, "fontSize": "18dp", "color": INK3},
                     {"type": "Text", "text": "${payload.card.source}", "fontSize": "18dp",
                      "color": INK3, "paddingLeft": "2vw"}]}]}}]}}


def kind_of(card: dict) -> str:
    """A dose is medicine; everything else is the household."""
    if re.search(r"medicine", str(card.get("title") or ""), re.I):
        return "med"
    m = re.match(r"^(.+?) · (.+)$", str(card.get("eyebrow") or ""))
    if m and not re.search(r"pharmacy|order", m.group(1), re.I) \
            and "sandbox" not in m.group(2).lower():
        return "med"
    return "home"


def sticker(card: dict, kind: str) -> tuple:
    """The one sticker on the label: (colour, word). Red only for a refusal."""
    tone, title = card.get("tone") or "info", str(card.get("title") or "")
    eb, items = str(card.get("eyebrow") or "").lower(), card.get("items") or []
    if kind == "med":
        if tone == "stop":
            return "red", "Stopped"
        if tone == "ok":
            return "green", "Logged" if "logged" in title.lower() else "Taken today"
        return "out", "Not yet today" if "not taken" in title.lower() else "Check first"
    if eb == "the record":
        return ("out", "Check failed") if tone == "stop" else ("green", "Intact")
    if tone == "stop":
        return "red", "Refused"
    if "order placed" in eb:
        return "green", "Paid"
    won = next((i for i in items if i.get("status") == "won"), None)
    if won:
        return "yel", re.sub(r" said$", "", str(won.get("label") or "")) + "'s rule"
    if tone == "warn":
        f = next((i for i in items if i.get("status") == "needs_attention"), None)
        who = f and re.search(r"\bfor ([A-Z][a-z]+)", str(f.get("detail") or ""))
        return "out", ("Needs " + who.group(1)) if who else "Check first"
    return "blue", "For the family"


def _row(i: dict, overruling: bool) -> dict:
    st = i.get("status") or "info"
    mark = ("done" if st in ("done", "won") else "attention" if st == "needs_attention"
            else "info")
    detail_color, row_bg = INK, PAPER
    if st == "lost":
        # Lost is a refusal, unless the card weighs one person's word
        # against another's: then it is a preference that was overruled.
        if overruling:
            mark, detail_color = "over", INK3
        else:
            mark, row_bg = "refused", RED_TINT
    label, detail = str(i.get("label") or ""), str(i.get("detail") or "")
    rec = re.match(r"^#(\d+) (\S+)$", label)
    if rec:
        label = f"#{rec.group(1)} {DID.get(rec.group(2), rec.group(2))}"
    if label == "The rule":
        s = re.match(r"^([A-Z][a-z]+) set it (.*)$", detail)
        label = "Rule" + (f", {s.group(1)}" if s else "")
        if s:
            detail = "Set it " + s.group(2)
    return {"label": label, "detail": detail, "meta": str(i.get("meta") or ""),
            "mark": mark, "detailColor": detail_color, "rowBg": row_bg,
            "markColor": {"done": GREEN, "refused": RED}.get(mark, INK)}


def datasource(card: dict, record: dict | None = None) -> dict:
    """The card as Hearth sent it, plus what APL cannot compute: the label,
    the header, the sticker, each row's mark, and a source line naming what
    drew it and which record entry it is."""
    tone = card.get("tone") or "info"
    kind = kind_of(card)
    items = card.get("items") or []
    overruling = any(i.get("status") == "won" for i in items)
    colour, word = sticker(card, kind)
    bg, fg, border = STICKERS[colour]
    eyebrow = str(card.get("eyebrow") or "")
    if kind == "med":
        m = re.match(r"^(.+?) · (.+)$", eyebrow)
        head = (f"Hearth · for {m.group(1) if m else eyebrow or 'the family'}",
                m.group(2) if m else "Medicine")
    else:
        head = ("Hearth · household", eyebrow)
    source = "Hearth, via a classic Alexa skill"
    if record:
        source += f" · record #{record.get('seq')} {record.get('outcome', '')}".rstrip()
    return {"payload": {"card": {
        "kind": kind,
        "eyebrow": eyebrow.upper(),
        "headLeft": head[0].upper(), "headRight": head[1].upper(),
        "headBg": RULE if kind == "med" else PAPER,
        "headColor": PAPER if kind == "med" else INK,
        "title": str(card.get("title") or ""),
        "body": str(card.get("body") or ""),
        "footer": str(card.get("footer") or ""),
        "items": [_row(i, overruling) for i in items[:5]], "source": source,
        "sticker": {"text": word.upper(), "bg": bg, "color": fg, "border": border},
        "toneColor": TONES.get(tone, TONES["info"]),
        "titleColor": INK}}}


def directive(card: dict, record: dict | None = None) -> dict:
    """An Alexa.Presentation.APL.RenderDocument directive, as a plain dict."""
    return {"type": "Alexa.Presentation.APL.RenderDocument", "token": TOKEN,
            "document": DOCUMENT, "datasources": datasource(card, record)}
