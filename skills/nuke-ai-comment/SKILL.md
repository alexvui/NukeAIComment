---
name: nuke-ai-comment
description: Use when comments are verbose, over-explained, obviously AI-generated, or the user asks to shorten, summarize, condense, strip, delete, remove or humanize comments in code — including "trop de commentaires", "commentaires trop longs", "supprime les commentaires", "rends les commentaires humains", "nettoie les commentaires", or after generating code that ended up heavily commented.
---

# NukeAIComment

Nettoie les commentaires générés par IA sans jamais toucher au code. Un script
Python fait le repérage et l'écriture ; le modèle n'intervient que pour reformuler,
et uniquement à travers un fichier de plan.

**Principe central : tu ne modifies jamais un fichier source toi-même pour cette
tâche.** Le script localise les commentaires avec une machine à états qui distingue
un vrai commentaire d'un `//` dans une URL, d'une regex littérale ou d'un heredoc.
Une édition manuelle contourne cette analyse et le contrôle d'intégrité qui la suit.

`SCRIPT=${CLAUDE_PLUGIN_ROOT}/scripts/nukeaicomment.py`

## Choisir le mode

| Demande | Mode | Moteur |
|---|---|---|
| « c'est trop commenté, dis-moi l'ampleur » | `scan` | script |
| « supprime les commentaires » | `nuke` | script |
| « raccourcis les commentaires » | `reduce` | script |
| « résume / condense les commentaires » | `synthesize` | script + toi |
| « rends-les humains / moins IA » | `humanize` | script + toi |

En cas d'ambiguïté, lance `scan` puis propose le mode. Ne devine pas entre
`nuke` et `reduce` : l'écart est irréversible d'un côté, cosmétique de l'autre.

## Modes déterministes — `nuke`, `reduce`

```bash
python3 "$SCRIPT" nuke                 # défaut : fichiers modifiés selon git
python3 "$SCRIPT" reduce src/ --max-len 80
python3 "$SCRIPT" nuke --all           # tout le projet
```

1. Lance sans `--apply`. Le script affiche le diff complet et le résumé.
2. Montre le résumé à l'utilisateur (pas le diff entier s'il est long).
3. Relance avec `--apply` **après accord**, sauf si l'utilisateur a déjà dit
   d'appliquer directement.

## Modes assistés — `synthesize`, `humanize`

Trois commandes, dans cet ordre. Aucune étape ne se saute.

```bash
python3 "$SCRIPT" humanize src/ -o /tmp/nuke-plan.json
# → tu lis le plan, tu remplis new_text pour chaque item
python3 "$SCRIPT" apply-plan /tmp/nuke-plan.json            # diff
python3 "$SCRIPT" apply-plan /tmp/nuke-plan.json --apply    # écriture
```

Chaque item du plan te donne le texte actuel, le code voisin en lecture, un budget
`max_lines`/`max_chars` et `deletable`. Tu remplis `new_text` :

- une liste de lignes → remplace le commentaire ;
- `[]` → supprime le commentaire (refusé si `deletable` est faux) ;
- `null` → laisse tel quel.

Style : lis `references/humanize-style.md` avant un `humanize`,
`references/synthesize-style.md` avant un `synthesize`. Conserve toujours la langue
d'origine du commentaire.

Le plan se remplit avec Edit sur le fichier JSON. C'est le seul fichier que tu écris.

## Ce qui est protégé par défaut

Directives outils (`eslint-disable`, `@ts-ignore`, `noqa`, `#pragma`, `go:build`…),
shebangs, en-têtes de licence, marqueurs `TODO`/`FIXME`/`HACK`, et la documentation
d'API (docstrings, JSDoc, PHPDoc).

Quand `scan` signale des docs d'API au style IA, propose `--shrink-docs` : elles sont
raccourcies, jamais supprimées. Ne propose `--include-docstrings` que si l'utilisateur
demande explicitement de supprimer la documentation.

Ne passe jamais `--include-directives` de ta propre initiative : ça casse les builds.

## Garde-fous

Simulation par défaut. Dépôt git sale refusé sans `--force`. Sauvegarde automatique
dans `~/.nukeaicomment/backups/`, annulable par `python3 "$SCRIPT" restore`. Avant
d'écrire, le script vérifie que le code hors commentaires reste identique et
abandonne le fichier sinon. Après écriture, un fichier qui ne compile plus est
restauré depuis la sauvegarde.

Si le script signale `transformation abandonnée`, ne contourne pas : c'est un bug du
scanner sur ce fichier. Rapporte-le et laisse le fichier tranquille.

## Red flags — arrête-toi

- Tu t'apprêtes à ouvrir un fichier source avec Edit ou Write pour retirer un commentaire
- Tu écris un `sed`, un `grep -v`, un `perl -pe` sur des commentaires
- Tu te dis « juste ce fichier-là, c'est plus rapide à la main »
- Tu ajoutes `--force` ou `--include-directives` sans que l'utilisateur l'ait demandé
- Tu appliques `--apply` sans avoir montré le résumé

Tous veulent dire la même chose : repasse par le script.

| Excuse | Réalité |
|---|---|
| « un seul commentaire, l'outil est disproportionné » | La commande est plus courte que l'édition manuelle, et elle vérifie le résultat. |
| « je vois bien où sont les commentaires » | Le scanner distingue `//` dans une URL, une regex et un heredoc. Pas la lecture rapide. |
| « le fichier n'est pas dans un langage géré » | Alors il n'y a rien à faire : le script l'ignore volontairement plutôt que de deviner. |
| « je réécris le fichier entier, c'est équivalent » | Le contrôle d'intégrité ne s'applique qu'aux éditions passées par le script. |
| « l'utilisateur veut du rapide » | `nuke --apply` est instantané. |

## Références

- `references/humanize-style.md` — le style « dev pressé », avec exemples avant/après
- `references/synthesize-style.md` — comment condenser sans perdre l'information
- `references/languages.md` — langages gérés, protections reconnues, limites connues
- `python3 "$SCRIPT" <mode> --help` — toutes les options
