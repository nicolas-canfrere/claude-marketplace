---
name: architecture-improvements
description: "Use when the user asks for an architecture review or audit of a codebase or of one of its modules: shallow modules, deep modules (Ousterhout), information leakage, a rule duplicated across handlers, pass-through layers, « des pistes d'amélioration d'architecture », « où est-ce que ça fuit », /architecture-improvements. Not for reviewing a diff or a pull request."
argument-hint: [scope]
disable-model-invocation: true
---

# Revue d'architecture par la profondeur des modules

Trouve où un codebase gagnerait à approfondir ses modules, présente les pistes avec leurs preuves, puis creuse avec
l'utilisateur celle qu'il choisit. Le skill ne modifie pas le code de l'application.

## Principe

La grille est celle de *A Philosophy of Software Design* (Ousterhout) :

- **Profondeur** = fonctionnalité cachée ÷ coût de l'interface. Un module profond offre beaucoup derrière peu de
  choses à savoir.
- **Information leakage** : une même décision (règle, format, ordre d'appel) vit dans plusieurs modules. Un
  changement de cette décision les touche tous.
- **Pull complexity downwards** : le module absorbe la complexité plutôt que de la renvoyer à ses appelants.
- **Deletion test** : si l'on supprime le module suspect et qu'on inline son contenu chez ses appelants, la
  complexité se *concentre*-t-elle ou se *déplace*-t-elle seulement ? Elle se déplace : le module était superficiel.
  Elle se disperse chez plusieurs appelants : il était profond.

Une fuite ne se voit pas dans un fichier seul. Elle se voit en lisant côte à côte les modules **frères** (les
handlers d'un même contexte, les adapters d'un même port, les contrôleurs d'une même ressource).

## 1. Lire le cadre du repo

Avant d'explorer, lis ce qui fixe les règles du repo : `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`, la
doc d'architecture, et le dossier des ADR (`doc/adr/`, `docs/adr/`, `adr/`, `docs/decisions/`…). Retiens :

- **Le vocabulaire** du repo (couches, contextes, port, adapter…). Le rapport l'emploie tel quel, sans introduire
  un lexique concurrent.
- **Les contraintes non négociables** : vérificateur d'architecture (Deptrac, ArchUnit, dependency-cruiser…),
  règles sur les tests existants, gates de qualité, conventions imposées (bus, CQRS, nommage).
- **Les décisions actées** dans les ADR.

Si le repo n'a rien de tout ça, dis-le en une ligne et utilise le vocabulaire d'Ousterhout.

## 2. Cibler

- L'utilisateur a nommé un périmètre : prends-le.
- Sinon, cherche les hot spots, là où un approfondissement rapportera sur les prochains changements :

  ```bash
  git log --since="3 months ago" --name-only --pretty=format: | grep -v '^$' | awk -F/ '{print $1"/"$2"/"$3}' | sort | uniq -c | sort -rn | head -15
  ```

  Ajuste la profondeur du `awk` à la structure du repo. Garde **un** contexte ou module, le plus modifié.

Annonce le périmètre retenu en une ligne avant d'explorer.

## 3. Explorer

Lis **tous** les fichiers du périmètre, pas un échantillon. Au-delà d'une trentaine de fichiers, délègue la lecture à
un sous-agent `general-purpose` (contexte vierge), avec dans son brief : le périmètre, le vocabulaire du repo, la
liste de signaux ci-dessous, la consigne de rendre chaque signal avec ses `fichier:ligne`, et l'interdiction de
proposer des interfaces.

Signaux à chercher :

| Signal | Où regarder |
|---|---|
| Même règle réimplémentée, parfois sous des formes différentes | Les modules frères, côte à côte |
| Même structure (vue, DTO, message) construite à plusieurs endroits | `new X(` dans tout le périmètre |
| Pass-through : une méthode ou une classe qui ne fait que relayer | Les classes de moins de ~20 lignes |
| Interface plus coûteuse que ce qu'elle cache : nombreux paramètres, booléens positionnels, nullables en grappe | Constructeurs, factories, signatures publiques |
| Plusieurs ports d'une méthode vers la même cible | Les interfaces d'un même contexte |
| Appelant qui doit connaître l'ordre d'appel ou l'état interne | Les séquences répétées `find` puis `check` puis `save` |
| Module profond : interface courte, beaucoup de complexité absorbée | Ports d'infrastructure, services de domaine |

Relève aussi les modules profonds : ils servent de modèle à imiter dans les pistes.

## 4. Filtrer

Chaque candidat passe ces tests, dans l'ordre :

1. **Preuve** : relis toi-même le code cité. Un constat sans `fichier:ligne` vérifié est écarté, y compris s'il vient
   d'un sous-agent.
2. **Deletion test** : la piste concentre-t-elle la complexité, ou la déplace-t-elle ?
3. **Contraintes du repo** : une piste qui viole une règle non négociable est écartée.
4. **ADR** : une piste qui contredit une ADR n'est gardée que si la friction observée justifie de la rouvrir. Elle
   porte alors la mention de l'ADR concernée.
5. **Convention assumée** : un module superficiel *imposé* par une convention du repo (handler de bus qui relaie,
   adapter anti-corruption qui traduit) n'est pas un défaut. Range-le dans « coûts assumés », sans recommandation.

Donne à chaque piste retenue un niveau : **Fort** (fuite prouvée sur 3 sites ou plus, ou risque d'incohérence
visible par l'utilisateur), **À explorer** (2 sites, ou gain réel mais local), **Spéculatif** (dépend d'une
évolution qui n'a pas encore eu lieu).

## 5. Restituer

Deux sorties, le même contenu :

**Dans la conversation**, dans cet ordre, avec des codes `F1`, `F2`… stables pour la suite :

1. **Ce qui est profond** : 2 à 4 constats, une ligne chacun.
2. **Les pistes** : pour chacune, le niveau, les sites (`fichier:ligne`), le problème, ce qu'il coûte au prochain
   changement, et la **direction** de la solution (« une seule fabrique de la vue », « la règle descend dans
   l'agrégat ») sans signature ni interface.
3. **Coûts assumés** : ce qui est superficiel par convention, une ligne chacun.
4. **Recommandation** : quelles pistes, dans quel ordre, en une ou deux phrases. C'est la dernière chose écrite.

**En page HTML** autonome, selon [HTML-REPORT.md](HTML-REPORT.md). Écris-la dans le répertoire scratchpad de la
session s'il existe, sinon dans `$TMPDIR`, jamais dans le repo, et donne son chemin absolu.

Termine en demandant quelle piste approfondir.

## 6. Approfondir une piste

Quand l'utilisateur choisit une piste :

- Si le skill `superpowers:brainstorming` est disponible, invoque-le avec la piste comme point de départ. Sinon, pose
  les questions une à une : contraintes, forme du module approfondi, ce qu'il cache, ce que ses appelants n'ont plus
  à savoir, tests impactés.
- Liste les **tests existants** que la piste modifierait. Si le repo protège ses tests existants, cette liste est à
  faire valider avant tout code.
- Le résultat suit le circuit du repo (spec, plan, ticket) s'il en a un.
- Si l'utilisateur **rejette** une piste pour une raison durable (contrainte, décision d'équipe), propose de l'acter
  en ADR dans le dossier du repo, au format et à la numérotation des ADR existantes, pour qu'elle ne revienne pas à
  la revue suivante. Une raison passagère (« pas maintenant ») ne fait pas une ADR.

## Erreurs courantes

| Erreur | Correction |
|---|---|
| Juger chaque fichier isolément | Lire les modules frères côte à côte : c'est là que les fuites apparaissent |
| Compter les petits fichiers comme superficiels | Appliquer le deletion test : un petit module peut être profond |
| Recommander de supprimer une couche imposée par l'architecture | La ranger dans « coûts assumés » |
| Proposer une interface dès le rapport | Donner la direction, concevoir à l'étape 6 |
| Reprendre un constat de sous-agent sans le relire | Vérifier chaque `fichier:ligne` soi-même |
| Introduire *seam*, *component*, *service* dans un repo qui dit *port*, *adapter* | Employer le vocabulaire relevé à l'étape 1 |
