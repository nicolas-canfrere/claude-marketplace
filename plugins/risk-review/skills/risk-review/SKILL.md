---
name: risk-review
description: "Use when the user asks how risky a diff, a branch or a PHP/Symfony pull request is to merge or deploy in a microservices context, or what to check before shipping it: « est-ce risqué de merger », « niveau de risque de la PR », « que vérifier avant la mise en prod », /risk-review. Rates the risk (Faible/Modéré/Élevé/Critique) with its reasons, the checks to run first and the deployment plan. Not for line-by-line bug hunting: use /code-review."
---

# Review avec niveau de risque (PHP / Symfony / microservices)

Objectif : dire **à quel point ce changement peut casser quelque chose en production**, pourquoi, et quoi vérifier avant de merger. La qualité du code (style, nommage) passe après : on ne la signale que si elle crée un risque.

Étapes : récupérer le changement (§1), classer les fichiers par zone (§2), appliquer les points de contrôle de chaque zone (§3), noter (§4), rédiger la sortie (§5).

## 1. Récupérer le changement

### Source

Dans cet ordre, prendre la première source disponible :
- **une PR indiquée** : `gh pr view <n> --json title,body,baseRefName,baseRefOid,headRefOid,files,commits,state,mergedAt`. Récupérer les deux versions : `git fetch origin <baseRefOid> pull/<n>/head`, puis désigner chaque version par son SHA, jamais par `FETCH_HEAD`, qu'un fetch ultérieur écrase. Diff sans le lock : `git diff <baseRefOid>...<headRefOid> -- . ':!composer.lock'`. Si ce diff est vide ou ne correspond pas au champ `files`, revenir à `gh pr diff <n>`. Lire les fichiers à la version de la PR, pas dans la copie de travail (qui peut être sur une autre branche) : `git show <headRefOid>:<chemin>`. Remplacer `<baseRefOid>` et `<headRefOid>` par la valeur du SHA collée en clair, jamais par une variable shell : sous zsh, `$H:app/…` est lu comme un modificateur (`:a`, `:h`, `:s`…) et casse la commande. Exemple : `git show 3f9c2e1:src/Foo.php`. Si le repo courant n'est pas celui de la PR, chercher un clone local de ce repo (dossiers voisins) et y travailler ; à défaut, lire les fichiers avec `gh api -H 'Accept: application/vnd.github.raw' 'repos/<owner>/<repo>/contents/<chemin>?ref=<headRefOid>'` et chercher les appelants avec `gh search code`.
- **une branche** : `git fetch origin`, puis déterminer la base avec `git symbolic-ref --short refs/remotes/origin/HEAD` (à défaut : `origin/main`, `origin/master` ou `origin/develop`). Toujours comparer à la base distante, jamais à la branche locale, qui peut être périmée et faire entrer dans le diff des commits déjà mergés : `git diff <base>...HEAD`. Si la copie de travail contient aussi des modifications non commitées, les inclure avec `git diff $(git merge-base <base> HEAD)` et le signaler dans la sortie.
- **les changements locaux sur la branche de base** : `git diff HEAD`.
- **un diff ou des fichiers collés** par l'utilisateur.

### Périmètre du diff

Lire d'abord le `CLAUDE.md` ou l'`AGENTS.md` du repo : il peut déclarer des fichiers générés ou des conventions utiles à la revue.

