# PROP HUNTER — Originalbilder und Sportvorlagen

**Verbindlich:** Die vier vom Nutzer gelieferten Original-Layouts müssen als Binärdateien (JPG/WEBP) im Repository liegen. Keine nachgebauten Ersatzlayouts als Originale deklarieren.

| Kartentyp | Originalfoto / Referenz | Vorgesehenes Originalasset |
|---|---|---|
| Single | `1000114998.jpg` | `card_templates/originals/single.jpg` |
| Ladder | `1000114995.jpg` | `card_templates/originals/ladder.jpg` |
| Builder | `1000114996.jpg` | `card_templates/originals/builder.jpg` |
| Lottery | `1000114997.jpg` | `card_templates/originals/lottery.jpg` |

Die Screenshots enthalten Beispielspieler/Quoten sowie Handy-Bedienelemente; für eine dynamische Karte müssen erst die eigentlichen Bilder freigestellt und die Beispieldaten entfernt werden. Die unveränderten Quelldateien bleiben separat als Referenz erhalten.

## Vier Sportumgebungen, vier Original-Layouts = 16 Templates

- **Basketball:** NBA, WNBA, NCAAB, Euroleague
- **American Football:** NFL, NCAAF
- **Eishockey:** NHL
- **Baseball:** MLB

Jeder Sportbereich braucht die vier Dateien unter
`card_templates/render_ready/{basketball|football|hockey|baseball}/{single|ladder|builder|lottery}.webp`.

Alle Vorlagen behalten die jeweilige **Originalanordnung**, Branding und @prophunter. Nur Sportlogo, Teamwappen, Spielerporträt, Spielort, echte Quote, L10/L15 und später Ergebnis ändern sich.

**Ladder:** Immer **genau ein Spielerbild**, ein Spieler, mehrere Schwellen/Quoten; nie mehrere verschiedene Spieler wie bei Builder.

**Aktueller Status:** Der Code enthält die Sport-/Layout-Zuordnung und Ladder-Korrektur, aber die vier Nutzer-JPGs und die 16 sauber bearbeiteten sportbezogenen WEBP-Dateien sind noch **nicht** im Repository. Ein erfolgreicher Originalvorlagen-Versand ist deshalb nicht nachgewiesen. Vorlage erst nach Asset-Prüfung, Bildvergleich und Telegram-Probelauf als produktiv markieren.
