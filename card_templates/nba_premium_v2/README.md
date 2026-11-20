# PROP HUNTER — NBA Premium Mastervorlagen v2

52 echte, **datenfreie**, mehrschichtige SVG-Master im freigegebenen blau-goldenen Arena-Stil. Der NBA-Logo-Kasten bleibt erhalten, mit dem NBA-Logo aus der vom Nutzer gelieferten Originalkarte anstelle des Textplatzhalters „NBA PROPS“.

## Aufbau
- `assets/arena.jpg`: eigenständiger Basketballarena-Hintergrund **ohne** Spieler, Teamwappen, Quoten, Namen oder Statistiken.
- `single_*.svg` (21): Single-Märkte; `longshot.svg` (1).
- `ladder_2.svg` bis `ladder_6.svg` (5): **ein** freigestellter Spieler, mehrere Stufen.
- `same_player_2.svg` bis `_6.svg` (5): **ein** Spieler, 2–6 verschiedene Props.
- `builder_2.svg` bis `_6.svg` (5): 2–6 Spieler/Legs mit eigenen transparenten Fotoebenen.
- `cross_game_2.svg` bis `_6.svg` (5), `combo_2.svg` bis `_6.svg` (5), `lottery_2.svg` bis `_6.svg` (5).

Jedes dynamische Textfeld ist mit `data-field` markiert. Fotos/Wappen sind separate `data-image-slot`-Ebenen. **Keine** eingebrannten Namen, Fotos, Wappen, Quoten oder Statistiken; **keine** überklebten Beispielkarten. Wappen sind frei schwebend und Teamnamen stehen darunter. Spieler links ohne Rahmen. Spielername kleiner, ohne PRO-TIP-Kasten oder Trennlinie.

`previews/` enthält die gerenderten **leeren** Master, nicht reale Tipps. Produktiv ist der neue Renderer über `PH_NBA_PREMIUM_V2=1` nur für NBA-Tipps mit echten Fotos, Wappen, Spielzeiten und verifizierten Buchmacherquoten aktiviert. Bei fehlenden Daten wird keine Ersatzgrafik erzeugt. Alte/prozedurale Designs sind als Fallback verboten; der Premium-Renderer muss erfolgreich sein. Beim Settlement wird die **ursprüngliche Telegram-Nachricht bearbeitet**, ohne zusätzliche Tippnachricht.

`build_masters.py` erzeugt die 52 SVGs und die Prüf-Vorschauen aus dem vorhandenen Arena-Bild. `manifest.json` definiert die Familien und Feldbelegungen.