Lister les fichiers modifiés : pour une PR, avec le champ `files` de `gh pr view` (lignes ajoutées et supprimées par fichier ; `gh pr diff` n'accepte pas `--stat`) ; pour une branche, avec `git diff --stat <base>...HEAD`.

Ne pas analyser ligne à ligne le contenu de `composer.lock` (seulement les paquets ajoutés, retirés ou dont la version change, par exemple `git diff <base>...<head> -- composer.lock | grep -E '^[-+] +"(name|version)"'`), les fichiers générés, les snapshots ni les baselines d'outils (PHPStan, Psalm). Reconnaître un fichier généré par le `CLAUDE.md` ou l'`AGENTS.md`, un en-tête `@generated` ou `DO NOT EDIT`, ou un `linguist-generated` dans `.gitattributes`. Un contrat généré (spec OpenAPI) ne s'analyse pas ligne à ligne : comparer entre les deux versions l'ensemble des chemins et opérations, et les propriétés de chaque schéma (par exemple `yq '.paths | keys'` et `yq '.components.schemas'`). Un bloc déplacé produit des lignes `-` sans rien supprimer : seul un élément absent de la version après déclenche le plancher « champ supprimé ».

### Description et historique

Lister les commits (champ `commits` de `gh pr view`, ou `git log <base>..HEAD`) et comparer la description de la PR au diff et à son état (une PR mergée dont le titre ou la description dit encore « DRAFT » ou « do not merge » se signale). Un changement de comportement absent de la description s'examine en priorité et se signale dans la sortie : c'est celui qui échappe aux relecteurs.

Même traitement pour l'historique interne de la PR :
- un commit annulé par un revert ou corrigé plusieurs fois signale un point débattu : l'examiner et vérifier l'argument du revert ;
- une migration ajoutée puis modifiée par un commit suivant (le diff la montre comme ajoutée) a pu tourner dans sa première version sur un environnement persistant (staging, éphémère) : vérifier la table des versions de migrations (nom défini par `table_storage` dans la config des migrations, `doctrine_migration_versions` par défaut) et le schéma réel de cet environnement, ou en faire une case à cocher.

### Appelants et consommateurs

Pour chaque fichier à risque, **lire le fichier complet et ses appelants dans le repo** (grep sur le nom de la classe ou de la méthode), pas seulement les lignes du diff. Fichiers et appelants se lisent à la même version que le diff (`<headRefOid>` pour une PR : `git grep <motif> <headRefOid>`).

Une classe neuve n'est atteignable que si elle est câblée : vérifier sa déclaration dans le conteneur (autowiring, `services.*`, configuration DI propre au repo) et son point d'entrée (route, handler, abonné, commande). Pour une PR mergée, `git log <headRefOid>..origin/<base> -- <fichiers de configuration DI>` date le moment où elle est devenue atteignable.

Le grep ne trouve pas les consommateurs situés dans d'autres services. Dès que le diff rompt un contrat existant vu par d'autres services (suppression, renommage, changement de type ou de sémantique ; un ajout compatible n'en a pas besoin), les chercher avec le CLI `rchiv`, au plus quatre appels. L'appeler directement comme le décrivent les §2.0 et §2.1 du skill `engineering:context-acquisition` (invocation, lecture des réponses, codes de sortie), sans dérouler ce skill : ses phases 2 et 3 (wiki, rapport en anglais) ne servent pas ici.
- **message ou event asynchrone : obligatoire pour toute routing key émise ou modifiée par le diff**, même portée par une classe neuve et même sans rupture apparente, avec `trace-event <routing_key>` (émetteurs et abonnés). Une recherche de code (`gh search code`) ne suffit pas : l'abonné déclare sa propre classe de message et son binding de queue, sans le nom de classe de l'émetteur.
- **route HTTP** : `trace-origin-endpoint <service> <method> <path>` pour la route précise. `who-calls <service>` ne renvoie qu'un échantillon de routes et ne prouve pas qu'un appelant utilise celle-ci. `gh search code` sur le chemin de la route est un complément, pas un substitut : il ne cherche que dans les branches par défaut et rate les URL construites dynamiquement.
- **table lue par un autre service** : `who-accesses <table>`, qui ne donne que des compteurs. Confirmer chaque lecteur dans son code (clone local ou `gh search code --owner Evaneos <table>`) : étape obligatoire.
- **table exportée vers l'entrepôt de données** : `rchiv` ne voit pas Airbyte. La source qui fait foi est la déclaration des sources dans `Evaneos/data-platform-dbt` (`src/models/medallion/bronze/src_<service>.yml`) : lire le fichier du service, ou `gh search code --repo Evaneos/data-platform-dbt <table>`.

Le registre `rchiv` est un indice (§4, « Indice ou preuve ») : un consommateur compte s'il est confirmé dans le code de sa branche par défaut. Si le code le contredit (registre périmé), ne pas le compter, le signaler et proposer de corriger le registre avec le skill `engineering:rchiv-feedback`.

Un contrat est nouveau seulement si son identifiant n'existe nulle part : la routing key pour un message, le chemin pour une route, le nom pour une table. Une classe neuve ne suffit pas. Contrat nouveau : pas de recherche, appliquer plutôt les contrôles « Nouvelle route » du §3.

Une ressource partagée hors contrat (service account GCP, bucket, topic) modifiée ou retirée : chercher qui d'autre l'utilise là où elle est déclarée (repo d'infra, Terraform, Crossplane) ; à défaut, en faire une case à cocher.

Si `rchiv` échoue ou ne connaît pas l'élément, le dire dans la sortie, appliquer la règle d'information manquante du §4 et ajouter dans « À faire avant le merge » la validation par les équipes consommatrices.

## 2. Classer les fichiers par zone

| Zone | Exemples de chemins |
|---|---|
| Contrat d'API exposé | `src/Controller`, DTO, groupes du Serializer, `#[Route]`, attributs API Platform, spec OpenAPI |
| Contrat asynchrone | Messages Messenger, handlers, `config/packages/messenger.{yaml,php}`, payloads d'events (Kafka, RabbitMQ) |
| Données | `migrations/`, entités Doctrine, mappings, repositories, requêtes DQL ou SQL |
| Contrat data | Tables ou schémas exportés vers l'entrepôt de données (Airbyte, BigQuery) |
| Sécurité | `config/packages/security.{yaml,php}`, voters, authenticators, firewalls, `#[IsGranted]`, gestion des JWT ou des secrets, identité du pod (`serviceAccount`, annotations Workload Identity, rôles IAM) |
| Appels inter-services | HttpClient, clients générés, timeouts, retries, circuit breakers |
| Configuration / infra | `.env*`, `config/` (YAML ou PHP), `services.{yaml,php}`, feature flags, Dockerfile, CI, Helm |
| Dépendances | `composer.json` / `composer.lock` (montées majeures, nouveaux paquets) ; dans le Dockerfile : image de base (`FROM`), version de PHP, extensions PECL, paquets système |
| Logique métier | `src/Domain`, services, calculs, machines à états |
| Tests / docs | `tests/`, `*.md` |

## 3. Appliquer les points de contrôle

Lire [`references/checks.md`](references/checks.md) et appliquer la section de chaque zone touchée, plus la section « Toujours ». Une route neuve relève à la fois de « Contrat d'API exposé » et de « Sécurité ».

## 4. Noter

### Règles de notation

Sur chaque axe, **3 = pire cas**, à condition que le diff ou l'historique du code en montre un mécanisme concret : un pire cas seulement théorique (« une montée de runtime peut tout casser ») ne se note pas. L'Impact mesure le scénario de panne, pas l'effet voulu : la disparition d'une table que la PR supprime exprès n'est pas une perte de données ; un lecteur qui la lit encore, si.

Impact, Rayon, Irréversibilité et Non-détection se notent sur **un seul risque** : celui dont la somme de ces quatre axes est la plus élevée. Ne pas combiner l'Impact d'un risque et la Non-détection d'un autre : le score décrirait un risque qui n'existe pas. Les autres risques sont listés et peuvent déclencher un plancher. La Complexité porte sur le **diff entier**.

Le score évalue le **déploiement de la PR**. Un risque qui n'apparaît qu'au moment où des consommateurs adoptent un contrat neuf se liste dans les risques, marqué « à l'adoption », sans compter dans le score (sauf PR mergée, voir §5).

### Grille

| Axe | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| **Impact** : qu'est-ce qui casse si c'est faux ? | rien de visible | dégradation mineure ou contournable (libellé, log, perf marginale) | fonctionnalité en erreur pour une partie des utilisateurs, flux bloqué mais récupérable | perte ou corruption de données, faille, panne d'un service ou de ses consommateurs |
| **Rayon d'impact** : qui est touché ? | rien en production (tests, outillage) | une fonctionnalité secondaire d'un service | le parcours principal du service (ce pour quoi il existe), tout le service, ou un consommateur externe | plusieurs services ou consommateurs (contrat partagé, librairie commune, middleware global, table partagée) |
| **Irréversibilité** : un rollback suffit-il ? | rollback du code suffit | rollback + action manuelle simple (vider un cache, relancer un job) | rollback + intervention sur les données ou les messages (rejeu, `down()` avec perte possible) | impossible sans perte (`DROP`, données réécrites, messages déjà consommés ailleurs, emails envoyés) |
| **Non-détection** : la panne serait-elle vue vite ? | chemin couvert par les tests, erreur bruyante immédiate | vue en quelques minutes par les alertes ou les logs d'erreur | vue seulement par un utilisateur ou un contrôle manuel | silencieuse (flux async, données fausses sans erreur) |
| **Complexité** du changement | localisé, une zone, quelques dizaines de lignes | plusieurs fichiers d'une même zone, ou fonctionnalité verticale purement additive (contrôleur, application, persistance neufs, non appelés par l'existant), ou suppression de code prouvé inatteignable (aucun appelant, flag à sa valeur effective dans tous les environnements) | plusieurs zones dont le comportement existant change, ou logique conditionnelle non triviale | concurrence, transactions, cache |

Pour la Complexité, la zone Tests / docs ne compte pas. Une contrainte d'ordre de déploiement, même entre repos, ne se note pas en Complexité : elle va dans « Déploiement », et son non-respect est un risque noté sur les quatre autres axes. Un changement qui peut aveugler la détection (agent APM, logs, métriques ou alertes inopérants) note au moins 2 en Non-détection, même si rien d'autre ne casse : les pannes suivantes deviennent invisibles.

### Information manquante

Consommateurs d'un contrat, volumétrie d'une table, configuration externe (valeur réelle d'un flag ou d'une variable dans chaque environnement) : chercher d'abord à lever l'inconnue. Une valeur qui existe mais qu'on ne connaît pas relève de cette règle ; un mécanisme de panne dont ni le diff ni l'historique ne montrent d'indice est un pire cas théorique et ne se note pas.
- Consommateurs : `rchiv` (voir §1).
- Configuration externe : les `values` Helm du repo, puis Vault ou l'outil de flags s'ils sont accessibles.
- Volumétrie : `information_schema.tables` si un accès en lecture à la base est disponible, sinon les métriques de la base dans Datadog si son MCP est connecté, sinon une estimation à partir d'indices (ordre de grandeur des ids, chiffres donnés dans la PR), justifiée dans la note.

Pas de +1 si la note reste la même quelle que soit la valeur inconnue. Si ni la base, ni Datadog, ni les indices ne répondent, ne pas supposer le meilleur cas : ajouter **+1 au maximum** sur l'axe associé à l'inconnue (volumétrie d'une table ou configuration externe → Impact ; consommateurs d'un contrat → Rayon ; couverture de tests du chemin modifié → Non-détection), et transformer l'inconnue en case à cocher dans « À faire avant le merge ».

### Indice ou preuve

Un fait qui change une note ou déclenche un plancher doit être prouvé : qu'un consommateur existe encore, qu'un code soit déployé, qu'une configuration ait telle valeur, qu'une période de compatibilité ait eu lieu.
- L'existence d'un appelant ou d'un lecteur se prouve dans le code de sa branche par défaut.
- Ce qui est déployé ou configuré se prouve en production : outil de déploiement (Concourse, FluxCD), base, logs, Vault.

Le registre `rchiv`, les dates `mergedAt`, la description de la PR, ou la branche par défaut quand la question porte sur le déploiement, ne sont que des indices. Un fait seulement indiqué se traite comme une information manquante. Si le plancher Critique dépend d'un fait qu'on ne peut ni prouver ni écarter, ne pas l'appliquer : appliquer le plancher Élevé, et faire de la preuve une case à cocher.

### Niveau

Score = somme (0 à 15) :
- **0–3 Faible** : merge normal.
- **4–7 Modéré** : relecture attentive, tests ciblés.
- **8–11 Élevé** : deuxième relecteur, plan de rollback, déploiement surveillé.
- **12–15 Critique** : ne pas merger sans actions préalables (découpage, feature flag, migration en plusieurs temps, validation des équipes consommatrices).

**Niveau retenu = le plus haut entre le niveau du score et les planchers ci-dessous.**

Les planchers s'énoncent par principe. Les cas cités sont des exemples, pas une liste fermée : un cas absent qui relève du même principe compte. Chaque plancher repose sur des faits prouvés (voir « Indice ou preuve »).

Plancher **Critique** :
- **un risque avec Impact 3 et Irréversibilité ≥ 2** ;
- **un consommateur d'un autre service ne pourra plus lire, sans versioning ni période de compatibilité** : champ supprimé ou renommé, ou type changé, dans son contrat ;
- **des données lues par un autre service disparaissent** : migration qui supprime une table ou des colonnes dont un lecteur est confirmé dans le code.

Plancher **Élevé** :
- **un consommateur existant risque de ne plus pouvoir lire** : champ supprimé ou renommé, ou type changé, dans une réponse d'API, un message asynchrone ou une table exportée vers l'entrepôt ; message émis dans une enveloppe que le parseur d'un abonné ne sait pas lire ; classe de message Messenger renommée ou déplacée (le serializer stocke le FQCN des messages en file) ;
- **un état déjà enregistré ailleurs diverge du code** : migration déjà mergée puis modifiée (la nouvelle version ne tournera pas là où l'ancienne est enregistrée dans la table des versions de migrations) ; routing, transport ou queue modifiés, ou handler supprimé, avec des messages en vol ;
- **le schéma existant perd quelque chose** : migration avec `DROP`, `RENAME`, changement de type ou `NOT NULL` sans valeur par défaut sur une table existante ;
- **qui a accès à quoi change** : règle `access_control`, firewall, hiérarchie de rôles, voter ou authenticator, en YAML ou PHP (un commentaire ou un reformatage ne compte pas) ; identité du pod (service account, Workload Identity, rôles IAM) ;
- **l'environnement d'exécution change** : nouvelle variable d'environnement obligatoire sans valeur par défaut ; montée majeure d'un paquet ; version mineure ou majeure de PHP (8.3 → 8.4 change le runtime).

### Exemples de calibrage

| Changement | Impact / Rayon / Irréversibilité / Non-détection / Complexité | Niveau |
|---|---|---|
| Ajout d'un test unitaire | 0 / 0 / 0 / 0 / 0 = 0 | Faible |
| Endpoint et tables neufs, pas encore appelés, accès contrôlé | 1 / 0 / 0 / 1 / 1 = 3 | Faible |
| Suppression sur plusieurs zones de code prouvé inatteignable | 0 / 0 / 0 / 0 / 1 = 1 | Faible |
| Montée de patch de l'image PHP, CI qui démarre le serveur réel, aucun incident passé sur ce Dockerfile | 1 / 2 / 0 / 0 / 0 = 3 | Faible |
| Même montée, avec un incident passé sur ce Dockerfile (extension ou agent APM cassés) | 3 / 2 / 0 / 1 / 0 = 6 | Modéré |
| Ajout d'un champ nullable dans une réponse d'API | 1 / 2 / 0 / 1 / 0 = 4 | Modéré |
| Ajout d'une colonne `NOT NULL` sans défaut sur une table existante | 2 / 1 / 1 / 1 / 1 = 6 | Élevé (plancher) |
| Renommage d'une classe de message Messenger, messages en file | 3 / 2 / 2 / 3 / 1 = 11 | Critique (plancher : Impact 3 et Irréversibilité ≥ 2) |

## 5. Format de sortie (en français)

```
## Niveau de risque : <Faible|Modéré|Élevé|Critique> (<score>/15)
<1 à 2 phrases : pourquoi ce niveau, et sur quel risque portent les axes. Si un plancher s'applique, le nommer.>
<Si la source inclut des modifications non commitées, le dire.>

| Axe | Note | Justification |
|---|---|---|
| Impact | x/3 | ... |
| Rayon d'impact | x/3 | ... |
| Irréversibilité | x/3 | ... |
| Non-détection | x/3 | ... |
| Complexité | x/3 | ... |

### Risques identifiés (du plus grave au moins grave)
1. **[Zone] Titre court**, `fichier.php:ligne`
   Scénario concret de panne -> conséquence.
   Mitigation proposée.

### À faire avant le merge
- [ ] ...

### Déploiement
Ordre recommandé (migration / code / consommateurs), feature flag éventuel, métriques et logs à surveiller, procédure de rollback.

### Remarques mineures
(optionnel, 3 maximum)
```

### PR déjà mergée

Le mode dépend du champ `state` (`MERGED` : revue a posteriori ou post-mortem), pas de ce qu'affirme l'utilisateur : signaler l'écart s'il y en a un.
- Le temps écoulé depuis le déploiement est une information. Sous le niveau de risque, rendre un verdict **matérialisé / non matérialisé / inconnu**, appuyé sur les traces : incidents, erreurs dans les logs ou l'APM depuis le déploiement, commits de revert ou de correctif sur les fichiers touchés.
- « À faire avant le merge » devient « À vérifier en production » (logs, métriques, données à contrôler). Toute consigne du skill qui envoie un point dans « À faire avant le merge » (inconnue, validation des consommateurs) l'envoie alors dans « À vérifier en production ».
- « Déploiement » devient « En cas de problème » : des PR ont-elles été mergées depuis ? Si oui, revert du commit plutôt que rollback de l'image. Quelles données ont déjà été touchées ?
- Les actions hors repo listées dans la description (Vault, IAM, nettoyage de configuration) deviennent des cases dans « À vérifier en production » : ont-elles été faites, et dans le bon ordre par rapport au déploiement ?
- Merge n'est pas déploiement : l'ordre de déploiement entre repos se prouve par l'outil de déploiement, pas par les `mergedAt` des PR liées (§4, « Indice ou preuve »).
- Noter la PR telle qu'elle tourne aujourd'hui : les risques « à l'adoption » comptent dans le score si le code ou le contrat est atteignable en production, qu'un consommateur externe l'appelle ou qu'un commit ultérieur du même repo l'ait câblé (voir §1, appelants). Sinon, cette vérification devient une case dans « À vérifier en production ».

### Règles

- Chaque risque cite un fichier et une ligne, plus un scénario concret. Un risque de processus ou inter-repos (ordre de déploiement, état de la PR) cite à la place une PR ou un commit. Pas de risque générique (« pourrait poser problème »). La ligne est celle de la version après changement ; pour une ligne supprimée, citer la ligne de la version de base et le préciser.
- Une note augmentée faute d'information le dit dans sa justification.
- Les actions hors repo listées dans la description de la PR (Vault, IAM, nettoyage de configuration) entrent dans « Déploiement », à leur place par rapport au déploiement du code.
- Si la PR corrige une faille, un rollback la rouvre : dans « Déploiement » ou « En cas de problème », mettre en balance le rollback et l'exposition, et privilégier un contournement.
- Ne pas gonfler le score : un diff limité à des tests, de la doc ou un refactoring interne couvert par des tests reste Faible.
