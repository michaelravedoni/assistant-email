# Assistant Email

Une petite application de la barre de menus macOS qui lit une conversation email, vous laisse **dicter** votre réponse en vrac, puis demande à **Antigravity CLI** (commande `agy`, votre abonnement Google AI Pro, sans clé API) de la rédiger proprement selon le **profil** de la boîte mail : ton, signature et dossier de modèles. Le brouillon reste modifiable, puis il est **déposé dans le dossier Brouillons** de votre boîte IMAP (ou copié pour être collé). Vous relisez et envoyez vous-même depuis votre client mail.

## Comment ça marche

```
Client mail (Apple Mail, Postbox, Thunderbird…)
        │  message sélectionné (Apple Mail)  ·  liste IMAP  ·  copier-coller
        ▼
Assistant Email (barre de menus ✉︎ + fenêtre)
        │  conversation + dictée + profil (ton, signature, modèles TXT/MD)
        ▼
commande « agy -p » en arrière-plan (abonnement déjà connecté)
        │  brouillon rédigé
        ▼
fenêtre : vous corrigez, ajustez (« plus court », « ajoute que… »)
        │
        ▼
dossier Brouillons IMAP (dans le bon fil de discussion)  ou  presse-papiers
```

Trois façons d'indiquer la conversation :

- **Boîte mail** : la liste des derniers messages du profil, lue en IMAP. Un clic charge le message et retrouve les messages précédents du fil (y compris vos réponses dans « Envoyés »).
- **Apple Mail** : menu ✉︎ › « Répondre au message sélectionné dans Mail ». Le profil est choisi d'après l'adresse destinataire.
- **Coller** : pour Postbox, Thunderbird ou n'importe quoi d'autre. Copiez la conversation, puis menu ✉︎ › « Répondre au texte copié ».

Pour dicter : bouton **🎙︎ Dicter** (il lance la dictée de macOS) ou touche **Fn deux fois**. Pour terminer, cliquez sur ✓ dans la bulle de dictée ou appuyez sur Fn. ⌘↩ lance la rédaction.

**Modèles et documents** : un profil peut avoir plusieurs sources (dossiers et fichiers TXT/Markdown, sous-dossiers compris), que l'on active ou désactive d'un interrupteur. Les sources **partagées** (Réglages) s'ajoutent à celles de chaque profil. Tout est transmis à l'IA, qui choisit elle-même ceux qui conviennent et s'en inspire sans les recopier ; la fenêtre indique ensuite de quels modèles elle s'est inspirée.

**Style appris de vos envoyés** : par profil, l'IA lit vos derniers emails envoyés (5 à 30, sans les citations) pour imiter votre vrai style. Désactivable.

**Façon d'écrire** : trois choix rapides (vous/tu/selon la conversation, sobre/cordial/chaleureux, concis/normal/détaillé) et un champ libre pour les nuances.

## Installation recommandée : le fichier .dmg

Une fois le code sur GitHub, une construction automatique (GitHub Actions, sur un Mac de GitHub) fabrique l'application **universelle** (Intel et Apple Silicon) et la dépose dans les **Releases** sous forme de `AssistantEmail-x.y.z.dmg`. Vous ne construisez rien vous-même.

1. Ouvrez le `.dmg` téléchargé, glissez **Assistant Email** dans **Applications**, lancez-le.
2. Premier lancement : sans compte Apple Developer, macOS demande une confirmation. Faites clic droit › **Ouvrir** › **Ouvrir** (ou, sous macOS 15 : Réglages Système › Confidentialité et sécurité › **Ouvrir quand même**). Une seule fois.
3. Menu ✉︎ › **Profils et réglages**.

**Mise à jour** : menu ✉︎ › « Rechercher une mise à jour… » (ou Réglages). Si une version plus récente existe, le bouton télécharge le `.dmg` ; glissez l'app dans Applications en remplaçant l'ancienne. Profils, sources de modèles et réglages sont dans `~/Library/Application Support/AssistantEmail/` (hors de l'app) : ils sont conservés. Les mots de passe sont dans le Trousseau. Une copie datée des profils est faite à chaque modification (20 gardées), avec export et import dans les Réglages.

Pour un dépôt privé, les Réglages demandent le dépôt (`propriétaire/dépôt`) et un **jeton d'accès** GitHub en lecture seule (GitHub › Settings › Developer settings › Fine-grained tokens › accès « Contents : Read-only » sur ce dépôt). Il est gardé dans le Trousseau.

**Publier une nouvelle version** (pour la personne qui développe) : augmenter `__version__` dans `assistant_email/__init__.py`, puis `git tag v0.3.0 && git push --tags`. La construction fait le reste.

**Sans compte Apple Developer** l'app est signée localement (signature « ad hoc ») : elle fonctionne, mais demande la confirmation ci-dessus. Avec un compte (99 $ par an), ajoutez dans GitHub › Settings › Secrets les clés `APPLE_CERT_P12`, `APPLE_CERT_PASSWORD`, `APPLE_SIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` : l'app est alors signée et notarisée, sans aucun avertissement.

## Dans Mail : action rapide

Au premier lancement, l'app installe l'action **« Répondre avec l'IA »**. Dans Mail, sélectionnez un message puis : menu **Mail › Services › Répondre avec l'IA**. Pour un raccourci clavier : Réglages Système › Clavier › Raccourcis clavier › Services › Général (ou « Mail ») › cochez l'action et double-cliquez à droite pour choisir la combinaison. L'assistant s'ouvre alors sur le message sélectionné.

## Non lus et suivis

La liste de la boîte affiche une pastille bleue pour les non lus et une étoile pour les suivis. Filtres **Tous / Non lus / ★** (le dernier choix est mémorisé par profil) et tri par date, non lus d'abord ou suivis d'abord. Ouvrir un message dans l'assistant **ne le marque jamais comme lu** : les boutons « Marquer lu » et « Suivre » en haut de la conversation sont les seules écritures faites sur vos messages, et seulement quand vous cliquez.

## Installation de secours (sans GitHub)

1. Téléchargez **AssistantEmail.zip** et ouvrez-le (double-clic) : un dossier `AssistantEmail` apparaît.
2. Double-cliquez sur **Installer.command**.
   - Si macOS refuse (« développeur non identifié ») : clic droit › **Ouvrir** › **Ouvrir**. Sur macOS 15 et suivants : Réglages Système › Confidentialité et sécurité › tout en bas, **Ouvrir quand même**.
   - Si macOS propose d'installer les « outils de ligne de commande », acceptez, puis relancez Installer.command.
3. L'installateur crée **~/Applications/Assistant Email.app**, propose de la lancer à l'ouverture de session, et l'icône **✉︎** apparaît en haut à droite.
4. Menu ✉︎ › **Profils et réglages** › créez un profil par boîte mail :
   - choisissez l'hébergeur (Infomaniak, Gmail, iCloud, Outlook ou autre : le serveur est rempli pour vous), puis le mot de passe (gardé dans le Trousseau macOS ; avec la double authentification, utilisez un mot de passe d'application) ;
   - façon d'écrire, signature, sources de modèles (boutons « Ajouter un dossier / un fichier ») ;
   - **Tester la connexion** vérifie le mot de passe et détecte les dossiers Brouillons et Envoyés (le test se lance aussi après un premier enregistrement).
