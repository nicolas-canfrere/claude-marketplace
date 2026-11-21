---
name: retro
description: "Use when the user asks for a retrospective of their recent Claude Code sessions, to find what keeps going wrong across sessions and repos and fix the agent's environment (checks, repo docs, global instructions, memory), or to compile their gotchas inbox: « fais une retro », « qu'est-ce qui coince dans mes sessions », /retro. Not for reviewing code or a pull request."
argument-hint: "[jours | YYYY-MM-DD]"
disable-model-invocation: true
---

# Retro des sessions Claude Code

Relis les sessions d'une période, tous repos confondus, et améliore l'**environnement** de l'agent : ce qui ferait que
la prochaine session ne refasse pas la même erreur, ne cherche pas la même information, ne soit pas corrigée sur le
même point. Le skill ne corrige pas de code applicatif et ne commite jamais.

## Principe

- **Un constat se prouve par la répétition.** Une règle tirée d'un incident isolé et sans coût alourdit les
  instructions sans rien éviter.
- **La destination la plus forte gagne.** Un contrôle automatique vaut mieux qu'une phrase dans une doc, qui vaut
  mieux qu'une instruction globale, qui vaut mieux qu'une mémoire.
- **Retirer compte autant qu'ajouter.** Une instruction qui ne change aucun comportement coûte à chaque session.

## 1. Période

- Sans argument : les 7 derniers jours.
- Un nombre : ce nombre de jours.
- Une date `YYYY-MM-DD` : depuis cette date.

## 2. Condenser

Lance, avec le dossier de base de ce skill et le répertoire scratchpad de la session (sinon `$TMPDIR`) :

```bash
python3 -I <dossier du skill>/scripts/condense.py --since <YYYY-MM-DD> --out <scratchpad>/retro
```

Le script ne garde de chaque session que ses **signaux** (`tool_error`, `repeat`, `interrupt`, `denial`,
`correction`), chacun avec le tour qui le précède, et écrit un fichier par session qui en a. Il imprime un résumé
JSON : `sessions`, `sessions_with_signals`, `total_chars`, `repos` (nom, nombre de sessions, fichiers, taille) et
`batches` (les lots de lecture). Un repo est la racine git du dossier de la session ; deux clones du même remote sont
un seul repo ; les sessions lancées hors d'un repo forment le groupe `hors repo`.

Les condensés peuvent contenir des secrets : ils restent dans le scratchpad, ne sont jamais copiés dans un repo ni
envoyés à un service externe.

## 3. Lire le cadre

