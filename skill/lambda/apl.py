"""Hearth's card, drawn in APL for an Echo Show.

Hearth returns its card as `structuredContent.card` on every visual tool
result: {pattern, tone, eyebrow, title, body, items[{label, detail, meta,
status}], footer}. The MCP App view (`ui://hearth/card-….html`) draws it as
HTML for an Alexa+ host; a classic skill cannot host HTML, so this draws the
same data with the same colours as an APL document. The data is passed through
untouched as the document's datasource; the layout is all here.
"""
from __future__ import annotations

TOKEN = "hearthCard"
TONES = {"stop": "#ff6b4a", "ok": "#7fd49a", "warn": "#ffc35c", "info": "#9ec5ff"}
MARKS = {"done": "#7fd49a", "won": "#7fd49a", "lost": "#ff6b4a",
         "needs_attention": "#ffc35c", "info": "#8d7868"}

DOCUMENT = {
    "type": "APL",
    "version": "2023.3",
    "theme": "dark",
    "mainTemplate": {
        "parameters": ["payload"],
        "items": [{
            "type": "Container",
            "width": "100vw", "height": "100vh",
            "backgroundColor": "#1a1411",
            "items": [
                {"type": "Frame", "width": "100vw", "height": "1.5vh",
                 "backgroundColor": "${payload.card.toneColor}"},
                {"type": "ScrollView", "width": "100vw", "grow": 1,
                 "item": {
                     "type": "Container",
                     "paddingLeft": "5vw", "paddingRight": "5vw",
                     "paddingTop": "4vh", "paddingBottom": "4vh",
                     "items": [
                         {"type": "Text", "text": "${payload.card.eyebrow}",
                          "fontSize": "@fontSizeSmall", "color": "#cdb9aa",
                          "letterSpacing": "2dp"},
                         {"type": "Text", "text": "${payload.card.title}",
                          "fontSize": "@fontSizeXLarge", "fontWeight": "bold",
                          "color": "${payload.card.titleColor}", "paddingTop": "1vh"},
                         {"type": "Text", "text": "${payload.card.body}",
                          "when": "${payload.card.body}",
                          "fontSize": "@fontSizeMedium", "color": "#fbf3ec",
                          "paddingTop": "2vh"},
                         {"type": "Container", "paddingTop": "3vh",
                          "data": "${payload.card.items}",
                          "items": [{
                              "type": "Container", "direction": "row",
                              "paddingBottom": "2vh",
                              "items": [
                                  {"type": "Frame", "width": "1.6vw", "height": "1.6vw",
                                   "borderRadius": "1vw", "backgroundColor": "${data.markColor}",
                                   "alignSelf": "start", "paddingTop": "1vh"},
                                  {"type": "Container", "paddingLeft": "2vw", "shrink": 1,
                                   "items": [
                                       {"type": "Text", "text": "${data.label}",
                                        "fontSize": "@fontSizeSmall", "fontWeight": "bold",
                                        "color": "#fbf3ec"},
                                       {"type": "Text", "text": "${data.detail}",
                                        "fontSize": "@fontSizeSmall", "color": "#cdb9aa"},
                                       {"type": "Text", "text": "${data.meta}",
                                        "when": "${data.meta}",
                                        "fontSize": "@fontSizeXSmall", "color": "#8d7868"}]}]}]},
                         {"type": "Text", "text": "${payload.card.footer}",
                          "when": "${payload.card.footer}",
                          "fontSize": "@fontSizeXSmall", "color": "#8d7868",
                          "paddingTop": "2vh"},
                         {"type": "Text", "text": "${payload.card.source}",
                          "fontSize": "@fontSizeXSmall", "color": "#6f5f54",
                          "paddingTop": "3vh"}]}}]}]}}


def datasource(card: dict, record: dict | None = None) -> dict:
    """The card as Hearth sent it, plus the two colours APL cannot compute and
    a source line naming what drew it and which record entry it is."""
    tone = card.get("tone") or "info"
    items = [{"label": str(i.get("label") or ""), "detail": str(i.get("detail") or ""),
              "meta": str(i.get("meta") or ""),
              "markColor": MARKS.get(i.get("status"), MARKS["info"])}
             for i in card.get("items") or []]
    source = "Hearth, via a classic Alexa skill"
    if record:
        source += f" · record #{record.get('seq')} {record.get('outcome', '')}".rstrip()
    return {"payload": {"card": {
        "eyebrow": str(card.get("eyebrow") or "").upper(),
        "title": str(card.get("title") or ""),
        "body": str(card.get("body") or ""),
        "footer": str(card.get("footer") or ""),
        "items": items, "source": source,
        "toneColor": TONES.get(tone, TONES["info"]),
        "titleColor": TONES.get(tone, "#fbf3ec") if tone != "info" else "#fbf3ec"}}}


def directive(card: dict, record: dict | None = None) -> dict:
    """An Alexa.Presentation.APL.RenderDocument directive, as a plain dict."""
    return {"type": "Alexa.Presentation.APL.RenderDocument", "token": TOKEN,
            "document": DOCUMENT, "datasources": datasource(card, record)}
