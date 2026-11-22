# Points de contrôle par zone

Appliquer la section de chaque zone touchée par le diff (zones du §2 de `SKILL.md`), et toujours la dernière section.

## Contrat d'API exposé

Contrat modifié :
- Ajout de champ seulement (OK) ou suppression/renommage (cassant) ?
- Groupes du Serializer modifiés ? Valeurs `null` nouvelles ?
- Les consommateurs connus sont-ils prêts ? Un versioning d'API est-il nécessaire ?

Nouvelle route (appliquer aussi la section Sécurité) :
- Collision avec une route existante (même chemin, `requirements`, ordre ou `priority`) ?
- Quel firewall la prend en charge (le premier qui matche, selon l'ordre, le `pattern` et les `methods`), et quel authenticator ou token handler accepte-t-il ?
- Règle `access_control` héritée d'un préfixe existant : le rôle qu'elle impose est-il celui voulu pour cette route ?
- Route en lecture appelée sur un chemin chaud (par exemple à chaque page du site public) : coût de la requête, index utilisé, borne sur le nombre d'éléments demandés, cache côté appelant ou côté service ?
- Route en écriture : que produit une double soumission ou un retry de l'appelant (doublon, 409, réponse identique) ?

## Contrat asynchrone

Tous transports (Messenger, Burrow, Swarrot, bibliothèque maison) :
- Nouvel émetteur sur une routing key existante : comparer l'enveloppe (params, payload), l'exchange et la routing key avec ceux de l'émetteur existant, et lire le parseur de chaque abonné trouvé par `trace-event`.
- Message modifié : chaque abonné sait-il lire le nouveau format, et l'ancien pendant le déploiement ?

Messenger :
- Un message déjà en file peut-il encore être désérialisé par le nouveau code, et l'ancien code lire les nouveaux messages pendant un déploiement progressif ?
- Un versioning du message est-il nécessaire ?
- Les handlers sont-ils idempotents ?
- Le retry ou le failure transport est-il configuré ?
- Une exception qui change de classe ou de parent change-t-elle le sort du message (rejoué, envoyé au failure transport, acquitté) ? Par exemple, une exception qui devient ou étend `UnrecoverableMessageHandlingException` n'est plus rejouée.

## Données (Doctrine)

- L'ancien code tourne-t-il sur le nouveau schéma ? C'est ce qui fixe l'Irréversibilité, plus que le `down()` : si oui, un rollback du code suffit.
- `down()` absent ou vide : un risque seulement si le schéma créé est incompatible avec l'ancien code en cas de rollback (pas pour un index ou une colonne nullable ajoutés).
- `down()` qui rétrécit un type (`BIGINT` → `INTEGER`, `NUMERIC` → `INTEGER`, `VARCHAR` raccourci) : il échoue dès que de nouvelles données dépassent l'ancien domaine, et le retour au schéma précédent devient impossible sans perte.
- Type numérique changé : la précision et l'échelle de la cible couvrent-elles les valeurs de la source et de l'amont (par exemple `NUMERIC(20,10)` face à des valeurs à 14 décimales) ?
- Propriété typée non nullable hydratée depuis une colonne nullable (fréquent en PHP 7.4+ sur une base ancienne) : une ligne à `NULL` fait échouer l'hydratation. Vérifier la nullabilité réelle de la colonne et l'existence de lignes à `NULL`.
- Quand la migration tourne-t-elle (hook Helm avant la release, job, commande au démarrage du conteneur : voir le chart Helm et l'entrypoint du Dockerfile), et l'ancien code sert-il encore du trafic pendant ce temps ? C'est ce qui décide si un verrou touche le trafic.
- Verrou long sur une grosse table ? Cas le plus fréquent : la création d'index. En PostgreSQL, elle doit passer par `CREATE INDEX CONCURRENTLY`, qui échoue dans une transaction et impose `isTransactional(): false` dans la migration ; en MySQL, vérifier que l'`ALTER` reste online (`ALGORITHM=INPLACE, LOCK=NONE`).
- `ALTER TABLE` sur une table lue en continu : un `SET lock_timeout` en tête de migration évite que les lectures s'empilent derrière le verrou en attente. La config des migrations (`transactional`, `all_or_nothing`) tient-elle les verrous jusqu'au commit de tout le lot ?
- `DROP ... IF EXISTS` sur un objet (contrainte, index) qui n'a pas été créé dans ce repo : son nom est-il vérifié contre le schéma réel ? Un nom faux fait du `IF EXISTS` un no-op silencieux, et l'étape suivante échoue ou laisse l'objet en place.
- PostgreSQL : `DROP ... RESTRICT` ne voit pas les fonctions ni les triggers PL/pgSQL qui citent la table dans leur corps. Chercher dans `pg_proc.prosrc`.
- Argument d'ordre entre migrations : le vérifier contre le comparateur configuré. Le comparateur par défaut trie par nom de classe complet, pas par horodatage seul.
- Ordre de déploiement code/migration compatible avec un rolling deploy ?
- Nouveaux problèmes N+1, `flush()` dans une boucle, transactions trop larges ?

## Contrat data

- L'utilisateur de synchro a-t-il les droits de lecture sur une table neuve ?
- Quelles données personnelles part-elle exporter ?
- Une table destinée à disparaître casse la synchro le jour de son `DROP` : le prévoir avec l'équipe data.

## Sécurité

- Contrôle d'accès sur toute nouvelle route.
- Données personnelles que la réponse expose au rôle qui y a accès (champs, groupes du Serializer).
- Validation des entrées (Validator, DTO).
- Absence de données sensibles dans les logs ou les réponses.
- Requêtes paramétrées.
- Secret en clair ajouté dans un fichier versionné (`values*.yaml`, `.env*`, fixtures) : vrai secret, ou valeur locale sans portée ?
- Identité du pod modifiée ou retirée (`serviceAccount`, annotations Workload Identity, rôles IAM) : lister tous les appels du service au cloud (stockage, files, secrets, BigQuery…) et vérifier que la nouvelle identité les autorise. Qui d'autre utilise ce service account (voir §1, ressource partagée) ?

## Appels inter-services (HttpClient)

- Timeout défini ? Gestion des 4xx/5xx et des exceptions de transport ? Retry sur des appels non idempotents ?
- Appel à une route neuve ou modifiée d'un autre service : est-elle déployée en production, pas seulement présente sur sa branche par défaut ? Sinon, imposer l'ordre de déploiement (le fournisseur d'abord) ou un feature flag, et le reporter dans « Déploiement ». La présence sur la branche par défaut n'est qu'un indice (`SKILL.md` §4, « Indice ou preuve »).
- Payload envoyé modifié (champ ajouté, renommé ou retypé) : le fournisseur rejette-t-il les clés inconnues ou mal typées (contexte Serializer `allow_extra_attributes: false`, `additionalProperties: false` dans sa spec) ? Le fournisseur étant connu, lire directement son code de désérialisation : `rchiv` sert à trouver des consommateurs inconnus, pas à ça.

## Configuration / infra

- Nouvelle variable d'environnement documentée et présente dans tous les environnements ? Valeur par défaut sûre ?
- Variable d'environnement retirée : l'ancien code la lit encore. La retirer de Vault ou des `values` seulement après le déploiement du nouveau code ; sinon, un revert peut planter au démarrage si la variable y est obligatoire.
- Feature flag ou switch retiré, ou dont la valeur par défaut change : quelle était sa valeur réelle dans chaque environnement (`values` Helm, Vault, outil de flags) ? Le comportement conservé doit être celui de la valeur effective en production.

## Dépendances

Paquets Composer :
- Paquet retiré : ses dépendances transitives disparaissent aussi du lock. Pour chaque paquet qui disparaît, chercher ses namespaces dans `src/` et `config/` : le code peut les utiliser sans les déclarer.

Runtime / image :
- La CI exécute-t-elle le mode réel de production (serveur, mode worker), ou seulement la CLI ?
- L'agent APM supporte-t-il la nouvelle version de PHP ?
- Les extensions sont-elles toutes présentes et recompilées (comparer `php -m` avant et après) ?
- Le build fait-il des téléchargements non épinglés (`latest`, paquets système sans version) qui changent à chaque rebuild ?

## Toujours

- Tests : le chemin modifié est-il couvert ? Les cas d'erreur aussi ?
- Cache : invalidation correcte, clés qui changent de format.
- Si le diff rompt un contrat (API, message, schéma d'une table lue ailleurs) : le but était-il atteignable sans rupture (par exemple `BIGINT` au lieu de `NUMERIC`) ? Si oui, c'est la première mitigation à proposer, même si c'est un choix de conception.
