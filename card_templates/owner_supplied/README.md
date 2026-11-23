# PROP HUNTER NBA Single – Original vom 22.11.2026

- **Unveränderte Nutzerdatei:** `single_blank_20261122.png`, 512×512 Pixel, SHA-256 `499ed837eb187b672c9a7781553eb9889c9fe37bb501aef3df61da1010019692`. Die Bilddatei enthält das Gold-/Cyan-/Grün-Design, die Stadionkulisse und die Originalfelder.
- **Bereinigte Originalstufe:** `single_blank_editable_20261122.png` entfernt das statische Beispielresultat «OFFEN». **Aktueller Wappen-Master:** `single_blank_floating_20261123.png`, erstellt mit `build_floating_single.py`, entfernt zusätzlich die zwei alten Goldkreise und stellt den gemeinsamen, dunklen Original-Stadionhintergrund wieder her. Das originale `VS`, PROP-HUNTER-Logo, NBA-Schild und die übrigen Rahmen bleiben erhalten.
- **Renderer:** `prop_hunter_owner_supplied_single.py`. Fügt nur Spielerfoto, echte Logos, Namen, Datum, Markt, Quote, L5/L10/L15, Modellwerte, Einsatz und Status in die dafür vorgesehenen Originalfelder ein. Keine überklebten Beispielwerte, kein farbiges Abdeck-Rechteck und kein Ersatzdesign.
- **Adapter:** `prop_hunter_nba_owner_bridge.py` nutzt diese neue Vorlage nur für `type=single`, wenn `PH_NBA_USER_SINGLE_20261122=1` gesetzt ist. Ladders/Builder/Lottery behalten ihre eigenen Originale.
- **Sicherheitsprüfung:** `prop_hunter_owner_pixel_qa.py` verifiziert die Originalquelle und die unberührten festen Gold-Header-Pixel. Der Telegram-Metadatenrand wird **unterhalb** des vollständigen 1080-Pixel-Kartenbildes ergänzt; es wird nichts über der Karte angezeigt.
- **QA:** `python -m unittest -v test_prop_hunter_owner_supplied_single`. Prüfungen verwenden **künstliche Testdaten** und veröffentlichen keine Telegram-Tipps.

**Live-Freigabe:** Ein grüner Offline-Test allein ist keine Bestätigung, dass die neuen echten Telegram-Bilder korrekt aussehen. Die produktive Feature-Flag-Aktivierung erfolgt nur getrennt nach bestandener Quellen-, Renderer- und Telegram-Sandbox-Prüfung. Keine geratenen Buchmacherquoten.
