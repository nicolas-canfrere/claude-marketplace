---
name: asyncapi-doc
description: Rétro-documente les flux RabbitMQ d'un projet PHP legacy (Symfony Messenger, autre framework ou wrapper AMQP custom, vieux PHP) en un fichier AsyncAPI 3.1 validé, créé ou mis à jour. Use when asked to document RabbitMQ / AMQP flows, generate or update an asyncapi.yaml, map which exchanges and queues a PHP service publishes to or consumes, or reverse-engineer an event contract — « documenter les flux RabbitMQ », « générer l'asyncapi », « quels messages ce service publie / consomme », « contrat d'événements ».
---

# AsyncAPI depuis du code PHP legacy + RabbitMQ

Objectif : produire ou mettre à jour `asyncapi.yaml` à la racine du projet (AsyncAPI 3.1.0, à côté d'un éventuel `openapi.yaml`) décrivant ce que le service publie et consomme sur RabbitMQ, uniquement à partir de ce que le code prouve. Aucune hypothèse sur le framework, la version de PHP ou la librairie AMQP.

Règles d'or :
- **Ne jamais inventer.** Tout élément non prouvé par le code porte `x-unverified: "<raison précise>"` (une chaîne, jamais `true`) et figure dans le rapport final. Ce champ se pose sur le channel, l'opération, le message ou le schéma concerné, **jamais à l'intérieur d'un objet `bindings`**.
- **Jamais de secret dans le document.** Une URL `amqp://user:pass@host` ne se recopie pas : ne garder que host, port et vhost. Une valeur lue depuis l'environnement (`getenv`, `%env()%`, `$_ENV`) s'écrit comme variable de serveur (`{host}`) avec la variable d'environnement en `description`.

## 1. Trouver le point d'accès bas niveau à AMQP

Chercher dans le code du projet, et dans `vendor/` **uniquement** pour les librairies AMQP ci-dessous et les packages internes (namespaces maison, packages déclarés en `path` ou dépôt privé dans `composer.json`) :

- php-amqplib : `basic_publish`, `basic_consume`, `exchange_declare`, `queue_declare`, `queue_bind`, `new AMQPMessage`
- ext-amqp : `new AMQPExchange`, `->publish(`, `new AMQPQueue`, `->consume(`, `->bind(`
- Libs connues : `OldSound\RabbitMqBundle`, `Enqueue\`, `Swarrot\`, `Bunny\`, `Thumper`
- Symfony Messenger (`symfony/amqp-messenger`, DSN `amqp://`) : aucun appel AMQP dans `src/`, tout est dans la config (`messenger.yaml` / `messenger.php`) et dans `AmqpStamp`. Voir « Cas Symfony Messenger » ci-dessous.
- Config : fichiers yml/yaml/ini/php/xml/json contenant `exchange`, `queue`, `routing_key`, `binding`, `vhost`, `amqp://`
- Lancement des consommateurs : configs supervisord, crontab, Procfile, entrypoints Docker, manifests de déploiement. La queue consommée n'est souvent visible que là, en argument de commande.

Puis **remonter les wrappers** : pour chaque classe custom qui appelle ces fonctions, identifier sa méthode publique (`publish($event, $routingKey)`, `send()`, `dispatch()`...) et chercher tous ses appelants. Répéter jusqu'au code métier. Les vrais producteurs et consommateurs sont là.

Noter pour chaque wrapper comment il construit : nom d'exchange, routing key, headers applicatifs (table `headers` du message, par exemple un header `type` qui sert à router côté consommateur), propriétés AMQP (`content_type`, `content_encoding`, `type`, `reply_to`, `correlation_id`, `delivery_mode`), sérialisation (json_encode, serialize, normalizer maison). Un header nommé `type` et la propriété AMQP `type` sont deux choses distinctes : relever où le code écrit réellement la valeur.

### Cas Symfony Messenger

Lire, pour chaque transport AMQP :
- `exchange` (`name`, `type`) et `queues` → `binding_keys` : la topologie. Sans option `exchange`, Messenger utilise l'exchange `messages` (fanout) et la queue du même nom (défauts de `Symfony\Component\Messenger\Bridge\Amqp\Transport\Connection`).
- `routing` : quelle classe de message part sur quel transport.
- La routing key : `new AmqpStamp('<clé>')` au dispatch, souvent dans une gateway avec une table classe → clé. Sans `AmqpStamp`, Messenger publie sans routing key.
- `serializer` du transport :
  - service maison implémentant `SerializerInterface` → lire `encode()` (payload, headers) et `decode()` (ce que le consommateur exige) ;
  - `messenger.transport.symfony_serializer` → JSON des propriétés publiques de la classe, header applicatif `type` = FQCN de la classe, `content_type` AMQP `application/json` ; contrat couplé aux classes PHP, à signaler ;
  - aucun serializer et pas de `default_serializer` dans `framework.messenger` → `PhpSerializer`, donc `serialize()` PHP natif : contrat non portable, ne pas écrire `contentType: application/json`.
- `auto_setup: false` → la topologie réelle est déclarée ailleurs ; ne renseigner que ce que la config du transport donne.
- `retryStrategy`, option `delay` (exchange et queues de délai) et `failureTransport` → topologie implicite (voir étape 2).
- Consommateurs : `messenger:consume <transport>` dans les configs de lancement, puis les handlers `#[AsMessageHandler]` / `__invoke(<Message>)`.

## 2. Inventaire (avant d'écrire le YAML)

Construire une table de travail, une ligne par flux :

| sens (send/receive) | exchange (+type) | routing key / queue | message | source (`Classe::méthode`) | certitude |

- Routing key en dur → certaine. Construite dynamiquement (`'user.' . $action`) → lister les valeurs possibles trouvées ; si la liste n'est pas fermée, le noter `x-unverified`.
- Exchange/queue déclarés ailleurs (autre service, ops, définitions RabbitMQ) → le noter, ne pas deviner le type d'exchange.
- Consommateurs : relever la queue, ses bindings (exchange + pattern), et ce que le handler lit dans le message.
- Topologie implicite, à inventorier comme des flux à part entière :
  - arguments de `queue_declare` / `exchange_declare` : `x-dead-letter-exchange`, `x-dead-letter-routing-key`, `x-message-ttl` → queues de retry et dead-letter ;
  - `reply_to` + `correlation_id` → RPC : une opération `send` et une opération `receive` liées par `reply` ;
  - exchanges `x-delayed-message` ou header `x-delay` → messages différés, à signaler dans la description ;
  - retries par exchange de délai (Messenger `delay`) → interne au service : décrire l'exchange, les queues et la politique de retry dans la `description` du channel consommateur, pas de channel dédié ;
  - file d'échec hors RabbitMQ (Messenger `failureTransport` Doctrine, table SQL…) → pas de channel AMQP : la mentionner dans la `description` du channel consommateur concerné.

## 3. Reconstruire les payloads

Sources, par ordre de fiabilité :
1. Classe de message avec propriétés typées ou PHPDoc `@var`.
2. Tableau littéral passé à `json_encode` / méthode `toArray()` / `jsonSerialize()`.
3. Côté consommateur : clés lues (`$data['user_id']`, `isset($payload['x'])`) → donne les champs requis/optionnels.
4. Fixtures, tests, exemples de messages dans le repo.

Écrire un JSON Schema : types déduits des casts, validations et usages ; `required` seulement si le code le garantit. Un type non prouvé → omettre `type`, ajouter `description` + `x-unverified`. Si payload sérialisé en PHP natif (`serialize`), le signaler explicitement : contrat non portable.

Headers applicatifs relevés à l'étape 1 → `headers` du message (JSON Schema). Propriétés AMQP → binding de message, uniquement si le code pose la propriété elle-même :
```yaml
bindings:
  amqp:
    contentEncoding: gzip      # propriété AMQP content_encoding
    messageType: user.created  # propriété AMQP `type`, pas un header nommé `type`
```

## 4. Écrire / mettre à jour le document

Si `asyncapi.yaml` existe : **mise à jour incrémentale**.
- Conserver `info`, descriptions, exemples et tout contenu ajouté à la main.
- Ajouter ce qui manque.
- En cas de désaccord entre le document et le code : **le code gagne pour la structure** (noms, adresses, types, champs, `required`) ; le texte libre (descriptions, exemples) est conservé tel quel. Chaque divergence corrigée est listée dans le rapport.
- **Renommages, avant de conclure à un ajout + une disparition.** Pour chaque élément du document absent du code, chercher parmi les éléments nouveaux un candidat qui partage au moins deux de ces traits : même classe PHP dans `x-source`, même exchange, même schéma de payload (mêmes champs). Confirmer avec git quand c'est possible (`git log -S'<ancienne valeur>' --oneline` montre le commit qui l'a remplacée).
  - Renommage confirmé → modifier l'élément existant sur place (clé, `address`, nom de message) pour garder ses descriptions et exemples, mettre à jour les `$ref` qui le visent, et le lister comme renommage dans le rapport.
  - Doute (un seul trait commun, ou plusieurs candidats) → ne pas fusionner : traiter comme ajout + disparition, et poser la question dans le rapport (« `user.created` remplacé par `user.registered` ? »).
