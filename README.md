# UGREEN Album Share für Home Assistant

Bindet **geteilte Alben** (auch smarte Alben) eines UGREEN NAS (UGOS Pro, App „Fotos“) in Home Assistant ein – ohne SMB/WebDAV-Freigabe der ganzen Fotobibliothek und ohne NAS-Login.

- **Medien-Browser:** Jedes Album erscheint unter *Medien → UGREEN Alben* als Ordner mit allen Fotos (neueste zuerst). Die Liste wird live vom NAS gelesen, neue Fotos im Album sind sofort da.
- **Bild-Entität pro Album:** `image.<album>_zufallsfoto` zeigt ein zufälliges Foto und wechselt im einstellbaren Intervall – ideal für Picture-Entity-Karten oder Wandtablets.
- **Beliebig viele Alben**, verwaltet über *Konfigurieren*.

Fotos werden über Home Assistant ausgeliefert (Proxy), funktionieren also auch, wenn das NAS vom Browser aus nicht erreichbar ist (z. B. von unterwegs). HEIC-Fotos liefert das NAS automatisch als WebP.

## Installation über HACS

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → URL dieses Repositories, Typ **Integration**.
2. „UGREEN Album Share“ installieren und Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → UGREEN Album Share*.

## Album-Link erzeugen

In der UGREEN Fotos-App (Web oder Smartphone) ein Album öffnen → **Teilen** → Link kopieren. Der Link sieht so aus:

```
https://<nas>/photo/share/?id=2&pagetype=share&uuid=0d7328f5-....
```

- Ist die Freigabe mit einem **Zugangscode** geschützt, diesen im Feld „Zugangscode“ angeben (sonst leer lassen).
- Die Freigabe sollte **kein Ablaufdatum** haben, sonst verschwindet das Album danach.
- Home Assistant muss die Adresse im Link erreichen können.

## Konfiguration

Beim Hinzufügen wird der erste Album-Link abgefragt. Danach unter *UGREEN Album Share → Konfigurieren*:

| Menüpunkt | Funktion |
|---|---|
| Album hinzufügen | weiteren Freigabe-Link eintragen (Zugangscode und Name optional, Standard-Name ist der Albumname) |
| Album bearbeiten | Name oder Zugangscode eines Albums ändern (z. B. wenn der Code auf dem NAS geändert wurde) |
| Alben entfernen | ein oder mehrere Alben entfernen (inkl. Gerät & Entität) |
| Einstellungen | Wechselintervall des Zufallsfotos, SSL-Prüfung (z. B. für selbstsignierte Zertifikate abschalten) |

## Beispiel: Diashow-Karte

```yaml
type: picture-entity
entity: image.laura_zufallsfoto
show_state: false
show_name: false
```

## Wie es funktioniert

Die Integration nutzt dieselbe API wie die Freigabe-Webseite des NAS:

1. `POST /ugreen/v5/photo/share/white/verify` → anonymes Token (24 h gültig, wird automatisch erneuert).
   Bei geschützten Freigaben liefert das NAS stattdessen einen RSA-Schlüssel (`x-rsa-token`); der Zugangscode wird damit verschlüsselt an `POST …/white/password` geschickt, was das Token liefert.
   Das NAS begrenzt Code-Eingaben (HTTP 429, ca. 1 Minute warten).
2. `GET /ugreen/v5/photo/share/external/detail` → Fotoliste
3. `GET /ugreen/v5/photo/share/external/stream?id=…&size_type=…` → Foto (1 = Vorschau, 3 = volle Größe als WebP, 0 = Original)

Der Zugangscode wird in der Home-Assistant-Konfiguration (`.storage`) gespeichert, wie Passwörter anderer Integrationen auch. Das NAS liefert über das Token nur Fotos aus, die im geteilten Album enthalten sind.

Getestet mit UGOS Pro, App `com.ugreen.album-share` Version 324.
