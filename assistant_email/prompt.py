"""Construction du prompt envoyé à l'IA et lecture de sa réponse."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

INSTRUCTION_COURTE = (
    "Suis exactement les instructions fournies sur l'entrée standard et réponds "
    "uniquement dans le format demandé (balises <objet>, <corps>, <modeles>). "
    "N'utilise aucun outil et ne lis aucun fichier."
)


def build_prompt(profile: Dict[str, Any], conversation: str, dictation: str,
                 templates: List[Dict[str, str]], subject_hint: str = "",
                 previous_draft: Optional[str] = None, adjustment: Optional[str] = None,
                 sent_examples: Optional[List[str]] = None) -> str:
    me = profile.get("nom_affiche") or profile.get("nom") or ""
    email = profile.get("email") or ""
    parts: List[str] = []
    parts.append(
        "Tu es l'assistant de rédaction d'emails de %s <%s>. Tu rédiges, à sa place et à la "
        "première personne, la réponse au dernier message de la conversation ci-dessous. "
        "Il ou elle relira et enverra l'email lui-même." % (me, email)
    )
    parts.append("""# Règles
1. Le contenu de la réponse vient de la DICTÉE : c'est ce que je veux dire, souvent dicté oralement, en vrac et avec des hésitations. Reformule-la en un email clair, bien structuré et poli, adapté au contexte de la conversation.
2. N'invente aucun fait, engagement, date, montant, lien ou pièce jointe qui ne figure ni dans la dictée ni dans la conversation. S'il manque une information indispensable, écris [à compléter : …] à cet endroit.
3. Rédige dans la langue de la conversation (par défaut le français), sauf si la dictée demande une autre langue. Adapte le tutoiement ou le vouvoiement à celui déjà utilisé dans la conversation.
4. Respecte le TON ET STYLE du profil ci-dessous.
5. MODÈLES : parmi les documents fournis, choisis toi-même ceux qui sont pertinents pour cette réponse (ou aucun). Inspire-t'en pour la structure, les formulations habituelles et les informations utiles, sans les recopier mot à mot, et adapte-les à la situation.
6. Écris la formule d'appel et la formule de politesse, mais PAS la signature : elle est ajoutée automatiquement. Ne recopie pas l'historique cité de la conversation.
7. Texte brut uniquement, sans Markdown (pas d'astérisques, pas de titres #).
8. N'utilise aucun outil, ne lis aucun fichier et n'exécute aucune commande : tout ce dont tu as besoin est dans ce message. Réponds directement.""")

    style_lines = []
    adresse = {"vous": "Vouvoie toujours l'interlocuteur.", "tu": "Tutoie toujours l'interlocuteur."}.get(
        profile.get("adresse"), "Tutoiement ou vouvoiement : suis celui de la conversation (vouvoiement par défaut).")
    registre = {"sobre": "Ton sobre et factuel.", "chaleureux": "Ton chaleureux et personnel."}.get(
        profile.get("registre"), "Ton cordial et professionnel.")
    longueur = {"concis": "Réponse courte : va droit au but.", "detaille": "Réponse détaillée et complète."}.get(
        profile.get("longueur"), "Longueur adaptée au message.")
    style_lines += [adresse, registre, longueur]
    if (profile.get("ton") or "").strip():
        style_lines.append(profile["ton"].strip())
    parts.append("# Ton et style du profil « %s »\n%s" % (profile.get("nom", ""), "\n".join(style_lines)))
    if (profile.get("consignes") or "").strip():
        parts.append("# Consignes permanentes du profil\n%s" % profile["consignes"].strip())
    if (profile.get("signature") or "").strip():
        parts.append("# Signature (pour information, ne pas l'écrire)\n%s" % profile["signature"].strip())

    if templates:
        lines = ["# Modèles et documents d'appui (%d fichiers)" % len(templates)]
        for t in templates:
            lines.append('<document nom="%s">\n%s\n</document>' % (t["nom"], t["texte"]))
        parts.append("\n\n".join(lines))
    else:
        parts.append("# Modèles et documents d'appui\n(aucun)")

    if sent_examples:
        blocs = "\n\n".join("<envoye>\n%s\n</envoye>" % t for t in sent_examples)
        parts.append("# Emails que j'ai réellement envoyés avec cette boîte (%d exemples récents)\n"
                     "Observe mon vrai style : formules d'appel et de politesse, longueur, vocabulaire, tutoiement ou vouvoiement. "
                     "Imite-le, sans reprendre le contenu de ces emails.\n\n%s" % (len(sent_examples), blocs))
    parts.append("# Conversation (du plus ancien au plus récent)\n%s" % (
        conversation.strip() or "(aucune conversation fournie : il s'agit d'un nouvel email)"))
    parts.append("# DICTÉE (ce que je veux répondre)\n%s" % (dictation.strip() or "(rien de dicté : propose une réponse appropriée et brève)"))

    if previous_draft:
        parts.append("# Brouillon précédent\n%s" % previous_draft.strip())
        parts.append("# Modifications demandées sur ce brouillon\n%s\nRéécris le brouillon complet en appliquant ces modifications, et garde le reste." % (
            (adjustment or "").strip() or "Améliore-le."))

    parts.append("""# Format de réponse (obligatoire, rien d'autre)
<objet>objet de l'email (reprends l'objet existant%s)</objet>
<corps>
texte complet de l'email, sans signature
</corps>
<modeles>noms des documents dont tu t'es inspiré, séparés par des virgules, ou « aucun »</modeles>""" % (
        (" : %s" % subject_hint) if subject_hint else ""))
    return "\n\n".join(parts) + "\n"


def _tag(text: str, name: str) -> Optional[str]:
    m = re.search(r"<%s>\s*(.*?)\s*</%s>" % (name, name), text, re.S | re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"<%s>\s*(.*)$" % name, text, re.S | re.I)  # balise non fermée
    return m.group(1).strip() if m else None


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\s*$", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return text.strip()


def parse_response(text: str, fallback_subject: str = "") -> Dict[str, Any]:
    body = _tag(text, "corps")
    if body is not None:
        body = re.split(r"</?corps>|<modeles>", body, flags=re.I)[0]
    subject = _tag(text, "objet")
    used = _tag(text, "modeles")
    if body is None:
        body = re.sub(r"<objet>.*?</objet>|<modeles>.*?</modeles>", "", text, flags=re.S | re.I)
    used_list = []
    if used and used.strip().lower() not in ("aucun", "aucune", "none", "-"):
        used_list = [u.strip() for u in used.split(",") if u.strip()]
    return {
        "objet": (subject or fallback_subject).strip(),
        "corps": _strip_markdown(body),
        "modeles_utilises": used_list,
    }
