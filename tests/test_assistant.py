import email
import imaplib
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

TMP = tempfile.mkdtemp()
os.environ["ASSISTANT_EMAIL_HOME"] = TMP
os.environ["ASSISTANT_EMAIL_TROUSSEAU"] = "memoire"
os.environ["FAKE_GEMINI_LOG"] = os.path.join(TMP, "gemini.json")

import fake_imap  # noqa: E402
imaplib.IMAP4_SSL = fake_imap.FakeIMAP

from assistant_email import (brouillon, config, gemini, imap_client, keychain, messages,  # noqa: E402
                             modeles, prompt, server, service)

MODELES = Path(TMP) / "modeles"


def setUpModule():
    MODELES.mkdir(exist_ok=True)
    (MODELES / "devis.md").write_text("# Réponse à une demande de devis\nMerci pour votre intérêt…", encoding="utf-8")
    (MODELES / "relance.txt").write_text("Je me permets de revenir vers vous…", encoding="utf-8")
    (MODELES / "image.png").write_bytes(b"\x89PNG")
    (MODELES / "sous").mkdir(exist_ok=True)
    (MODELES / "sous" / "conditions.md").write_text("Acompte de 30 % à la commande.", encoding="utf-8")
    # copiés hors du dossier partagé, qui n'autorise pas l'exécution
    for name, src in (("agy", "fake_agy.py"), ("gemini", "fake_gemini.py")):
        fake = Path(TMP) / "bin" / name
        fake.parent.mkdir(exist_ok=True)
        fake.write_text((ROOT / "tests" / src).read_text(), encoding="utf-8")
        fake.chmod(0o755)
    config.save_settings({"gemini_chemin": str(Path(TMP) / "bin" / "agy")})


def profil():
    (Path(TMP) / "profils.json").unlink() if (Path(TMP) / "profils.json").exists() else None
    return service.save_profile({
        "nom": "Pro", "nom_affiche": "Michael Test", "email": "moi@exemple.ch",
        "ton": "Vouvoiement, ton chaleureux et concis.", "signature": "Michael Test\nAtelier Exemple",
        "sources_modeles": [{"chemin": str(MODELES), "actif": True}], "mot_de_passe": "secret"})


class TestProfils(unittest.TestCase):
    def test_creation_et_mot_de_passe(self):
        p = profil()
        self.assertTrue(p["id"].startswith("pro-"))
        self.assertEqual(p["imap_utilisateur"], "moi@exemple.ch")
        self.assertEqual(p["imap_hote"], "mail.infomaniak.com")
        self.assertTrue(p["mot_de_passe_enregistre"])
        self.assertNotIn("mot_de_passe", json.loads((Path(TMP) / "profils.json").read_text()))
        p2 = service.save_profile({"id": p["id"], "ton": "Tutoiement"})
        self.assertEqual(p2["email"], "moi@exemple.ch")
        self.assertEqual(p2["ton"], "Tutoiement")
        service.delete_profile(p["id"])
        self.assertIsNone(keychain.get_password(p["id"]))

    def test_modeles(self):
        t = modeles.load_templates([str(MODELES)])
        self.assertEqual(sorted(x["nom"] for x in t), ["modeles/devis.md", "modeles/relance.txt", "modeles/sous/conditions.md"])
        self.assertEqual(modeles.load_templates(["/nexiste/pas", ""]), [])
        self.assertEqual(modeles.describe_source(str(MODELES))["nombre"], 3)
        self.assertEqual(modeles.describe_source(str(MODELES / "devis.md"))["type"], "fichier")
        self.assertEqual(modeles.describe_source("/nexiste/pas")["type"], "absent")

    def test_plusieurs_sources(self):
        p = profil()
        autre = Path(TMP) / "autre"
        autre.mkdir(exist_ok=True)
        (autre / "ton-perso.md").write_text("Je dis toujours « bien à vous ».", encoding="utf-8")
        config.save_settings({"sources_globales": [{"chemin": str(autre), "actif": True}]})
        try:
            names = [t["nom"] for t in modeles.load_templates(config.template_sources(p))] if False else \
                [t["nom"] for t in modeles.load_templates(config.template_sources(config.get_profile(p["id"])))]
            self.assertIn("autre/ton-perso.md", names)
            self.assertIn("modeles/devis.md", names)
            # une source désactivée est ignorée, un fichier seul est accepté
            service.save_profile({"id": p["id"], "sources_modeles": [
                {"chemin": str(MODELES), "actif": False}, {"chemin": str(MODELES / "devis.md")}]})
            names = [t["nom"] for t in modeles.load_templates(config.template_sources(config.get_profile(p["id"])))]
            self.assertEqual(sorted(names), ["autre/ton-perso.md", "devis.md"])
        finally:
            config.save_settings({"sources_globales": []})

    def test_ancien_format_dossier_modeles(self):
        (Path(TMP) / "profils.json").write_text(json.dumps([{"id": "vieux-1", "nom": "Vieux", "email": "a@b.ch",
                                                              "dossier_modeles": str(MODELES)}]))
        p = config.get_profile("vieux-1")
        self.assertEqual(p["sources_modeles"], [{"chemin": str(MODELES), "actif": True}])
        self.assertNotIn("dossier_modeles", p)


