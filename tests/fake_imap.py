"""Serveur IMAP simulé (remplace imaplib.IMAP4_SSL) pour les tests."""
import re

from email.message import EmailMessage

MAILBOXES = {}
APPENDED = []
FLAGS = {}   # (boîte, uid) -> ensemble de drapeaux


def make(mid, frm, to, subject, date, body, refs="", irt="", cc="", html=False):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"], m["Message-ID"] = frm, to, subject, date, mid
    if cc:
        m["Cc"] = cc
    if refs:
        m["References"] = refs
    if irt:
        m["In-Reply-To"] = irt
    if html:
        m.set_content("version texte")
        m.add_alternative(body, subtype="html")
        m.get_body(("plain",)).set_content(re.sub("<[^>]+>", "", body))
    else:
        m.set_content(body)
    return m.as_bytes()


def reset():
    MAILBOXES.clear()
    del APPENDED[:]
    FLAGS.clear()
    FLAGS[("INBOX", 1)] = {"\\Seen"}
    FLAGS[("INBOX", 3)] = {"\\Flagged"}
    MAILBOXES["INBOX"] = {
        1: make("<a1@client.ch>", "Claire Martin <claire@client.ch>", "moi@exemple.ch",
                "Devis site web", "Mon, 12 Oct 2026 09:00:00 +0200",
                "Bonjour,\nPourriez-vous m'envoyer un devis pour la refonte de notre site ?\nClaire"),
        3: make("<a3@client.ch>", "Claire Martin <claire@client.ch>", "Moi <moi@exemple.ch>",
                "Re: Devis site web", "Wed, 14 Oct 2026 10:00:00 +0200",
                "Merci ! Une question : le délai de 6 semaines est-il ferme ?\nClaire",
                refs="<a1@client.ch> <s2@exemple.ch>", irt="<s2@exemple.ch>", cc="paul@client.ch, moi@exemple.ch"),
    }
    MAILBOXES["Sent"] = {
        2: make("<s2@exemple.ch>", "Moi <moi@exemple.ch>", "claire@client.ch", "Re: Devis site web",
                "Tue, 13 Oct 2026 15:00:00 +0200", "Bonjour Claire,\nVoici le devis : 4800 CHF, délai 6 semaines.",
                refs="<a1@client.ch>", irt="<a1@client.ch>"),
    }
    MAILBOXES["Brouillons"] = {}


reset()


class FakeIMAP:
    PASSWORD = "secret"

    def __init__(self, host, port, ssl_context=None):
        self.host = host
        self.selected = None

    def login(self, user, password):
        import imaplib
        if password != self.PASSWORD:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Authentication failed.")
        return "OK", [b"Logged in"]

    def logout(self):
        return "BYE", [b""]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent"',
                      b'(\\HasNoChildren \\Drafts) "/" "Brouillons"', b'(\\HasNoChildren) "/" "Archives 2025"']

    def select(self, name, readonly=False):
        name = name.strip('"')
        if name not in MAILBOXES:
            return "NO", [b"no such mailbox"]
        self.selected = name
        self.readonly = readonly
        return "OK", [str(len(MAILBOXES[name])).encode()]

    def uid(self, cmd, *args):
        box = MAILBOXES[self.selected]
        if cmd == "SEARCH":
            if args[1] == "ALL":
                return "OK", [b" ".join(str(u).encode() for u in sorted(box))]
            if args[1] in ("UNSEEN", "FLAGGED"):
                want = "\\Flagged" if args[1] == "FLAGGED" else None
                hits = [u for u in sorted(box) if (want in FLAGS.get((self.selected, u), set()) if want
                                                    else "\\Seen" not in FLAGS.get((self.selected, u), set()))]
                return "OK", [b" ".join(str(u).encode() for u in hits)]
            if args[1] == "HEADER":
                want = args[3].strip('"')
                hits = [str(u).encode() for u, raw in box.items()
                        if re.search(rb"Message-ID: " + re.escape(want.encode()), raw, re.I)]
                return "OK", [b" ".join(hits)]
        if cmd == "FETCH":
            out = []
            for u in args[0].split(","):
                raw = box[int(u)]
                if "HEADER.FIELDS" in args[1]:
                    raw = raw.split(b"\n\n", 1)[0] + b"\n\n"
                fl = " ".join(sorted(FLAGS.get((self.selected, int(u)), set())))
                out.append((b"%d (UID %s FLAGS (%s) BODY[] {%d}" % (int(u), u.encode(), fl.encode(), len(raw)), raw))
                out.append(b")")
            return "OK", out
        if cmd == "STORE":
            assert not self.readonly, "STORE sur une boîte ouverte en lecture seule"
            flags = set(args[2].strip("()").split())
            key = (self.selected, int(args[0]))
            if args[1].startswith("+"):
                FLAGS.setdefault(key, set()).update(flags)
            else:
                FLAGS.setdefault(key, set()).difference_update(flags)
            return "OK", [b"done"]
        raise AssertionError(cmd)

    def append(self, mailbox, flags, date, message):
        APPENDED.append((mailbox, flags, message))
        return "OK", [b"[APPENDUID 1 1] Append completed."]
