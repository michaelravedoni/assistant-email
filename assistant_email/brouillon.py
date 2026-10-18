"""Fabrication du message brouillon (RFC 5322) prêt à déposer dans le dossier Brouillons."""
from __future__ import annotations

from email import policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, Optional


def add_signature(profile: Dict[str, Any], body: str) -> str:
    sig = (profile.get("signature") or "").strip("\n")
    body = body.rstrip()
    if sig.strip() and not body.endswith(sig.strip()):
        body += "\n\n" + sig
    return body


def remove_signature(profile: Dict[str, Any], body: str) -> str:
    sig = (profile.get("signature") or "").strip()
    body = body.rstrip()
    if sig and body.endswith(sig):
        body = body[: -len(sig)].rstrip()
    return body


def compose_body(profile: Dict[str, Any], body: str, quote: Optional[Dict[str, Any]] = None) -> str:
    """Texte final : le corps (signature comprise, telle qu'éditée) suivi éventuellement de la citation."""
    text = body.rstrip()
    if quote and profile.get("citer_original", True) and (quote.get("corps") or "").strip():
        head = "Le %s, %s a écrit :" % (quote.get("date", ""), quote.get("de", ""))
        quoted = "\n".join(("> " + l) if l else ">" for l in quote["corps"].splitlines())
        text += "\n\n" + head + "\n" + quoted
    return text + "\n"


def build_draft(profile: Dict[str, Any], to: str, cc: str, subject: str, body: str,
                in_reply_to: str = "", references: str = "",
                quote: Optional[Dict[str, Any]] = None) -> bytes:
    msg = EmailMessage()
    msg["From"] = formataddr((profile.get("nom_affiche") or "", profile.get("email") or ""))
    if to.strip():
        msg["To"] = to.strip()
    if cc.strip():
        msg["Cc"] = cc.strip()
    msg["Subject"] = subject.strip()
    msg["Date"] = formatdate(localtime=True)
    domain = (profile.get("email") or "localhost").split("@")[-1] or "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg["X-Mailer"] = "Assistant Email"
    msg.set_content(compose_body(profile, body, quote), charset="utf-8")
    return msg.as_bytes(policy=policy.SMTP)
