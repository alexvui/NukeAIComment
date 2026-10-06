# NukeAIComment — Design

Date : 2026-08-12
Statut : validé

## Problème

Claude (et les LLM en général) produisent des commentaires longs, exhaustifs et
redondants : ils décrivent *ce que fait* la ligne suivante au lieu d'expliquer
*pourquoi* elle existe. Le code devient bruyant et se signale immédiatement comme
généré. Il faut un outil qui nettoie ces commentaires à la demande, sans jamais
toucher au code.

## Objectif

Un plugin Claude Code distribuable, `nuke-ai-comment`, exposant quatre
transformations sur les commentaires d'un projet, plus un mode rapport.

| Mode | Moteur | Effet |
|---|---|---|
| `scan` | script | Rapport seul : combien de commentaires, lesquels ressemblent à de l'IA. Aucune écriture. |
| `nuke` | script | Supprime tous les commentaires non protégés. |
| `reduce` | script | Rétrécit sans reformuler : bloc → une ligne, suppression du remplissage, troncature. |
| `synthesize` | script + LLM | Chaque bloc devient une ligne qui ne conserve que le non-évident. |
| `humanize` | script + LLM | `reduce` puis réécriture au style « dev pressé ». |

## Contraintes retenues

- **Python 3, stdlib uniquement.** Le plugin doit s'installer sans `pip install`.
- **Le LLM ne voit jamais le code entier et n'en produit jamais.** Il ne reçoit que
  des blocs de commentaires et un contexte de lecture ; il ne renvoie que du texte
  de commentaire.
- **Dry-run par défaut.** Rien n'est écrit sans `--apply`.
- **Le code non-commentaire doit être identique après transformation.** Invariant
  vérifié automatiquement, sur tous les langages, sans dépendance externe.

## Architecture

```
NukeAIcomment/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── commands/nuke.md
├── skills/nuke-ai-comment/
│   ├── SKILL.md
│   └── references/{humanize-style,synthesize-style,languages}.md
├── scripts/
│   ├── nukeaicomment.py          # point d'entrée
│   └── nukeai/
│       ├── languages.py          # table de syntaxe par langage
│       ├── scanner.py            # machine à états → spans de commentaires
│       ├── regions.py            # découpage multi-syntaxe (html/vue/svelte/php)
│       ├── classify.py           # protections + score « écrit par IA »
│       ├── reducer.py            # transformations déterministes
│       ├── rewrite.py            # application des éditions par offset
│       ├── verify.py             # invariant « code inchangé »
│       ├── guards.py             # git, backup, restore
│       ├── targets.py            # résolution des fichiers cibles
│       ├── planfile.py           # plan JSON pour les modes LLM
│       ├── report.py             # diff unifié + résumé
│       └── cli.py
└── tests/
```

### Scanner

Une machine à états parcourt le fichier caractère par caractère :

```
CODE → STRING → TEMPLATE → REGEX → LINE_COMMENT → BLOCK_COMMENT → CODE
```

Elle est paramétrée par une `LangSpec` (délimiteurs de commentaires, délimiteurs de
chaînes, échappement, littéraux regex, blocs imbricables). C'est ce qui évite les
trois faux positifs classiques :

```js
const url = "https://x.com";        // le // dans une chaîne
const re  = /path\/to\/[^/]+/g;     // le / d'une regex littérale
<div>{/* commentaire JSX */}</div>  // délimiteur composite
```

Règle supplémentaire pour les langages à `#` (Python, shell, YAML, TOML) : `#`
n'ouvre un commentaire qu'en début de ligne ou précédé d'une espace. Idem pour
`--` en SQL.

Chaque commentaire trouvé devient un objet avec : offsets début/fin, type
(`line` / `block` / `docstring`), indentation, position (seul sur sa ligne ou en fin
de ligne de code), texte brut, texte nu, et le code voisin (±3 lignes).

**Fichiers multi-syntaxe** (`.html`, `.vue`, `.svelte`, `.php`) : un pré-découpage en
régions attribue à chaque zone la `LangSpec` correcte (`<script>` → JS, `<style>` →
CSS, hors `<?php ?>` → HTML). Sans cela, `<a href="https://x">` serait vu comme un
commentaire de ligne.

**Langage inconnu** : le fichier est ignoré et signalé. Jamais deviné.

### Protections

Actives dans tous les modes, chacune désactivable explicitement. Un commentaire
protégé n'est jamais modifié ni supprimé.

