# Marchio zeroCAM

I file stanno sotto `static/` perché l'interfaccia web li serve direttamente:
spostarli altrove romperebbe gli `url_for('static', filename='brand/...')` di
`templates/index.html` e `templates/login.html`.

Di ogni variante c'è l'SVG e il PNG. Nelle pagine si usa l'SVG, che resta
nitido a qualsiasi dimensione e su qualsiasi densità di schermo; il PNG serve
dove l'SVG non è accettato, come l'icona per la schermata home di iOS.

| File | Formato | Uso |
|---|---|---|
| `zc_logo_big` | 315×94, marchio esteso con payoff | Intestazione della console, pagina di accesso |
| `zc_logo_primary` | 72×72, icona su fondo turchese | Favicon, icona dell'applicazione |
| `zc_logo_light` | 72×72, icona su fondo chiaro | Sfondi scuri |
| `zc_logo_dark` | 72×72, icona su fondo scuro | Sfondi chiari, stampa in negativo |

Il marchio esteso è largo più del triplo della sua altezza: va vincolata
l'altezza (`.brand-logo` in `static/css/style.css`) lasciando libera la
larghezza. Sotto i 30 pixel di altezza il payoff *live landscape cam* non è
più leggibile e conviene passare all'icona.
