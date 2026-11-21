# Retro — design

Date : 2026-11-21. Statut : proposé, relu par un builder.

Inspiré de [`mattpocock/skills` › `engineering/retro`](https://github.com/mattpocock/skills/tree/main/skills/engineering/retro).

## Intention

Après plusieurs jours de travail avec Claude Code, sur plusieurs repos, relire ce qui s'est passé et améliorer
l'**environnement** de l'agent, pas le code : ce qui ferait que la prochaine session ne refasse pas la même erreur, ne
cherche pas la même information, ne soit pas corrigée sur le même point. Le skill de Pocock travaille sur une seule
session et ne fait que suggérer ; celui-ci croise les sessions d'une période pour ne retenir que ce qui se répète, et
applique ce que l'utilisateur choisit.

## Objectifs, non-objectifs, anti-objectifs

**Objectifs**

- Lire toutes les sessions Claude Code d'une période (7 jours par défaut), tous repos confondus.
- Retenir un constat seulement s'il revient dans au moins 2 sessions (ou gotchas), ou s'il a coûté cher une fois.
- Proposer pour chaque constat retenu une action, avec sa destination, son repo et ses preuves.
- Proposer la suppression des instructions existantes qui ne changent aucun comportement.
- Appliquer les actions choisies par l'utilisateur, sans commiter.

**Non-objectifs**

- Corriger du code applicatif.
- Produire une page HTML : le rapport est dans la conversation.
- Compiler la mémoire native de Claude Code ou réorganiser des instructions sans lien avec un constat.

**Anti-objectifs**

- Une règle tirée d'un incident isolé et sans coût.
- Des instructions qui grossissent à chaque retro sans jamais rien retirer.
- Un commit, un push ou une PR faits par le skill.
- Une troncature silencieuse : si toute la matière ne peut pas être lue, le skill le dit.
- Une proposition déjà refusée qui revient, quand l'utilisateur a donné un endroit pour noter les refus.

## Contraintes

- **Indépendance** : aucune dépendance obligatoire à un autre skill, à un plugin ou à un chemin propre à une machine.
  Tout ce qui est optionnel est conditionné à un prédicat observable.
- **Optionnel, brainstorming** : si le skill `superpowers:brainstorming` est disponible, l'approfondissement d'une
  action floue passe par lui ; sinon le skill pose lui-même les questions, une à la fois.
- **Optionnel, gotchas** : si la variable d'environnement `GOTCHAS_DIR` est définie et désigne un dossier existant, ses
  fichiers Markdown sont une matière de plus et l'endroit où noter les refus. Elle se définit par machine, de
  préférence dans `~/.claude/settings.json` (`"env": { "GOTCHAS_DIR": "…" }`). Sans elle, le skill fonctionne sur les
  seuls transcripts.
- **Données** : les transcripts peuvent contenir des secrets. Les condensés restent dans le scratchpad de la session
  (sinon `$TMPDIR`), ne sont jamais envoyés à un service externe ni copiés dans un repo.
- **Distribution** : plugin `retro` de la marketplace `claude-marketplace`, invocation manuelle uniquement
  (`disable-model-invocation: true`), commande `/retro:retro [période]`.
- **Script** : Python 3 de la bibliothèque standard seulement, lancé par `python3 -I`.

## Approches

**Quand lancer la retro** (décidé par l'utilisateur) :

- Sur la session en cours, en fin de session : pas de script, mais tout repose sur un seul incident. Écartée.
- **Sur les sessions d'une période, après plusieurs jours de travail. Retenue.**

**Périmètre** (décidé par l'utilisateur) : **toutes les sessions de la période, tous repos confondus**, pour voir ce qui
se répète d'un repo à l'autre, qui relève des instructions globales. Chaque action nomme le repo où elle s'applique.

**Lecture de la matière** (décidé par l'utilisateur) :

- O1 — Un script condense chaque session ; l'agent principal lit tous les condensés. Croisement direct, coût faible,
  mais le contexte sature au-delà d'un volume.
- O2 — Un sous-agent par repo lit ses transcripts et rend ses constats. Tient tout volume, mais ne voit pas ce qui se
  répète entre repos, sauf à l'agrégation.
- **Retenue : O1, avec repli O2 au-delà de 150 000 caractères de condensés.** Le repli est annoncé à l'utilisateur.
- Révisé après la relecture du builder (117 sessions sur 7 jours, ~15 projets) : le script ne garde que les signaux,
  pas chaque message, pour que O1 reste le cas courant ; le repli découpe en **lots de ~150 000 caractères**,
  regroupés par repo quand c'est possible, et les constats semblables sont rapprochés à l'agrégation, y compris entre
  repos. Rien n'est jamais coupé.

**Mémoire des refus** (décidé par l'utilisateur) : dans `GOTCHAS_DIR` quand la variable existe (le VAULT n'est pas au
même endroit sur toutes les machines) ; sinon rien n'est mémorisé.

**Gotchas** (décidé par l'utilisateur) : le retro **remplace** la compilation manuelle de l'inbox des gotchas vers la
mémoire. Cycle de vie d'un gotcha :

- `inbox` → `compiled` quand une action appliquée s'appuie sur lui ;
- `inbox` → `rejected` quand l'utilisateur refuse l'action qui s'appuie sur lui (avec la raison) ;
- reste `inbox` quand il est sous le seuil de preuve : il compte à la retro suivante.

**Repo d'une session** (choix du concepteur) : la racine git du `cwd` de la session ; deux clones du même remote sont
un seul repo. Les sessions lancées hors d'un repo (dossier personnel, dossier parent de plusieurs repos, notes)
forment un groupe « hors repo », compté pour le seuil de preuve, dont les actions ne visent que les instructions
globales ou la mémoire.

## Conception

### Fichiers

```
plugins/retro/
├── .claude-plugin/plugin.json
└── skills/retro/
    ├── SKILL.md
    └── scripts/condense.py
```

Entrée ajoutée à `.claude-plugin/marketplace.json` et section ajoutée au `README.md`, comme `architecture-improvements`.

### Déroulé du skill

1. **Période** : argument optionnel. Un nombre est un nombre de jours ; une date `YYYY-MM-DD` est un début ; sans
   argument, 7 jours.
2. **Condenser** : `python3 -I <dossier du skill>/scripts/condense.py --since <date> --out <dossier>`. Le script imprime
   un résumé JSON : nombre de sessions, repos, taille totale, fichier condensé par session, groupés par repo.
3. **Lire le cadre** de chaque repo présent : `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, et ce qui porte ses contrôles
   (`Makefile`, `composer.json`/`package.json` scripts, workflows CI). Lire aussi les instructions globales
   (`~/.claude/CLAUDE.md` et ses imports `@…`) et l'index de mémoire de chaque projet
   (`~/.claude/projects/<slug>/memory/MEMORY.md` s'il existe). C'est ce qui permet de savoir qu'un contrôle manque ou
   qu'une instruction existe déjà.
4. **Gotchas** : si `GOTCHAS_DIR` est utilisable, lire les fichiers `status: inbox` (matière) et `status: rejected`
   (refus passés à ne pas reproposer).
5. **Lire la matière** : sous 150 000 caractères, l'agent lit tous les condensés. Au-delà, un sous-agent
   `general-purpose` par lot de ~150 000 caractères (sessions regroupées par repo quand c'est possible), briefé avec
   la grille ci-dessous et la consigne de rendre chaque constat avec ses preuves ; l'agent principal agrège et
   rapproche les constats semblables, y compris entre lots et entre repos.
6. **Filtrer** : seuil de preuve, puis destination, puis élagage (sections suivantes).
7. **Restituer** dans la conversation, puis attendre le choix de l'utilisateur.
8. **Appliquer** les actions choisies, sans commiter. Une action floue est approfondie (brainstorming si disponible).
   Choix du concepteur :
   - une action « contrôle automatique » n'est **pas construite** : c'est du code, soumis aux règles du repo cible
     (test d'abord, validation de l'impact, gates). Le skill la décrit assez précisément pour qu'une session dédiée
     dans ce repo la réalise ;
   - avant d'écrire dans un repo, le skill lit son état git ; s'il a déjà des modifications non commitées, il ne
     l'écrit pas et le signale.
9. **Clore** : si `GOTCHAS_DIR` est utilisable, appliquer le cycle de vie des gotchas (section Approches), et noter
   chaque refus d'une action venue des transcripts dans un nouveau fichier `status: rejected`, avec sa raison.

### Ce que le script garde d'une session

Le script lit `~/.claude/projects/*/*.jsonl` modifiés depuis le début de la période, en ignorant les transcripts de
sous-agents et les entrées `isSidechain`. Il ne garde que les **signaux**, pour que la lecture de tous les condensés
par l'agent principal reste le cas courant. Pour chaque session qui a au moins un signal dans la période, un fichier
texte avec :

- l'en-tête : id, repo (racine git du `cwd`), branche, titre, première et dernière date, nombre de tours ;
- chaque `tool_result` en erreur (`is_error`), avec l'outil, un résumé de son entrée et le début de l'erreur ;
- les appels d'outil identiques répétés après un échec ;
- les interruptions et les refus de permission par l'utilisateur ;
- les messages humains susceptibles d'être une correction (qui suivent une action de l'agent et la contestent,
  la réorientent ou la refusent), tronqués ;
- pour chaque signal, le tour qui le précède : le message humain et la dernière réponse de l'assistant, tronqués.

Une session sans aucun signal n'est comptée que dans le résumé (nombre de sessions par repo).

### Grille de lecture

| Signal | Exemple de destination |
|---|---|
| L'utilisateur corrige l'agent sur le même point | Doc du repo ou instructions globales |
| Une erreur qu'un contrôle aurait attrapée | Contrôle automatique du repo |
| Une longue recherche d'un fichier ou d'une info | Pointeur de navigation dans la doc du repo |
| Une instruction existante ignorée ou mal comprise | Clarifier ou supprimer l'instruction |
| Un outil ou une commande coûteux, ou qui échoue en boucle | Doc du repo, script, permission |
| Une information inaccessible (logs, service tiers) | Accès outillé, documenté dans le repo |

### Seuil de preuve

Un constat est retenu s'il apparaît dans **au moins 2 sessions ou gotchas**, ou s'il a **coûté cher une fois** : une
correction explicite de l'utilisateur, au moins 3 échecs consécutifs du même outil, un retour en arrière demandé. Les
autres sont écartés, cités en une ligne chacun.

### Destination, de la plus forte à la plus faible

1. Contrôle automatique du repo (test, lint, règle d'analyse statique, cible de build).
2. Doc du repo (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, doc d'architecture).
3. Instructions globales (`~/.claude/CLAUDE.md` et ses imports).
4. Mémoire du projet.
5. Nouveau skill : proposé et décrit, jamais créé sans approfondissement.

Un constat qui revient dans plusieurs repos va au niveau global, sauf s'il relève d'un contrôle propre à chaque repo.

### Élagage

Le skill relit les instructions des repos présents et les instructions globales, et propose de supprimer une
instruction quand : elle répète un contrôle automatique existant, elle répète une autre instruction, ou les sessions de
la période montrent qu'elle n'a pas d'effet. Chaque suppression cite sa raison.

### Restitution

Dans cet ordre :

1. **Matière lue** : période, nombre de sessions par repo, gotchas lus, repli O2 éventuel.
2. **Actions** `A1…` : destination, repo, fichier, ce qui change, preuves (session, date, extrait court).
3. **Élagage** `P1…` : instruction, fichier, raison.
4. **Écartés** : une ligne par constat sous le seuil.

Termine en demandant quelles actions appliquer.

## Laissé au builder

- Les longueurs de troncature et le format exact des condensés.
- La détection des appels répétés et des retours en arrière à partir du format JSONL.
- Le nom exact des fichiers condensés et du résumé JSON.
- Le format des gotchas que le skill écrit pour un refus venu des transcripts, aligné sur les fichiers déjà présents
  dans `GOTCHAS_DIR`.
