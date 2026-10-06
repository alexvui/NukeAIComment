# NukeAIComment

Plugin Claude Code qui nettoie les commentaires générés par IA — **sans jamais
toucher au code**.

Les LLM commentent chaque ligne, décrivent ce que le code dit déjà, et remplissent
les blocs JSDoc de `@param items - The array of items`. Ce plugin retire ce bruit,
en cinq modes.

| Mode | Moteur | Effet |
|---|---|---|
| `scan` | script | Rapport : combien de commentaires, lesquels ont un style IA. Aucune écriture. |
| `nuke` | script | Supprime tous les commentaires non protégés. |
| `reduce` | script | Raccourcit sans reformuler : bloc → une ligne, remplissage retiré, troncature. |
| `synthesize` | script + modèle | Chaque bloc devient une ligne qui ne garde que le non-évident. |
| `humanize` | script + modèle | Réécrit au style « dev pressé » : minuscule, pas de point final, le pourquoi et pas le quoi. |

## Installation

```bash
/plugin marketplace add alexvui/NukeAIComment
/plugin install nuke-ai-comment@nuke-ai-comment
```

Le plugin fournit le skill `nuke-ai-comment` et la commande `/nuke`.

Python 3.8+ suffit — aucune dépendance externe.

## Utilisation

Dans Claude Code :

```
/nuke                     scan, puis proposition de mode
/nuke nuke                supprime, sur les fichiers modifiés selon git
/nuke reduce src/         raccourcit ce dossier
/nuke humanize            réécrit au style humain
```

En ligne de commande directe :

```bash
SCRIPT=~/.claude/plugins/.../nuke-ai-comment/scripts/nukeaicomment.py

python3 "$SCRIPT" scan --all
python3 "$SCRIPT" nuke src/            # simulation + diff
python3 "$SCRIPT" nuke src/ --apply    # écriture
python3 "$SCRIPT" restore              # annulation
```

## Ce qui est protégé

Rien de tout cela n'est supprimé, même en `nuke` :

- **Directives outils** — `eslint-disable`, `@ts-ignore`, `noqa`, `type: ignore`,
  `#pragma`, `go:build`, `rubocop:`, `shellcheck disable`, `DO NOT EDIT`… une
  centaine de motifs.
- **En-têtes** — shebang, déclaration d'encodage, licence et copyright.
- **Marqueurs** — `TODO`, `FIXME`, `HACK`, `XXX`, `NOTE`, `BUG`…
- **Documentation d'API** — docstrings, JSDoc, PHPDoc.

`--shrink-docs` raccourcit la documentation d'API sans jamais la supprimer.
`--include-docstrings` autorise sa suppression. `--no-keep-todo` et
`--include-headers` lèvent les autres protections.

## Pourquoi le code ne bouge pas

Trois mécanismes.

**Un scanner, pas une regex.** Une machine à états parcourt le fichier caractère par
caractère avec les règles du langage. Elle ne confond pas un commentaire avec :

```js
const url = "https://x.com";        // le // d'une chaîne
const re  = /path\/to\/[^/]+/g;     // le / d'une regex littérale
<div>{/* commentaire JSX */}</div>  // un délimiteur composite
```

ni avec un heredoc shell, un scalaire bloc YAML, ou du HTML hors `<?php ?>`.

**Le modèle ne produit jamais de code.** Pour `synthesize` et `humanize`, le script
écrit un plan JSON contenant les commentaires et leur contexte de lecture. Le modèle
remplit un champ texte, rien d'autre. Le script réinjecte par offset. Toute réponse
contenant un délimiteur de commentaire est nettoyée ou rejetée.

**Un invariant vérifié après écriture.** Le fichier modifié est re-scanné ; on retire
les commentaires des deux versions et on compare. Si le code diffère d'un caractère,
tout est restauré depuis la sauvegarde. S'y ajoutent les vérificateurs natifs quand
ils sont présents : `node --check`, `php -l`, `bash -n`, `ruby -c`, `gofmt -e`.

## Garde-fous

- Simulation par défaut ; `--apply` pour écrire.
- Dépôt git sale refusé sans `--force`.
- Sauvegarde dans `~/.nukeaicomment/backups/<projet>/<horodatage>/`,
  `restore` pour annuler, `restore --list` pour choisir.
- Hors dépôt git, la sauvegarde est obligatoire.

## Développement

```bash
PYTHONPATH=scripts python3 -m unittest discover -s tests -v
```

115 tests : machine à états par langage, protections, transformations, rendu,
plan JSON, sauvegarde, CLI de bout en bout, et l'invariant « le code ne bouge pas »
vérifié sur chaque fixture dans les trois configurations de protection.

Le design est documenté dans
[docs/superpowers/specs/](docs/superpowers/specs/2026-08-12-nuke-ai-comment-design.md).

## Licence

MIT — voir [LICENSE](LICENSE).
