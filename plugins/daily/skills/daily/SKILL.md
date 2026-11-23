---
name: daily
description: "Écrit la daily note du jour dans le vault Obsidian à partir des sessions Claude Code de la journée. Use when the user types /daily or asks for the daily note, the end-of-day recap, or « ce que j'ai fait avec Claude aujourd'hui »."
---

# Daily note des sessions Claude

Rédige `/home/nicolas/Documents/VAULT/6_DAILY/YYYY-MM-DD.md` à partir des transcripts Claude Code de la journée. Le fichier `/home/nicolas/Documents/VAULT/AGENTS.md` fixe les conventions du vault : lis-le avant d'écrire.

## 1. Extraire

```bash
python3 -I <dossier du skill>/scripts/extract.py [YYYY-MM-DD]
```

Sans argument, le script prend la date du jour. Il sort un JSON avec une entrée par session active ce jour-là : `session`, `launch_dir`, `cwd`, `branch`, `title`, `prs` et `turns`. Chaque turn contient l'heure, ton prompt et la dernière réponse qu'il a reçue. Les transcripts de subagents sont exclus.

Ne lis pas les `.jsonl` bruts. Si un turn est trop tronqué pour comprendre ce qui a été conclu, ouvre seulement le passage concerné du transcript (`~/.claude/projects/*/<session>.jsonl`).

## 2. Rédiger

Regroupe le travail par **sujet** et non par session : un même sujet peut couvrir plusieurs sessions, et une session peut traiter plusieurs sujets. Le repo et le ticket (`FIT-18`, etc.) servent à identifier le sujet.

Pour chaque sujet, écris :

- **Fait** : le résultat obtenu, pas le chemin suivi.
- **Décisions** : les choix tranchés pendant la session, avec leur raison si elle apparaît.
- **PR** : les liens de `prs` qui concernent ce sujet.
- **Pièges** : les comportements non évidents découverts (config trompeuse, hôte ou port inattendu, outil qui ment). Omets la ligne s'il n'y en a pas.
- **En suspens** : ce qui reste à faire, ou ce qui attend quelqu'un d'autre.
- **Sessions** : pour chaque session qui a traité ce sujet, son `session` complet suivi de son `launch_dir`. C'est le dossier où la session a été lancée, et `claude --resume` ne la retrouve que depuis ce dossier : `cd <launch_dir> && claude --resume <session>`. N'utilise pas `cwd` pour ça, car il peut avoir changé en cours de session.

Ne parle pas des échanges sans résultat (questions de navigation, essais abandonnés), sauf s'ils ont appris quelque chose.

Si un sujet relève d'un projet de `1_PROJECTS/` (regarde ces notes avant d'écrire), ajoute ` · [[<projet>]]` à la fin de son titre `###`. Ainsi, les backlinks de la note de projet donnent l'historique de ses journées. Relie de la même façon, dans le texte, les notes de `4_TOOLS/` ou de `7_GOTCHAS/` qui correspondent. Ne crée pas de note juste pour avoir quelque chose à lier.

## 3. Écrire

Utilise ce format :

```markdown
---
type: daily
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [daily]
---

## Avec Claude

<2-3 lignes : ce qui a avancé aujourd'hui>

### <Sujet> — `<repo>`
- **Fait** : …
- **Décisions** : …
- **PR** : …
- **Pièges** : …
- **En suspens** : …
- **Sessions** : `<session>` (`<launch_dir>`)

## À reprendre demain
- [ ] …
```

`À reprendre demain` rassemble tous les éléments `En suspens` sous forme de cases à cocher.

Si le fichier existe déjà (créé par Obsidian ou rempli par Nicolas), ne remplace que les sections `## Avec Claude` et `## À reprendre demain`, et mets à jour `updated`. Laisse tout le reste intact.

Pour finir, donne le chemin du fichier écrit et le nombre de sujets couverts.
