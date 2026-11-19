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
