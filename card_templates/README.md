# PROP HUNTER — Mastervorlagen-Stand 19.11.2026

**Neue Entscheidung des Nutzers:** Wie bei NETRATTLER gibt es jetzt eine
**vollständige NBA-Premiumkollektion mit 52 datenfreien, editierbaren
SVG-Mastern** unter [nba_masters](./nba_masters). Sie umfasst Single-Props
(21 Marktvarianten), Longshot, Ladder, Builder, Same-Player-Builder,
Cross-Game-Builder, Combo/Multi und Lottery, jeweils 2–6 Legs.
Alle Spielerfotos werden als **freigestellte, rahmenlose Ebenen**
eingesetzt; Namen, Wappen, Uhrzeiten, Quoten, L5/L10/L15 und Auswertung
sind getrennte Text-/Bildslots. Es wird nichts überklebt.

**Abgrenzung:** Die vier historischen JPGs in `originals/` bleiben
unverändert als **Referenzbilder**, nicht als live nutzbare Datenmaster.
Die neuen 52 SVGs sind ein **neues, sauberes Layoutsystem**, das sich
am freigegebenen blau-goldenen Originalstil und der NETRATTLER-
Masterkollektion orientiert. Es ist **noch nicht produktiv aktiviert**;
vor Telegram-Einsatz sind visuelle Freigabe, echte Datenzuordnung und
Integration des neuen SVG-Renderers erforderlich.

---

# PROP HUNTER — Originalbilder und Sportvorlagen

**Verbindlich:** Die vier vom Nutzer gelieferten Original-Layouts müssen als Binärdateien (JPG/WEBP) im Repository liegen. Keine nachgebauten Ersatzlayouts als Originale deklarieren.

| Kartentyp | Originalfoto / Referenz | Vorgesehenes Originalasset |
|---|---|---|
| Single | `1000114998.jpg` | `card_templates/originals/single.jpg` |
| Ladder | `1000114995.jpg` | `card_templates/originals/ladder.jpg` |
| Builder | `1000114996.jpg` | `card_templates/originals/builder.jpg` |
| Lottery | `1000114997.jpg` | `card_templates/originals/lottery.jpg` |

Die Screenshots enthalten Beispielspieler/Quoten sowie Handy-Bedienelemente; für eine dynamische Karte müssen erst die eigentlichen Bilder freigestellt und die Beispieldaten entfernt werden. Die unveränderten Quelldateien bleiben separat als Referenz erhalten.

## Genau vier Original-Layouts — für ALLE Sportarten

**Keine neue Sport-Vorlage und kein anderes Design.** NBA, WNBA, NFL, NHL, MLB, NCAAB, NCAAF und Euroleague verwenden **dieselben vier von dir gelieferten NBA-Layouts**: Single, Ladder, Builder und Lottery. Lediglich Sportlogo, Foto des richtigen Spielers, Teamwappen, Marktdaten, echte Quoten, L10/L15 und Ergebnis werden dynamisch ersetzt.

Zielpfade für die bereinigten, automatisch befüllbaren Original-Layouts:

- `card_templates/render_ready/basketball/single.webp`
- `card_templates/render_ready/basketball/ladder.webp`
- `card_templates/render_ready/basketball/builder.webp`
- `card_templates/render_ready/basketball/lottery.webp`

Alle Vorlagen behalten die jeweilige **Originalanordnung**, Branding und @prophunter. Nur Sportlogo, Teamwappen, Spielerporträt, Spielort, echte Quote, L10/L15 und später Ergebnis ändern sich.

**Ladder:** Immer **genau ein Spielerbild**, ein Spieler, mehrere Schwellen/Quoten; nie mehrere verschiedene Spieler wie bei Builder.

**Stand 18.11.2026:** Die vier **unveränderten** Nutzer-JPGs sind in `card_templates/originals/` als Binärdateien auf GitHub vorhanden und überprüft: `single.jpg`, `ladder.jpg`, `builder.jpg`, `lottery.jpg` (Commit `3efd5c8e`). Die vier datenfreien `render_ready`-WEBPs sind **noch nicht** hochgeladen. Der Generator verwendet daher weiterhin seinen bisherigen Hintergrund-Fallback. Weder eine pixelgenaue Originaldarstellung mit wechselnden echten Spieldaten noch der Telegram-Originalvorlagen-Versand sind nachgewiesen. Die Originalscreenshots enthalten beispielhafte Quoten/Spieler und dürfen vor Datenbereinigung NICHT als ungefilterte Live-Pick-Hintergründe benutzt werden.