5. En haut à gauche, sous « Assistant Email », un point vert indique « agy prêt ». Sinon, ouvrez **Réglages** et collez le résultat de `which agy` (dans un terminal). L'ancienne commande `gemini` fonctionne encore si vous l'indiquez à la place.

La première fois que vous utilisez « Apple Mail », macOS demande l'autorisation de piloter Mail : acceptez.

Pour mettre à jour : relancez Installer.command depuis la nouvelle version (profils et mots de passe sont conservés). Cette voie ne fabrique pas une app autonome : préférez le `.dmg`. Pour désinstaller : **Desinstaller.command**.

L'application a sa propre icône (Dock, Finder, barre de menus claire ou sombre). Pour la régénérer : `python3 tools/make_icons.py` (nécessite Pillow).

Des exemples se trouvent dans `exemples/` (deux modèles et un exemple de texte « Ton et style »).

## Où sont les données

- Profils et réglages : `~/Library/Application Support/AssistantEmail/` (`profils.json`, `reglages.json`)
- Mots de passe : Trousseau macOS, service « AssistantEmail-IMAP »
- Journal en cas de problème : `~/Library/Application Support/AssistantEmail/journal.log`

Rien n'est envoyé ailleurs qu'à votre serveur IMAP et à l'IA de Google (via la commande `agy`). L'interface n'écoute que sur votre Mac (127.0.0.1) et est protégée par un jeton aléatoire.

## Dépannage

| Symptôme | Solution |
| --- | --- |
| Pas d'icône ✉︎ | Ouvrez `journal.log` ci-dessus. Pour voir l'erreur directement : `~/Library/Application\ Support/AssistantEmail/venv/bin/python -m assistant_email --web` avec `PYTHONPATH=~/Library/Application\ Support/AssistantEmail/app`. |
| « L'IA a échoué… connectez-vous » | Lancez `agy` une fois dans un terminal pour renouveler la connexion Google. |
| « Commande agy introuvable » | Réglages : indiquez le chemin donné par `which agy` (souvent `~/.local/bin/agy`). |
| « Modèle inconnu » | Videz le champ Modèle des Réglages, ou choisissez-en un dans la liste `agy models`. |
| La dictée ne démarre pas | Activez-la dans Réglages Système › Clavier › Dictée, puis utilisez Fn deux fois. |
| Brouillon pas dans le bon dossier | Indiquez le nom exact du dossier Brouillons dans le profil (voir « Tester la connexion »). |
| La fenêtre s'ouvre dans le navigateur | pywebview n'a pas pu s'installer ; tout fonctionne quand même. |

## Pour les curieux : structure

```
assistant_email/
  barre_menus.py   menu ✉︎ (rumps), lance le serveur local et la fenêtre
  fenetre.py       fenêtre native WebKit (pywebview), sinon navigateur
  server.py        serveur local + API JSON
  service.py       la logique : conversation → prompt → IA → brouillon
  imap_client.py   IMAP : liste, fil de discussion, dépôt du brouillon
  messages.py      lecture des emails (texte, HTML), destinataires de la réponse
  prompt.py        consignes envoyées à l'IA et lecture de sa réponse
  gemini.py        appel « agy -p » en mode headless (ou l'ancien « gemini »), dans un dossier vide
  sauvegarde.py    copies datées, export et import des profils et réglages
  updater.py       recherche de nouvelle version (Releases GitHub)
  action_rapide.py action « Répondre avec l'IA » de Mail
  modeles.py       chargement des sources de modèles (dossiers, fichiers TXT / Markdown)
  assets/          icônes (app .icns, barre de menus)
  brouillon.py     fabrication du brouillon (en-têtes de fil, signature, citation)
  macos.py         Apple Mail (AppleScript), presse-papiers, choix de dossier
  web/index.html   l'interface
setup.py           construction de l'app (py2app) ; .github/workflows/build.yml : construction automatique
tests/             tests avec un serveur IMAP et un agy simulés
```

Tests : `python3 tests/test_assistant.py`.