- Ce qui n'existe plus dans le code (et n'est pas un renommage) reçoit `x-deprecated-candidate: "<YYYY-MM-DD>"`, la date du passage qui l'a constaté, au lieu d'être supprimé. Ne jamais changer cette date lors des passages suivants.
- **Réévaluer les marqueurs existants à chaque passage :**
  - `x-unverified` : si le code prouve désormais l'élément, retirer le marqueur et renseigner la valeur prouvée ; si la raison a changé, la réécrire ; sinon le laisser.
  - `x-deprecated-candidate` : si l'élément est réapparu dans le code, retirer le marqueur ; sinon le garder. Supprimer l'élément seulement quand l'utilisateur le confirme dans la session (en réponse au rapport), jamais de sa propre initiative.

Conventions :
- `channels` côté publication : un channel par routing key, `address` = routing key. Routing key dynamique → paramètre de channel, pas de joker :
  ```yaml
  userEvents:
    address: user.{action}
    parameters:
      action:
        enum: [created, deleted]   # valeurs trouvées dans le code
    bindings:
      amqp:
        is: routingKey
        exchange: { name: user.events, type: topic, durable: true, vhost: / }
  ```
  `*` et `#` sont des patterns de binding RabbitMQ, jamais une `address`.
- `channels` côté consommation : un channel par queue, `address` = nom de la queue, binding `is: queue` avec `queue: { name, durable, exclusive, autoDelete }`. Les bindings de la queue vont dans `x-binding-keys` sur le channel (liste des patterns), l'exchange source dans la `description` :
  ```yaml
  userEventsQueue:
    address: my-service.user.events
    description: Liée à l'exchange user.events (topic).
    x-binding-keys: [user.created, user.deleted]
    bindings:
      amqp:
        is: queue
        queue: { name: my-service.user.events, vhost: / }
  ```
