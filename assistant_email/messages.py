"""Lecture des emails (MIME) et mise en texte d'une conversation."""
from __future__ import annotations

import html
import re
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List

MAX_BODY_CHARS = 20000


class _HtmlToText(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "blockquote", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _HtmlToText()
    try:
        parser.feed(markup)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_LIST_START = re.compile(r"^\s*([-*•·>|]|\d+[.)])\s")


def unwrap_text(text: str) -> str:
    """Recolle les paragraphes coupés à ~70 colonnes par certains expéditeurs, sans toucher aux listes, citations et signatures."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        lines = para.split("\n")
        longest = max((len(l) for l in lines), default=0)
        wrapped = (len(lines) >= 2 and longest >= 50
                   and not any(_LIST_START.match(l) for l in lines)
                   and all(len(l.rstrip()) >= 0.78 * longest for l in lines[:-1]))
        out.append(re.sub(r"[ \t]*\n[ \t]*", " ", para).strip() if wrapped else para)
    return "\n\n".join(out)


_QUOTE_START = re.compile(r"^(Le .{5,120}(a écrit|écrit)\s*:?|On .{5,120}wrote:|-{2,}\s*(Original|Message d'origine|Forwarded)|De\s?:\s|From:\s|Envoy[ée] de mon)", re.I)


def strip_quoted(text: str) -> str:
    """Retire l'historique cité sous une réponse (pour ne garder que ce que la personne a écrit)."""
    kept = []
    for line in text.split("\n"):
        if _QUOTE_START.match(line.strip()) or line.lstrip().startswith(">"):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def parse_bytes(raw: bytes) -> EmailMessage:
    return BytesParser(policy=policy.default).parsebytes(raw)


def body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):
        payload = part.get_payload(decode=True) or b""
        content = payload.decode("utf-8", errors="replace")
    if part.get_content_type() == "text/html":
        content = html_to_text(content)
    content = unwrap_text(content.replace("\r\n", "\n").strip())
    if len(content) > MAX_BODY_CHARS:
        content = content[:MAX_BODY_CHARS] + "\n[… message tronqué …]"
    return content


def _h(msg: EmailMessage, name: str) -> str:
    try:
        value = msg.get(name)
    except Exception:
        value = None
    return str(value).strip() if value is not None else ""


def message_ids(value: str) -> List[str]:
    return re.findall(r"<[^<>\s]+>", value or "")


def to_dict(msg: EmailMessage) -> Dict[str, Any]:
    date = _h(msg, "Date")
    try:
        ts = parsedate_to_datetime(date).timestamp() if date else 0.0
    except (TypeError, ValueError, IndexError):
        ts = 0.0
    return {
        "de": _h(msg, "From"),
        "a": _h(msg, "To"),
        "cc": _h(msg, "Cc"),
        "repondre_a": _h(msg, "Reply-To"),
        "objet": _h(msg, "Subject"),
        "date": date,
        "horodatage": ts,
        "message_id": (message_ids(_h(msg, "Message-ID")) or [""])[0],
        "in_reply_to": (message_ids(_h(msg, "In-Reply-To")) or [""])[0],
        "references": message_ids(_h(msg, "References")),
        "corps": body_text(msg),
    }


def conversation_text(messages: Iterable[Dict[str, Any]]) -> str:
    blocks = []
    for i, m in enumerate(messages, 1):
        lines = ["----- Message %d -----" % i, "De : %s" % m.get("de", "")]
        if m.get("a"):
            lines.append("À : %s" % m["a"])
        if m.get("cc"):
            lines.append("Cc : %s" % m["cc"])
        if m.get("date"):
            lines.append("Date : %s" % m["date"])
        lines.append("Objet : %s" % m.get("objet", ""))
        lines.append("")
        lines.append(m.get("corps", ""))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def reply_subject(subject: str) -> str:
    subject = (subject or "").strip()
    if re.match(r"^(re|ré|aw|sv|antw)\s*:", subject, re.I):
        return subject
    return "Re: " + subject if subject else "Re:"


def _addr_list(*values: str) -> List[str]:
    return [a for _, a in getaddresses([v for v in values if v]) if a]


def reply_meta(last: Dict[str, Any], own_addresses: Iterable[str]) -> Dict[str, Any]:
    """Destinataires, objet et en-têtes de fil pour répondre au dernier message."""
    own = {a.lower() for a in own_addresses if a}
    sender = parseaddr(last.get("de", ""))[1]
    to = last.get("repondre_a") or last.get("de", "")
    if sender.lower() in own:
        # Réponse à un message que j'ai moi-même envoyé : on relance ses destinataires.
        to = last.get("a", "")
    to_addrs = {a.lower() for a in _addr_list(to)}
    others = [a for a in _addr_list(last.get("a", ""), last.get("cc", ""))
              if a.lower() not in own and a.lower() not in to_addrs]
    refs = list(last.get("references") or [])
    if last.get("message_id") and last["message_id"] not in refs:
        refs.append(last["message_id"])
    return {
        "a": to,
        "cc_tous": ", ".join(dict.fromkeys(others)),
        "objet": reply_subject(last.get("objet", "")),
        "in_reply_to": last.get("message_id", ""),
        "references": " ".join(refs),
        "citation": {"de": last.get("de", ""), "date": last.get("date", ""), "corps": last.get("corps", "")},
    }


def recipients_of(msg: Dict[str, Any]) -> List[str]:
    return [a.lower() for a in _addr_list(msg.get("a", ""), msg.get("cc", ""))]