Pour chaque repo du résumé (sauf `hors repo`), lis `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, et ce qui porte ses
contrôles (`Makefile`, scripts de `composer.json` ou `package.json`, workflows CI). Lis les instructions globales
(`~/.claude/CLAUDE.md` et les fichiers qu'il importe par `@…`) et l'index de mémoire de chaque projet
(`~/.claude/projects/<slug>/memory/MEMORY.md` s'il existe).

C'est ce qui dit si un contrôle manque, si une instruction existe déjà, et ce qu'il serait possible de retirer.

## 4. Gotchas (optionnel)

Si la variable d'environnement `GOTCHAS_DIR` est définie et désigne un dossier existant :

- les fichiers en `status: inbox` sont une matière de plus, au même titre qu'un signal ;
- les fichiers en `status: rejected` sont des refus passés : ne repropose pas ce qu'ils couvrent.

Sinon, dis-le en une ligne et continue sur les seuls transcripts.

## 5. Lire la matière

- **Un seul lot** dans `batches` : lis tous les condensés toi-même.
- **Plusieurs lots** : annonce-le, puis délègue chaque lot à un sous-agent `general-purpose`, en parallèle, avec ce
  brief :

  > Lis en entier chacun de ces fichiers : <liste des fichiers du lot>. Ce sont des sessions Claude Code condensées
  > à leurs signaux. Relève ce qui va mal de façon répétée, selon cette grille : <grille de la section 6>. Pour
  > chaque constat, rends : ce qui se passe, les sessions concernées (id, repo, date) et un extrait court par
  > session. Un constat vu une seule fois n'est rendu que s'il est une correction explicite de l'utilisateur, au
  > moins 3 échecs consécutifs du même outil, ou un retour en arrière demandé. Ne propose aucune modification.

  Agrège ensuite les constats et rapproche ceux qui décrivent la même chose, entre lots et entre repos.

Un signal `correction` vient d'une liste de marqueurs : vérifie dans son contexte qu'il corrige vraiment l'agent
(« …, non ? » est une question, pas une correction).

## 6. Grille de lecture

| Signal | Exemple de destination |
|---|---|
| L'utilisateur corrige l'agent sur le même point | Doc du repo ou instructions globales |
| Une erreur qu'un contrôle aurait attrapée | Contrôle automatique du repo |
| Une longue recherche d'un fichier ou d'une info | Pointeur de navigation dans la doc du repo |
| Une instruction existante ignorée ou mal comprise | Clarifier ou supprimer l'instruction |
| Un outil ou une commande coûteux, ou qui échoue en boucle | Doc du repo, script, permission |
| Une information inaccessible (logs, service tiers) | Accès outillé, documenté dans le repo |

## 7. Filtrer

**Seuil de preuve.** Garde un constat s'il apparaît dans **au moins 2 sessions ou gotchas**, ou s'il a **coûté cher
une fois** : correction explicite de l'utilisateur, au moins 3 échecs consécutifs du même outil, retour en arrière
demandé. Les autres sont écartés.

**Destination**, de la plus forte à la plus faible :

1. Contrôle automatique du repo (test, lint, règle d'analyse statique, cible de build).
2. Doc du repo (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, doc d'architecture).
3. Instructions globales (`~/.claude/CLAUDE.md` et ses imports).
4. Mémoire du projet.
5. Nouveau skill : décrit, jamais créé sans approfondissement.

Un constat qui revient dans plusieurs repos va au niveau global, sauf s'il relève d'un contrôle propre à chaque repo.
Un constat du groupe `hors repo` ne vise que les instructions globales ou la mémoire.

**Élagage.** Propose de supprimer une instruction existante quand elle répète un contrôle automatique, répète une
autre instruction, ou quand les sessions de la période montrent qu'elle n'a pas d'effet. Donne la raison.

## 8. Restituer

Dans la conversation, dans cet ordre :

1. **Matière lue** : période, sessions par repo, sessions avec signaux, gotchas lus, lots et sous-agents éventuels.
2. **Actions** `A1…` : destination, repo, fichier, ce qui change, preuves (session, date, extrait court).
3. **Élagage** `P1…` : instruction, fichier, raison.
4. **Écartés** : une ligne par constat sous le seuil.

Termine en demandant quelles actions appliquer.

## 9. Appliquer

Pour chaque action choisie :

- **Contrôle automatique** : ne le construis pas, c'est du code soumis aux règles du repo cible (test d'abord,
  validation de l'impact, gates). Décris-le assez précisément pour qu'une session dédiée dans ce repo le réalise.
- **Autre destination** : lis d'abord l'état git du repo (`git -C <repo> status --short`). S'il a des modifications
  non commitées, n'y écris pas et signale-le. Sinon, applique la modification, sans commiter.
- **Action floue** : si le skill `superpowers:brainstorming` est disponible, approfondis-la avec lui. Sinon, pose les
  questions une à une avant d'écrire.

## 10. Clore

Si `GOTCHAS_DIR` est utilisable :

- un gotcha sur lequel s'appuie une action appliquée passe en `status: compiled` ;
- un gotcha sur lequel s'appuie une action refusée passe en `status: rejected`, avec la raison du refus ;
- un gotcha sous le seuil reste en `status: inbox` : il comptera à la retro suivante ;
- une action refusée qui ne venait que des transcripts devient un nouveau fichier dans `GOTCHAS_DIR`, au format des
  fichiers déjà présents, en `status: rejected`, avec la raison.

Le scratchpad n'est pas nettoyé à la main : il disparaît avec la session.

## Erreurs courantes

| Erreur | Correction |
|---|---|
| Ajouter une règle après un seul incident sans coût | Appliquer le seuil de preuve, ranger le constat dans « Écartés » |
| Tout envoyer dans les instructions globales | Chercher d'abord un contrôle, puis la doc du repo |
| Ne jamais rien retirer | Faire l'élagage à chaque retro |
| Prendre chaque signal `correction` pour une correction | Relire son contexte |
| Écrire dans un repo qui a des modifications en cours | Vérifier `git status` avant, signaler et passer |
| Construire un test ou une règle de lint | Le décrire pour une session dédiée au repo |
| Lire les `.jsonl` bruts | Passer par `condense.py` |
