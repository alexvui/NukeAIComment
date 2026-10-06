---
description: Réduit, synthétise, supprime ou humanise les commentaires générés par IA
argument-hint: "[nuke|reduce|synthesize|humanize|scan] [chemins] [options]"
---

Utilise le skill `nuke-ai-comment` pour nettoyer les commentaires.

Arguments reçus : `$ARGUMENTS`

Interprétation :

- Premier mot parmi `scan`, `nuke`, `reduce`, `synthesize`, `humanize` → c'est le mode.
- Aucun mode donné → lance `scan` d'abord, montre le résultat, puis propose le mode
  qui correspond à ce que tu vois.
- Le reste des arguments (chemins, `--apply`, `--all`, `--shrink-docs`…) passe tel
  quel au script.
- Aucun chemin donné → le script cible les fichiers modifiés selon git.

Suis la procédure du skill sans la raccourcir : simulation d'abord, résumé à
l'utilisateur, écriture ensuite. Pour `synthesize` et `humanize`, passe par le
fichier de plan JSON.