- Un même message publié et consommé par ce service est défini **une seule fois** dans `components.messages` et référencé depuis les deux channels. Un message consommé mais publié par un autre service est décrit uniquement à partir de ce que le consommateur lit ; le préciser dans sa `description`.
- Champs du binding : ne renseigner `exchange.type`, `durable`, etc. que si le code les montre ; sinon les omettre et poser `x-unverified` sur le channel.
- `operations` : `action: send` (le service publie) ou `receive` (il consomme), `channel` et `messages` en `$ref`.
- `components.messages` / `components.schemas` pour tout ce qui est réutilisé.
- Chaque message, opération et channel porte `x-source` : `chemin/fichier.php` + `Classe::méthode` (liste si plusieurs). Pas de numéro de ligne : il change à chaque modification du fichier et rend les mises à jour incrémentales bruyantes.
- `contentType` réel (`application/json` si json_encode).

Squelette minimal :
```yaml
asyncapi: 3.1.0
info:
  title: <nom du service>
  version: <version ou 0.1.0>
servers:
  rabbitmq:
    host: <host[:port] depuis config, sans identifiants ; sinon {host} + variable>
    protocol: amqp
channels: {}
operations: {}
components:
  messages: {}
  schemas: {}
```

## 5. Valider

Dans l'ordre, selon ce qui est disponible :
1. `asyncapi validate asyncapi.yaml` (ou `npx @asyncapi/cli validate ...`).
2. Sinon, en dernier recours : parser le YAML et vérifier que chaque `$ref` pointe vers une cible existante, que chaque opération a `action`, `channel`, `messages` et que chaque paramètre d'`address` est déclaré dans `parameters`. Cette vérification ne remplace pas le validateur : le dire dans le rapport.

Corriger jusqu'à validation. Dire explicitement quelle méthode a été utilisée.

## 6. Rapport final

Court, à la fin :
- Nombre de flux send/receive documentés, nouveaux vs modifiés.
- Divergences document/code corrigées.
- Renommages appliqués, et renommages probables non fusionnés avec leur question.
- Marqueurs retirés : `x-unverified` levés (avec la preuve trouvée), `x-deprecated-candidate` d'éléments revenus dans le code.
- Liste des éléments `x-unverified` avec la question précise à poser à l'équipe (ex. « type de l'exchange `billing` : déclaré hors de ce repo »).
- Candidats à la dépréciation, avec leur date de constat, et la question : « supprimer du document ? ».
- Points de risque repérés (payload `serialize()`, routing key entièrement dynamique, message sans consommateur visible, dead-letter sans consommateur, valeur de config non résolue).