1. **Directives outils** — `eslint-disable`, `@ts-ignore`, `prettier-ignore`, `noqa`,
   `type: ignore`, `pylint:`, `#pragma`, `//go:build`, `//nolint`, `rubocop:`,
   `phpcs:`, `shellcheck`, `istanbul ignore`, `sourceMappingURL`, `/*!`, etc.
2. **En-têtes** — shebang, déclaration d'encodage, blocs licence/copyright/SPDX dans
   les premières lignes.
3. **Marqueurs de dette** — `TODO`, `FIXME`, `HACK`, `XXX`, `NOTE`, `BUG`,
   `OPTIMIZE`, `REVIEW`, `DEPRECATED` (en majuscules, ou suivis de `:`).
4. **Documentation d'API** — docstrings Python, `/** */` JSDoc/PHPDoc/KDoc, `///` et
   `//!` Rust/C#.

Drapeaux : `--include-docstrings`, `--no-keep-todo`, `--include-headers`,
`--include-directives` (déconseillé, casse les builds).

### Score « écrit par IA »

Heuristiques cumulatives, servant au rapport et au filtre `--only-ai` :
reformulation de la ligne suivante, ouverture en « This function/method/class… »,
`@param` qui répète le type déjà déclaré, bannières décoratives
`// ===== SECTION =====`, énumérations « Step 1: », ratio commentaire/code élevé,
bloc de plus de 3 lignes pour une fonction de moins de 5 lignes.

### Flux LLM en deux temps

Pour `synthesize` et `humanize` :

```
1. script  --plan-out plan.json   {id, fichier, span, texte, contexte de lecture}
2. Claude lit plan.json, remplit new_text   (du texte, jamais du code)
3. script apply-plan plan.json    remplacement par offset, de la fin vers le début
```

Le script rejette tout `new_text` contenant des délimiteurs de commentaire, un
nombre de lignes supérieur au budget, ou un identifiant inconnu. Claude ne peut pas
modifier une ligne de code, même en essayant.

### Garde-fous

1. **Dry-run par défaut** — diff unifié + résumé ; `--apply` requis pour écrire.
2. **Git propre exigé** — refus si le working tree est sale, sauf `--force`. Hors
   dépôt git, le backup devient obligatoire.
3. **Backup** dans `.nukeaicomment-backup/<horodatage>/` ; `restore` restaure.
4. **Vérification post-écriture**, deux niveaux :
   - *Universelle* : on re-scanne le fichier modifié, on retire tous les commentaires
     des deux versions et on compare. Formellement :
     `canonical(t) = lignes de strip_comments(t), rstrip, sans lignes vides`.
     `canonical(avant) == canonical(après)` doit être vrai. Détecte toute atteinte au
     code, quel que soit le langage, sans dépendance.
   - *Native si disponible* : `python -m py_compile`, `node --check`, `php -l`,
     `bash -n`, `ruby -c`, `gofmt -e`.

   Échec → restauration des seuls fichiers fautifs depuis le backup, sortie en erreur.

Deux garde-fous se sont ajoutés à l'implémentation :

- Une docstring Python qui constitue à elle seule le corps de son bloc n'est jamais
  supprimée : la retirer laisserait un bloc vide. L'invariant universel ne détecte pas
  ce cas (la docstring disparaît des deux côtés de la comparaison), seul le
  vérificateur natif le voit — on préfère l'empêcher en amont.
- La restauration après échec est par fichier, pas globale : un fichier pathologique
  n'annule pas le travail sur les autres.

### Résolution des cibles

- Sans argument → fichiers modifiés selon git (staged + unstaged + untracked).
- `--all` → tout le dépôt, en respectant `.gitignore`.
- Chemins explicites (fichiers ou dossiers) → ces chemins.
- Toujours exclus : `node_modules`, `.git`, `dist`, `build`, `vendor`, `.venv`,
  `__pycache__`, fichiers minifiés (`.min.js`), fichiers > 1 Mo, binaires.

## Style de réécriture

`synthesize` : une ligne, ne garder que ce qu'on ne lit pas dans le code, langue
d'origine conservée.

`humanize` : minuscule initiale, pas de ponctuation finale, pas de préambule, pas de
reformulation du code, on explique le *pourquoi* ; un commentaire qui n'apporte rien
est supprimé plutôt que réécrit. Langue d'origine conservée.

## Tests

Corpus de fixtures `avant` / `attendu` par famille de langage, plus les cas pièges :
chaîne contenant `//`, regex JS, JSX, docstring Python vs commentaire, heredoc shell,
scalaire bloc YAML, HTML hors `<?php ?>`, commentaire imbriqué Rust. Invariant vérifié
sur chaque fixture : le code non-commentaire est inchangé.