class TestTexte(unittest.TestCase):
    def test_recolle_les_paragraphes_coupes(self):
        t = ("Bonjour,\n\nLa Course de Noël se tient le 12 décembre 2026 dans la vieille ville de\n"
             "Sion. Nous sommes Pasta Mo', un nouveau service genevois : pâtes fraîches\n"
             "fabriquées à Genève, cuisinées à la minute sous notre tente, avec une\n"
             "option végétarienne.\n\nBien cordialement,\nMalik – Pasta Mo'\n\nSite : pastamo.ch\n- une puce assez longue pour dépasser les cinquante caractères\n- autre")
        out = messages.unwrap_text(t)
        self.assertIn("vieille ville de Sion. Nous", out)
        self.assertIn("avec une option végétarienne.", out)
        self.assertIn("Bien cordialement,\nMalik – Pasta Mo'", out)   # signature intacte
        self.assertIn("- une puce assez longue pour dépasser les cinquante caractères\n- autre", out)


class TestOutilsApp(unittest.TestCase):
    def test_sauvegarde_et_export(self):
        from assistant_email import sauvegarde
        profil()                                                         # l'enregistrement a déjà fait une copie
        self.assertTrue(any(d.is_dir() for d in sauvegarde.dossier().iterdir()))
        self.assertIsNone(sauvegarde.sauvegarder_si_modifie())          # rien n'a changé depuis
        service.save_profile({"id": config.load_profiles()[0]["id"], "ton": "Autre ton"})
        self.assertGreaterEqual(len([d for d in sauvegarde.dossier().iterdir() if d.is_dir()]), 2)
        out = sauvegarde.exporter(Path(TMP) / "export.json")
        data = json.loads(out.read_text())
        self.assertNotIn("secret", out.read_text())                      # aucun mot de passe exporté
        service.delete_profile(config.load_profiles()[0]["id"])
        self.assertEqual(config.load_profiles(), [])
        self.assertEqual(sauvegarde.importer(out)["profils"], 1)
        self.assertEqual(config.load_profiles()[0]["ton"], "Autre ton")
        (Path(TMP) / "faux.json").write_text('{"x": 1}')
        with self.assertRaises(ValueError):
            sauvegarde.importer(Path(TMP) / "faux.json")

    def test_action_rapide(self):
        import plistlib
        from assistant_email import action_rapide
        services = Path(TMP) / "Services"
        self.assertTrue(action_rapide.installer(services))
        self.assertFalse(action_rapide.installer(services))              # déjà à jour
        wf = services / "Répondre avec l'IA.workflow" / "Contents"
        info = plistlib.loads((wf / "Info.plist").read_bytes())
        self.assertEqual(info["NSServices"][0]["NSRequiredContext"]["NSApplicationIdentifier"], "com.apple.mail")
        wflow = plistlib.loads((wf / "document.wflow").read_bytes())
        self.assertIn("declencheur", wflow["actions"][0]["action"]["ActionParameters"]["COMMAND_STRING"])
        action_rapide.ecrire_declencheur("mail")
        self.assertEqual(action_rapide.lire_declencheur(), "mail")
        self.assertIsNone(action_rapide.lire_declencheur())              # consommé
        action_rapide.ecrire_declencheur("mail")
        self.assertIsNone(action_rapide.lire_declencheur(age_max=0))     # trop ancien : ignoré

    def test_mise_a_jour(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from assistant_email import updater
        vus = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                vus[self.path] = self.headers.get("Authorization")
                if self.path.endswith("/releases/latest"):
                    body = json.dumps({"tag_name": "v9.0.0", "body": "Nouveautés", "html_url": "http://x",
                                       "assets": [{"name": "AssistantEmail-9.0.0.dmg",
                                                   "url": "%s/repos/o/r/releases/assets/1" % updater.API}]}).encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
                elif self.path.endswith("/assets/1"):
                    self.send_response(302); self.send_header("Location", "http://localhost:%d/fichier" % self.server.server_port)
                    self.end_headers()
                else:
                    body = b"DMG"
                    self.send_response(200); self.send_header("Content-Length", "3"); self.end_headers(); self.wfile.write(body)

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = updater.API
        updater.API = "http://127.0.0.1:%d" % srv.server_port
        try:
            r = updater.check("o/r", "jeton123")
            self.assertTrue(r["disponible"])
            self.assertEqual(r["derniere"], "9.0.0")
            self.assertEqual(vus["/repos/o/r/releases/latest"], "Bearer jeton123")
            r["asset_url"] = "%s/repos/o/r/releases/assets/1" % updater.API
            path = updater.download(r["asset_url"], r["asset_nom"], "jeton123", Path(TMP))
            self.assertEqual(path.read_bytes(), b"DMG")
            self.assertIsNone(vus["/fichier"])                           # jeton non transmis à l'hôte de redirection
            with self.assertRaises(updater.UpdateError):
                updater.check("pas un depot", None)
            with self.assertRaises(updater.UpdateError):
                updater.download("http://evil.example/x", "a.dmg")
        finally:
            updater.API = old
            srv.shutdown()
        self.assertEqual(updater.parse_version("v1.10.0") > updater.parse_version("1.9.9"), True)


class TestImap(unittest.TestCase):
    def setUp(self):
        fake_imap.reset()
        self.p = profil()

    def test_list_parsing(self):
        f = imap_client.parse_list_line(b'(\\HasNoChildren \\Drafts) "." "INBOX.Brouillons"')
        self.assertEqual(f["nom"], "INBOX.Brouillons")
        self.assertIn("\\drafts", f["drapeaux"])
        self.assertEqual(imap_client.parse_list_line(b'() "/" Sent')["nom"], "Sent")
        self.assertEqual(imap_client.quote_mailbox("Archives 2025"), '"Archives 2025"')

    def test_connexion(self):
        r = service.test_profile({"id": self.p["id"]})
        self.assertEqual(r["brouillons"], "Brouillons")
        self.assertEqual(r["envoyes"], "Sent")
        with self.assertRaises(imap_client.ImapError):
            service.test_profile({"email": "x@y.ch", "mot_de_passe": "faux"})

    def test_liste_et_fil(self):
        res = service.list_messages(self.p["id"])
        lst = res["messages"]
        self.assertEqual([m["uid"] for m in lst], ["3", "1"])  # plus récent d'abord
        self.assertEqual((res["non_lus"], res["suivis"]), (1, 1))
        self.assertEqual([(m["lu"], m["suivi"]) for m in lst], [(False, True), (True, False)])
        self.assertEqual([m["uid"] for m in service.list_messages(self.p["id"], "INBOX", "non_lus")["messages"]], ["3"])
        self.assertEqual([m["uid"] for m in service.list_messages(self.p["id"], "INBOX", "suivis")["messages"]], ["3"])
        conv = service.conversation(self.p["id"], "3")
        self.assertEqual([m["message_id"] for m in conv["messages"]],
                         ["<a1@client.ch>", "<s2@exemple.ch>", "<a3@client.ch>"])
        self.assertIn("4800 CHF", conv["texte"])
        r = conv["reponse"]
        self.assertEqual(r["a"], "Claire Martin <claire@client.ch>")
        self.assertEqual(r["cc_tous"], "paul@client.ch")
        self.assertEqual(r["objet"], "Re: Devis site web")
        self.assertEqual(r["in_reply_to"], "<a3@client.ch>")
        self.assertEqual(r["references"], "<a1@client.ch> <s2@exemple.ch> <a3@client.ch>")

    def test_drapeaux_manuels(self):
        service.set_flag(self.p["id"], "INBOX", "3", "lu", True)
        service.set_flag(self.p["id"], "INBOX", "3", "suivi", False)
        res = service.list_messages(self.p["id"])
        self.assertEqual((res["non_lus"], res["suivis"]), (0, 0))
        # ouvrir un message ne le marque jamais comme lu
        fake_imap.FLAGS[("INBOX", 1)].discard("\\Seen")
        service.conversation(self.p["id"], "1")
        self.assertNotIn("\\Seen", fake_imap.FLAGS[("INBOX", 1)])
        with self.assertRaises(imap_client.ImapError):
            service.set_flag(self.p["id"], "INBOX", "3", "inconnu", True)

    def test_depot_brouillon(self):
        conv = service.conversation(self.p["id"], "3")
        r = conv["reponse"]
        out = service.deposit(self.p["id"], r["a"], "", r["objet"], "Bonjour Claire,\n\nOui.\n\nMichael Test",
                              r["in_reply_to"], r["references"], r["citation"])
        self.assertEqual(out["dossier"], "Brouillons")
        box, flags, raw = fake_imap.APPENDED[-1]
        self.assertEqual(box, "Brouillons")
        self.assertIn("\\Draft", flags)
        self.assertIn(b"\r\n", raw)
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        self.assertEqual(msg["In-Reply-To"], "<a3@client.ch>")
        self.assertEqual(msg["From"], "Michael Test <moi@exemple.ch>")
        body = msg.get_content()
        self.assertIn("Oui.", body)
        self.assertIn("> Merci ! Une question", body)

    def test_selection_apple_mail(self):
        raw = fake_imap.MAILBOXES["INBOX"][3]
        conv = service.conversation_from_raw(raw)
        self.assertEqual(conv["profil"], self.p["id"])  # profil retrouvé via l'adresse en Cc/À
        self.assertEqual(len(conv["messages"]), 3)


class TestPromptEtGemini(unittest.TestCase):
    def setUp(self):
        fake_imap.reset()
        os.environ.pop("FAKE_GEMINI_FAIL", None)
        self.p = profil()

    def test_prompt(self):
        t = modeles.load_templates([str(MODELES)])
        txt = prompt.build_prompt(dict(self.p, adresse="vous", registre="chaleureux", longueur="concis"),
                                  "conv", "oui le délai est ferme", t, "Re: X")
        for needle in ("Vouvoiement, ton chaleureux", "Vouvoie toujours", "Ton chaleureux et personnel", "Réponse courte",
                       '<document nom="modeles/devis.md">', "oui le délai est ferme",
                       "[à compléter", "<objet>", "PAS la signature"):
            self.assertIn(needle, txt)

    def test_parse(self):
        r = prompt.parse_response("bruit\n<objet>Re: A</objet><corps>Bonjour\n\n**Merci**</corps><modeles>aucun</modeles>")
        self.assertEqual(r, {"objet": "Re: A", "corps": "Bonjour\n\nMerci", "modeles_utilises": []})
        r = prompt.parse_response("<corps>Texte sans fin", "Re: B")
        self.assertEqual((r["objet"], r["corps"]), ("Re: B", "Texte sans fin"))
        self.assertEqual(prompt.parse_response("juste du texte")["corps"], "juste du texte")

    def test_generation_bout_en_bout(self):
        conv = service.conversation(self.p["id"], "3")
        r = service.generate(self.p["id"], conv["texte"], "dis lui que c'est ferme", conv["reponse"]["objet"])
        self.assertEqual(r["modeles_utilises"], ["devis.md"])
        self.assertTrue(r["corps"].endswith("Atelier Exemple"))
        self.assertNotIn("**", r["corps"])
        log = json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())
        self.assertEqual(log["mode"], "json")
        self.assertIn("--output-format", log["argv"])
        self.assertIn("--print-timeout", log["argv"])
        self.assertIn("4800 CHF", log["prompt"])
        self.assertIn("dis lui que c'est ferme", log["prompt"])
        self.assertNotEqual(Path(log["cwd"]).resolve(), ROOT)
        # Ajustement : la signature du brouillon précédent n'est pas renvoyée au modèle
        service.generate(self.p["id"], conv["texte"], "", "", r["corps"], "plus court")
        log = json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())
        self.assertIn("plus court", log["prompt"])
        prev = log["prompt"].split("# Brouillon précédent")[1]
        self.assertNotIn("Atelier Exemple", prev.split("# Modifications")[0])

    def test_style_des_envoyes(self):
        r = service.generate(self.p["id"], "conv", "oui")
        self.assertEqual(r["nb_envoyes"], 1)
        log = json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())
        self.assertIn("<envoye>", log["prompt"])
        self.assertIn("Voici le devis : 4800 CHF", log["prompt"])
        service.save_profile({"id": self.p["id"], "envoyes_nb": 0})
        r = service.generate(self.p["id"], "conv", "oui")
        self.assertEqual(r["nb_envoyes"], 0)
        self.assertNotIn("<envoye>", json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())["prompt"])

    def test_strip_quoted(self):
        t = "Bonjour,\nOui c'est bon.\n\nLe 12 oct. 2026 à 09:00, Claire <c@x.ch> a écrit :\n> blabla"
        self.assertEqual(messages.strip_quoted(t), "Bonjour,\nOui c'est bon.")

    def test_gros_prompt_par_stdin(self):
        r = service.generate(self.p["id"], "x" * 200000, "réponds")
        log = json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())
        self.assertEqual(log["mode"], "stream")
        self.assertNotIn("-p", log["argv"])
        self.assertEqual(r["modeles_utilises"], ["devis.md"])

    def test_ancienne_commande_gemini(self):
        config.save_settings({"gemini_chemin": str(Path(TMP) / "bin" / "gemini")})
        try:
            r = service.generate(self.p["id"], "conv", "oui")
            self.assertIn("6 semaines", r["corps"])
            log = json.loads(Path(os.environ["FAKE_GEMINI_LOG"]).read_text())
            self.assertIn("conv", log["stdin"])
        finally:
            config.save_settings({"gemini_chemin": str(Path(TMP) / "bin" / "agy")})

    def test_detection_automatique(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = str(Path(TMP) / "bin") + os.pathsep + old
        try:
            self.assertEqual(Path(gemini.find_gemini("")).name, "agy")  # agy avant gemini
            self.assertEqual(Path(gemini.find_gemini("gemini")).name, "gemini")
        finally:
            os.environ["PATH"] = old

    def test_erreur_gemini(self):
        os.environ["FAKE_GEMINI_FAIL"] = "1"
        with self.assertRaises(gemini.GeminiError) as ctx:
            service.generate(self.p["id"], "c", "d")
        self.assertIn("connectez-vous", str(ctx.exception))
        os.environ.pop("FAKE_GEMINI_FAIL")

    def test_html(self):
        raw = fake_imap.make("<h@x>", "a@x", "moi@exemple.ch", "S", "Mon, 12 Oct 2026 09:00:00 +0200",
                             "<html><style>p{}</style><p>Bonjour&nbsp;toi</p><p>Ligne 2</p></html>", html=True)
        msg = messages.parse_bytes(raw)
        msg.get_body(("plain",)).set_content("")  # force le passage par le HTML
        self.assertEqual(messages.html_to_text("<style>x</style><p>Bonjour&nbsp;toi</p><p>Ligne 2</p>"), "Bonjour toi\n\nLigne 2")


class TestServeur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.LocalServer(0).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def call(self, path, body=None, token=server.TOKEN):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.srv.port, path),
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Jeton": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_page_et_jeton(self):
        with urllib.request.urlopen(self.srv.url()) as r:
            page = r.read().decode()
        self.assertIn(server.TOKEN, page)
        self.assertEqual(self.call("/api/etat", token="mauvais")[0], 403)

    def test_parcours_complet(self):
        fake_imap.reset()
        p = profil()
        code, etat = self.call("/api/etat")
        self.assertEqual(code, 200)
        self.assertTrue(etat["gemini_trouve"])
        code, lst = self.call("/api/messages?profil=" + p["id"] + "&filtre=non_lus")
        self.assertEqual((code, lst["non_lus"]), (200, 1))
        code, _ = self.call("/api/drapeau", {"profil": p["id"], "uid": "3", "drapeau": "lu", "valeur": True})
        self.assertEqual(code, 200)
        code, lst = self.call("/api/messages?profil=" + p["id"])
        code, conv = self.call("/api/conversation", {"profil": p["id"], "uid": lst["messages"][0]["uid"]})
        code, gen = self.call("/api/generer", {"profil": p["id"], "conversation": conv["texte"], "dictee": "ferme",
                                               "objet": conv["reponse"]["objet"]})
        self.assertEqual(code, 200, gen)
        r = conv["reponse"]
        code, dep = self.call("/api/deposer", {"profil": p["id"], "a": r["a"], "objet": gen["objet"], "corps": gen["corps"],
                                               "in_reply_to": r["in_reply_to"], "references": r["references"]})
        self.assertEqual((code, dep["dossier"]), (200, "Brouillons"))
        code, err = self.call("/api/conversation", {"profil": "inconnu", "uid": "1"})
        self.assertEqual(code, 400)
        self.assertIn("Profil introuvable", err["erreur"])
        code, ev = self.call("/api/evenements")
        self.assertEqual(ev, {"actions": []})
        self.assertTrue(server.window_is_open())


if __name__ == "__main__":
    unittest.main(verbosity=2)
