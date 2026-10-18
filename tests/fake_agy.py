#!/usr/bin/env python3
"""Faux binaire `agy` (Antigravity CLI) : mode headless -p / stream-json, enregistre ce qu'il reçoit."""
import json, os, sys
args = sys.argv[1:]
reponse = ("<objet>Re: Devis site web</objet>\n<corps>\nBonjour Claire,\n\nLe délai de **6 semaines** est ferme "
           "dès réception de l'acompte.\n\nMeilleures salutations\n</corps>\n<modeles>devis.md</modeles>")
if "--input-format" in args:
    line = sys.stdin.readline()
    prompt = json.loads(line)["message"]["content"]
    mode = "stream"
else:
    prompt = args[args.index("-p") + 1]
    mode = "json"
with open(os.environ["FAKE_GEMINI_LOG"], "w", encoding="utf-8") as fh:
    json.dump({"argv": args, "prompt": prompt, "mode": mode, "cwd": os.getcwd()}, fh)
fail = os.environ.get("FAKE_GEMINI_FAIL")
env = {"conversation_id": "c1", "status": "ERROR" if fail else "SUCCESS", "response": "" if fail else reponse,
       "duration_seconds": 1.2, "num_turns": 1, "usage": {"total_tokens": 10}}
if fail:
    env["error"] = "authentication required"
if mode == "json":
    print(json.dumps(env))
else:
    print(json.dumps({"event": "init", "conversation_id": "c1"}))
    print(json.dumps({"event": "step_update", "step": {"type": "thinking"}}))
    print(json.dumps({"event": "result", "result": env}))
sys.exit(1 if fail else 0)
