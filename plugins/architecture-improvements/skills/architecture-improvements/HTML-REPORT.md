# Page HTML du rapport

Un seul fichier `architecture-review-<repo>-<YYYYMMDD-HHMM>.html`, lisible hors ligne : CSS inline, aucune
dépendance sauf Mermaid, chargé seulement si la page contient un diagramme Mermaid.

## Contenu, dans l'ordre

1. **En-tête** : nom du repo, date, périmètre analysé, commit (`git rev-parse --short HEAD`), légende des
   diagrammes (boîte pleine = module, boîte épaisse = module profond, flèche rouge = fuite).
2. **Ce qui est profond** : liste courte, codes `F…` de la conversation.
3. **Une carte par piste**, mêmes codes que dans la conversation :
   - titre et badge de niveau (Fort / À explorer / Spéculatif) ;
   - sites concernés, en `fichier:ligne`, police à chasse fixe ;
   - **Problème** et **Direction**, une phrase chacun ;
   - **Gains**, 2 à 4 puces courtes (« la règle d'accès vit à un seul endroit ») ;
   - **Avant / Après** côte à côte : schéma des modules et des flèches de connaissance ;
   - si une ADR est concernée, un encart ambre qui la nomme.
4. **Coûts assumés** : liste courte.
5. **Recommandation** : un paragraphe, en dernier.

## Diagrammes

- Relations entre plusieurs modules (qui connaît quelle règle) : Mermaid `flowchart LR`, la règle dupliquée en nœud
  rouge relié à chaque site dans « Avant », un seul lien dans « Après ».
- Une seule interface trop large : pas de Mermaid. Deux boîtes HTML, la signature avant (longue) et la direction
  après (courte), suffisent.
- Hauteur de diagramme autour de 300 px. Un diagramme qui n'apprend rien de plus que le texte est retiré.

## Style

Thème clair et sombre par variables CSS, une couleur d'accent, rouge réservé aux fuites, ambre aux ADR. Largeur
maximale ~1000 px, cartes empilées, utilisable à largeur de téléphone.

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revue d'architecture</title>
<style>
  :root { --bg:#fafaf9; --fg:#1c1917; --muted:#57534e; --card:#fff; --line:#e7e5e4;
          --accent:#4f46e5; --leak:#dc2626; --adr:#d97706; --strong:#059669; --explore:#d97706; --spec:#64748b; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0c0a09; --fg:#f5f5f4; --muted:#a8a29e; --card:#1c1917; --line:#292524; }
  }
  body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif; }
  main { max-width:1000px; margin:0 auto; padding:24px 16px; }
  article { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px; margin:16px 0; }
  .badge { font-size:12px; font-weight:600; padding:2px 8px; border-radius:999px; color:#fff; }
  .strong { background:var(--strong); } .explore { background:var(--explore); } .spec { background:var(--spec); }
  .sites { font-family:ui-monospace, monospace; font-size:13px; color:var(--muted); }
  .before-after { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  @media (max-width:640px) { .before-after { grid-template-columns:1fr; } }
  .adr { border-left:4px solid var(--adr); padding:8px 12px; }
</style>
</head>
<body><main>
  <!-- en-tête, puis sections dans l'ordre ci-dessus -->
</main>
<!-- seulement si la page contient un bloc class="mermaid" -->
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: true, theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default' });
</script>
</body>
</html>
```
