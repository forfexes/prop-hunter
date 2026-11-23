# VERBINDLICHE REGEL – KARTENSTIL UNVERÄNDERLICH

**Geltungsbereich:** PROP HUNTER (NBA, NFL, NHL, MLB, WNBA, EuroLeague; Single, Ladder, Builder, Lottery); dieselbe Regel gilt für ALLE gegenwärtigen und künftigen Bots.

## Absolutes Design-Verbot ohne explizite Nutzerfreigabe

- **Bestehenden visuellen Stil NICHT ändern.** Keine Neugestaltung, keine neuen Stadionbilder, keine neue Farbwelt, Schriften, Rahmen, Kartenproportionen, Rubriken oder eigene Interpretation des Designs.
- Die vom Nutzer gelieferten **neuen Original-Karten und Screenshots** sind verbindlich; niemals einen generierten Ersatz oder eine vereinfachte PowerPoint-ähnliche Vorschau als Produktionsmaster ausgeben.
- Generierte neue Stilbilder, generische NBA-Arenen, dekorative Silhouetten, Avatar-/Kreisrahmen, aufgeklebte Wappen, Fantasieporträts und Fallback-Karten sind **VERBOTEN**. Echte Vereinswappen und authentische freigestellte Spielerbilder aus den Quellen verwenden; fehlende Assets nicht erfinden.
- Zulässige Arbeit **ohne** Designfreigabe: Daten- und Quotenprüfung, Fehlerbehebung, Layout-Überläufe korrigieren OHNE Änderungen des Stils, falsche/verzerrte Spielerfotos entfernen, Wappen sauber platzieren, bestehende Beschriftungen und Settlement korrekt befüllen, Tests ergänzen.
- Kein Preis/Markt/Match/Ergebnis/Spielerfoto als echt ausgeben, wenn nicht verifiziert; keine erfundenen Buchmacherquoten. Die originale Kartenhistorie und Settlement direkt in der ursprünglichen Telegram-Karte behalten.
- **Jede tatsächlich neue oder veränderte Mastergrafik zuerst IM CHAT als Bild zeigen, nicht als Download und nicht direkt an Telegram.** Erst bei ausdrücklicher visueller Zustimmung für diesen Master freigeben. Ein grüner CI-Test ist KEINE visuelle Zustimmung.
- Bestehende bestätigte Karten nicht automatisch auf neue Vorlagen migrieren. Ohne Freigabe nur unveränderte originalgetreue Vorlagen verwenden; unsichere/neue Varianten sperren statt beliebigen Ersatz zu veröffentlichen.
- Branding exakt nach jeweiliger vom Nutzer bereitgestellter Originalkarte beibehalten. Nicht alle Bots auf denselben Stil vereinheitlichen. `@prophunter` weder ohne Auftrag hinzufügen noch aus der Originalgrafik entfernen; Platzierung je Referenz beachten.

## Technik

Die nachstehenden Git-Blob-Hashes frieren nur den Stand der vorhandenen **Original-/freigegebenen Referenzbilder** ein. Sie sind keine Behauptung, dass unbestätigte Entwürfe als neue Master freigegeben wurden. `scripts/check_card_style_lock.py` und `.github/workflows/card_style_lock.yml` verhindern deren stillen Austausch. Neue Freigaben erfordern eine neue Nutzerentscheidung und entsprechend bewusste Änderung der gesperrten Bildliste. Änderungen nur am Rendercode allein müssen ebenfalls dieser unveränderlichen Designregel genügen.

**Kein generiertes Stadionbild dieser Chat-Sitzung darf ein Originalmaster im Bot ersetzen.**
