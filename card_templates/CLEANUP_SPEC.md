# PROP HUNTER – Originalvorlagen bereinigen, nicht überkleben

**Verbindliche Vorgabe:** Die vier originalen Nutzer-JPGs (`originals/single.jpg`,
`ladder.jpg`, `builder.jpg`, `lottery.jpg`) bleiben unverändert.

1. Aus dem echten Originalbild eine **separate bereinigte Basisdatei**
   `cleaned/<family>.png` erstellen. Ehemalige Beispieldaten vollständig
   entfernen: Spielerfotos, Spielernamen, Teamwappen und Teamnamen,
   Match-/Stadion-/Datumsangaben, Quoten, Odds, Statistiken, Einsätze,
   Zahlen, Trefferquoten, Auswertungsergebnisse und sportspezifische
   Beispiel-Wasserzeichen.
2. Die ursprüngliche visuelle Identität bleibt erhalten: Arena, Gold-/Violett-
   /Cyan-Akzente, Markenlogo, Formatüberschrift, feste Piktogramme,
   dekorative Rahmen und strukturierte freie Felder. Die NBA-Ligakennung
   ist eine statische Kennung, **kein Beispiel-Teamwappen**.
3. Niemals versuchen, alte Beispieldaten **zur Laufzeit** nur mit schwarzen,
   dunkelblauen oder deckenden Rechtecken zu kaschieren. Auf den fertigen,
   bereinigten Basisdateien gibt es überhaupt keine Beispieldaten mehr.
4. Erst danach die **echten Daten des konkreten Tipps** in die leeren
   Felder einsetzen. Das ist normale Kartengenerierung, kein Übermalen
   vorhandener Namen/Bilder/Zahlen. Für Ladders nur ein Spielerportrait
   (ein Spieler, mehrere Stufen). Builder mit 4–6 Spielern: alle zeigen.
   L5/L10/L15 nur aus tatsächlichen Formdaten; Modelle/Quoten nie erfinden.
5. **Visuelle Qualitätskontrolle ist Pflicht:** komplette PNG-Vorschau für
   Single, Ladder (2–5), Builder (2–6) und Lottery (2–9), inklusive
   Sonderfällen ohne Foto/Wappen; Kontrolle auf Geisterbilder, Schriftreste,
   Farbflecken, fehlende Rahmen und abgeschnittene Texte.
   Erst bei bestandener Sichtkontrolle darf eine bereinigte Vorlage
   in Produktion gehen oder Telegram-Karten ersetzen.

**Status 19.11.2026:** Ein erster rein automatischer OpenCV-Inpainting-Test
hat sichtbar schlechte Rekonstruktionsartefakte ergeben. Diese Experimental-
PNG-Dateien werden **nicht** als Produktionsvorlagen freigegeben und
wurden nicht nach `main/card_templates/cleaned` committed. Der
Testworkflow erstellt nur Vorschau-Artefakte; die echten Original-JPGs
sind unverändert und der aktuelle Telegram-Generator wurde dadurch
nicht umgestellt.

## Freigegebenes Layout – Spieler ohne Rahmen (19.11.2026)

Der Nutzer hat die neue **Single-Referenz mit rahmenlosem, grossflächigem
Spielerfoto direkt im Stadionhintergrund** ausdrücklich freigegeben.

- Ein freigestelltes Spielerfoto als **separate transparente Ebene** links,
  ohne Goldrahmen, dunkles Portrait-Rechteck oder sichtbare Kachel.
- Weiche Übergänge am rechten und unteren Rand, damit der Spieler optisch
  im Stadion steht. Keine Überdeckung der Teamwappen oder Tippfelder.
- Logo, Liga, Teams/VS, **verifizierte** Spielzeit, Spielername, Markt,
  Original-Buchmacherquote, L5/L10/L15, Modellwerte, Einsatz und
  Auswertung bleiben lesbar.
- Keine erfundenen Form-, Wahrscheinlichkeits-, Quoten- oder Ergebniswerte.
- Ladders: **ein** Spieler, 2–5 Stufen. Builder: 2–6 echte Legs und
  entsprechend mehrere Spieler; kein Darts-Design.
- Technische Implementierung: `_background_portrait` in
  `prop_hunter_original_compositor.py`. Diese wird erst verwendet, wenn
  eine **visuell geprüfte, wirklich saubere** Quelle unter
  `card_templates/approved/single.png` existiert.
- Bis dahin **keine** automatische Umstellung bestehender Telegram-Karten
  auf eine nur simulierte, unbereinigte oder dunkel übermalte Vorlage.
  Die Tests in `prop_hunter_borderless_portrait_test.py` prüfen den
  neuen Layer isoliert, ohne echte Tipps zu posten.
