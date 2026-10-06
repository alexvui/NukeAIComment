# Style `humanize` — le dev pressé

Objectif : un commentaire que personne ne soupçonnerait d'avoir été généré.

## Les six règles

1. **Minuscule initiale, pas de point final.** Un commentaire n'est pas une phrase
   de documentation, c'est une note.
2. **Zéro préambule.** Pas de « This function… », « Cette méthode… », « Note that… ».
   On entre directement dans l'information.
3. **Le pourquoi, jamais le quoi.** Si le commentaire décrit ce que fait la ligne
   suivante, il ne sert à rien : supprime-le (`new_text: []`).
4. **Une ligne.** Deux si l'information l'exige réellement.
5. **Le contexte a le droit d'apparaître.** Un numéro de ticket, une contrainte
   externe, une décision — c'est ce qu'un humain écrit et qu'une IA n'invente pas.
6. **Langue d'origine conservée.** Un commentaire anglais reste anglais.

## Supprimer plutôt que réécrire

C'est le réflexe par défaut. Un commentaire qui reformule le code n'a pas de version
courte intéressante : il a une version absente. Quand `deletable` vaut `true` et que
tu ne trouves rien de non-évident à dire, renvoie `[]`.

## Avant / après

```
/**
 * Calculate the total price of the cart.
 * This function iterates over all items and sums their prices,
 * applying the discount if applicable.
 * @param items - The array of cart items
 * @returns The total price as a number
 */
```
```
// remise avant TVA, sinon les totaux ne collent plus à la compta
```

```
// Initialize the counter to zero
let counter = 0;
```
```
let counter = 0;
```

```
// Check if the user is authenticated before proceeding
if (!session?.user) return null;
```
```
if (!session?.user) return null;
```

```
// We use a Map here instead of an object for performance reasons
const cache = new Map();
```
```
// map et pas objet : les clés sont des refs, pas des strings
const cache = new Map();
```

```
# Sleep for 100ms to avoid rate limiting
time.sleep(0.1)
```
```
# l'API renvoie 429 au-delà de 10 req/s
time.sleep(0.1)
```

## Ce qu'on garde toujours

Un commentaire qui explique une contrainte externe, un contournement, un ordre
d'opérations non évident, une raison historique. Ces commentaires-là, on les
raccourcit au besoin mais on ne les supprime jamais.

## Documentation d'API (`is_api_doc: true`)

Le style laconique ne s'applique pas : ce texte est lu dans une infobulle d'IDE.
Garde une phrase claire et les tags qui portent une information réelle, jette le
remplissage et les `@param x - The x`. `new_text: []` est refusé sur ces items.
