#!/usr/bin/env python3
"""Faux binaire `gemini` : enregistre ses arguments et l'entrée standard, renvoie une réponse au bon format."""
import json, os, sys
data = sys.stdin.read()
with open(os.environ["FAKE_GEMINI_LOG"], "w", encoding="utf-8") as fh:
    json.dump({"argv": sys.argv[1:], "stdin": data, "cwd": os.getcwd()}, fh)
if os.environ.get("FAKE_GEMINI_FAIL"):
    sys.stderr.write("Error: Please login again (auth expired)\n")
    sys.exit(1)
print("Loaded cached credentials.")
print("<objet>Re: Devis site web</objet>\n<corps>\nBonjour Claire,\n\nLe délai de **6 semaines** est ferme dès réception de l'acompte.\n\nMeilleures salutations\n</corps>\n<modeles>devis.md</modeles>")
