# Style `synthesize` — condenser sans perdre

Différence avec `humanize` : ici on **résume**, on ne change pas de registre. Le
commentaire reste une phrase propre ; il devient court.

## La règle

Une ligne, qui ne garde que ce qu'on ne peut pas lire dans le code.

Pour chaque bloc, pose-toi la question dans cet ordre :

1. Qu'est-ce que ce commentaire dit que le code ne dit pas ?
2. Si la réponse est « rien » → `new_text: []` quand `deletable` est vrai.
3. Sinon, écris cette réponse en une ligne, dans la langue d'origine.

## Avant / après

```
/**
 * Retry the request with exponential backoff.
 * This function will attempt the request up to maxRetries times, waiting
 * 2^n * 100ms between each attempt. If all attempts fail, the last error
 * is rethrown to the caller.
 */
```
```
/** Réessaie avec backoff exponentiel (2^n × 100 ms), relance la dernière erreur. */
```

```
# This block handles the migration of legacy user records.
# First we fetch all users with a null schema_version.
# Then we apply each migration step in order.
# Finally we mark them as migrated.
```
```
# migre les enregistrements sans schema_version, étape par étape
```

```
// The following code is a workaround for a bug in Safari 15 where
// the intersection observer does not fire for elements inside a
// position: sticky container.
```
```
// contournement Safari 15 : IntersectionObserver muet dans un conteneur sticky
```

## Ce qu'il ne faut pas faire

- Empiler les informations en une ligne à rallonge. Respecte `max_chars`.
- Garder une phrase par pure symétrie avec les autres commentaires du fichier.
- Traduire. La langue d'origine est conservée.
- Inventer une raison. Si le commentaire d'origine ne dit pas pourquoi, ton résumé
  ne peut pas le dire non plus.

## Documentation d'API (`is_api_doc: true`)

Garde le résumé en une phrase et les tags informatifs. Supprime les tags qui
répètent la signature (`@param items - The array of items`, `@returns The result`).
Le bloc lui-même est conservé : `new_text: []` est refusé.
