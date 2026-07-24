# qBittorrent Storage Mover

Ez a program automatikusan áthelyezi a qBittorrentben elkészült torrentek
adatait egy gyors letöltési meghajtóról (például NVMe SSD-ről) egy nagyobb
tárhelyre (például HDD-re), a telepítéskor megadott várakozási idő után,
miközben a torrentek tovább seedelnek.

Ez a leírás azoknak is szól, akik még soha nem telepítettek Linuxos
szolgáltatást. A parancsokat sorban, egyesével kell végrehajtani.

> [!IMPORTANT]
> A program jelenlegi változata natívan telepített `qbittorrent-nox`
> használatára készült. Dockerben futó qBittorrenthez ne használd változtatás
> nélkül.

## Mit csinál a program?

1. A megadott időközönként lekéri a torrentek állapotát a qBittorrent Web
   API-n keresztül.
2. Kiválasztja azokat, amelyek:
   - teljesen elkészültek;
   - legalább a beállított ideje elkészültek;
   - még a gyors forrásmeghajtón találhatók;
   - megfelelnek az opcionális TAG-szűrésnek.
3. Egyetlen kérésben átadja őket a qBittorrent költöztetési sorának.
4. A qBittorrent sorban áthelyezi az adatokat, és az új helyről tovább seedel.

A script nem másolja saját maga a fájlokat, és nem használ egyszerű `mv`
parancsot. Az áthelyezést mindig a qBittorrent végzi.

## Alapfogalmak röviden

| Fogalom | Jelentés |
|---|---|
| **Szerver** | A Linuxot és qBittorrentet futtató számítógép. |
| **SSH** | Távoli szöveges kapcsolat a szerverhez. |
| **Web UI** | A qBittorrent böngészőből elérhető kezelőfelülete. |
| **Forrásmappa** | A gyors meghajtón lévő jelenlegi letöltési mappa. |
| **Célmappa** | A nagyobb tárhelyen lévő mappa, ahová a torrentek kerülnek. |
| **TAG** | qBittorrentben egy torrenthez rendelt címke. |
| **Seedelés** | Az elkészült torrent adatainak visszaosztása. |
| **Dry run / próbaüzem** | A program megmutatja, mit tenne, de még nem mozgat. |
| **systemd timer** | A Linux időzítője, amely automatikusan elindítja a programot. |

## Mire lesz szükséged?

A telepítés előtt legyen meg:

- egy Linux szerver systemd rendszerrel;
- natívan telepített és működő `qbittorrent-nox`;
- Python 3.9 vagy újabb;
- bekapcsolt qBittorrent Web UI;
- a Web UI felhasználóneve és jelszava;
- a Web UI portja;
- a jelenlegi letöltési mappa pontos útvonala;
- a célmappa pontos útvonala;
- `sudo` jogosultság a szerveren;
- internetkapcsolat a GitHub repository letöltéséhez.

A forrásnak és a célnak külön fájlrendszeren kell lennie. Tipikus példa:

```text
Forrás (NVMe): /home/felhasznalo/torrents/qbittorrent
Cél (HDD):     /home/felhasznalo/storage
```

## 1. Kapcsolódás a szerverhez

Nyisd meg a saját számítógépeden a Terminált, majd írd be:

```bash
ssh FELHASZNALO@SZERVER_IP
```

Cseréld ki:

- `FELHASZNALO`: a szerveres felhasználónevedre;
- `SZERVER_IP`: a szerver IP-címére vagy domainnevére.

Példa:

```bash
ssh pista@192.0.2.10
```

Ha már a szerver parancssorában vagy, ezt a lépést hagyd ki.

## 2. A szükséges programok ellenőrzése

Futtasd:

```bash
command -v git
command -v python3
python3 --version
systemctl --version
```

Ha az első két parancs nem ír ki elérési utat, Debian vagy Ubuntu rendszeren
telepítsd őket:

```bash
sudo apt update
sudo apt install -y git python3
```

Más Linux-disztribúció esetén a rendszer saját csomagkezelőjével telepítsd a
`git` és `python3` csomagot.

## 3. A szükséges adatok megkeresése

### A qBittorrent Linux-felhasználója

Futtasd:

```bash
ps -eo user,comm | grep '[q]bittorrent-nox'
```

Példa eredmény:

```text
accofil  qbittorrent-nox
```

Ebben a példában a beírandó Linux-felhasználó: `accofil`.

### A Web UI címe és portja

Ha a script ugyanazon a szerveren fut, mint a qBittorrent, a cím általában:

```text
127.0.0.1
```

A portot a qBittorrent Web UI beállításaiban találod. Például:

```text
8080
```

Ha nem állítottál be külön HTTPS-t a qBittorrenthez, a protokoll:

```text
http
```

### A forrásmappa

Ez a qBittorrent alapértelmezett mentési útvonala. A Web UI-ban a
**Settings → Downloads → Default Save Path** résznél található.

### A célmappa

A célmappának már léteznie kell. Például:

```bash
sudo mkdir -p /mnt/storage
sudo chown QBIT_FELHASZNALO:QBIT_FELHASZNALO /mnt/storage
```

A `QBIT_FELHASZNALO` helyére a korábban megkeresett Linux-felhasználó kerüljön.
Meglévő mappánál ne változtass tulajdonost anélkül, hogy tudnád, más program
használja-e.

Ellenőrizd, hogy a forrás és a cél külön fájlrendszer:

```bash
findmnt -T /FORRAS/MAPPA
findmnt -T /CEL/MAPPA
```

A két parancsnál eltérő `SOURCE` eszközt kell látnod.

## 4. Letöltés a GitHubról

A szerveren futtasd:

```bash
cd ~
git clone https://github.com/takachlaszlo/qbittorrent-storage-mover.git
cd qbittorrent-storage-mover
```

Ellenőrizd, hogy jó mappában vagy:

```bash
ls -la
```

A listában szerepelnie kell többek között ezeknek:

```text
install.sh
qbit-move-completed.py
README.md
```

## 5. A telepítő elindítása

Futtasd:

```bash
sudo ./install.sh
```

Ha `Permission denied` hiba jelenik meg:

```bash
chmod +x install.sh
sudo ./install.sh
```

A `sudo` elkérheti a Linux-felhasználód jelszavát. Jelszóírás közben nem
jelennek meg csillagok vagy karakterek; ez normális. Írd be, majd nyomj
`Enter`-t.

## 6. Mit kérdez a telepítő?

A szögletes zárójelben látható érték az alapértelmezés. Ha az megfelelő,
egyszerűen nyomj `Enter`-t.

### `Linux user running qBittorrent`

A qBittorrent folyamat Linux-felhasználója.

Példa:

```text
accofil
```

### `qBittorrent Web UI protocol`

Általában:

```text
http
```

Csak akkor adj meg `https` értéket, ha magában a qBittorrentben HTTPS Web UI
van beállítva.

### `qBittorrent Web UI host/address`

Ha ugyanazon a szerveren fut minden:

```text
127.0.0.1
```

### `qBittorrent Web UI port`

A Web UI portja, például:

```text
8080
```

### `qBittorrent Web UI username`

A Web UI-ba történő bejelentkezéshez használt felhasználónév.

### `qBittorrent Web UI password`

A Web UI jelszava. Gépelés közben semmi nem látszik; ez szándékos biztonsági
viselkedés.

### `qBittorrent default download directory`

A gyors meghajtón lévő teljes forrásútvonal, például:

```text
/home/accofil/torrents/qbittorrent
```

### `Storage target directory`

A nagyobb tárhely teljes célútvonala, például:

```text
/home/accofil/storage
```

### `Move torrents this many hours after completion`

Hány órával a torrent elkészülése után kerüljön a költöztetési sorba.

Példák:

| Beírt érték | Jelentés |
|---:|---|
| `2` | Két óra után |
| `12` | Tizenkét óra után |
| `0.5` | Harminc perc után |

### `Run the check every N hours`

Milyen gyakran ellenőrizze a program a torrenteket.

Példák:

| Beírt érték | Jelentés |
|---:|---|
| `1` | Óránként |
| `6` | Hatóránként |
| `0.5` | Harmincpercenként |

### `Move all torrents or only selected tags? (all/tags)`

- `all`: minden megfelelő torrentet áthelyez;
- `tags`: csak a megadott qBittorrent TAG-ekkel rendelkezőket.

Ha `tags` értéket választasz, a TAG-eket vesszővel elválasztva add meg:

```text
autobrr,music,movies
```

Több TAG esetén már egyetlen egyező TAG is elegendő. A kis- és nagybetű
számít.

## 7. A próbaüzem értelmezése

A telepítő először biztonságos próbaüzemet indít. Ilyenkor nem történik
áthelyezés.

Példa:

```text
DRY RUN: eligible: 'Torrent neve'; age=9000s; source=/downloads; target=/storage
Dry run complete: 1 torrent(s); no data was moved.
```

Ez azt jelenti, hogy a torrent megfelel a feltételeknek, de még nem mozdult el.

A telepítő végül megkérdezi:

```text
Enable real moves and the configured timer now? [y/N]:
```

- `y`: bekapcsolja a valódi áthelyezést és az automatikus időzítőt;
- `n` vagy `Enter`: próbaüzemben hagyja, az időzítő kikapcsolva marad.

Csak akkor válassz `y`-t, ha a megjelenített forrás és cél helyes.
Az `y` megadása után a telepítő rögtön elindít egy valódi ellenőrzést. Az
áthelyezhető torrentek ekkor bekerülnek a qBittorrent költöztetési sorába;
ezután a beállított időközönként ismét lefut az ellenőrzés.

## 8. Sikeres telepítés ellenőrzése

Az időzítő állapota:

```bash
systemctl status qbit-mover.timer --no-pager
```

A kimenetben az `Active: active (waiting)` azt jelenti, hogy az időzítő
működik és a következő futásra vár. Ha a telepítő végén nem választottál
`y`-t, az időzítő szándékosan inaktív marad.

A következő futás időpontja:

```bash
systemctl list-timers qbit-mover.timer --no-pager --full
```

Az utolsó naplóbejegyzések:

```bash
sudo journalctl -u qbit-mover.service -n 100 --no-pager
```

Azonnali kézi ellenőrzés:

```bash
sudo systemctl start qbit-mover.service
```

Ha a `systemctl` kimenetének alján `(END)` látható, nyomd meg a `q` billentyűt
a lapozóból való kilépéshez. A `--no-pager` kapcsoló ezt megelőzi.

## Hol tárolódnak a beállítások?

A szerver saját beállításai itt vannak:

```text
/etc/qbit-mover/qbit-mover.env
```

A fájl tartalmazza a Web UI jelszavát, ezért ne másold nyilvános helyre és ne
töltsd fel GitHubra. A telepítő `0600` jogosultsággal hozza létre, így csak a
root olvashatja.

A fontos változók:

| Változó | Jelentés |
|---|---|
| `QB_URL` | A Web UI teljes címe és portja |
| `QB_USERNAME` | Web UI-felhasználónév |
| `QB_PASSWORD` | Web UI-jelszó |
| `SOURCE_PATH` | Forrásmappa |
| `TARGET_PATH` | Célmappa |
| `MIN_AGE_SECONDS` | Várakozási idő másodpercben |
| `MIN_FREE_BYTES` | A célmeghajtón fenntartandó szabad hely bájtban |
| `INCLUDE_TAGS` | Engedélyezett TAG-ek, üresen minden torrent |
| `DRY_RUN` | `1`: próbaüzem, `0`: valódi áthelyezés |

Kezdőként a beállítások kézi szerkesztése helyett futtasd újra a telepítőt:

```bash
cd ~/qbittorrent-storage-mover
sudo ./install.sh
```

Az ellenőrzések gyakorisága nem az env fájlban, hanem a
`/etc/systemd/system/qbit-mover.timer` fájlban tárolódik. Ezt is a telepítő
állítja be, ezért az időköz módosításához szintén futtasd újra a telepítőt.

## Frissítés újabb verzióra

```bash
cd ~/qbittorrent-storage-mover
git pull
sudo ./install.sh
```

A telepítő ismét bekéri és ellenőrzi a beállításokat, majd új próbaüzemet
végez.

## Eltávolítás

Lépj a repository mappájába:

```bash
cd ~/qbittorrent-storage-mover
sudo ./uninstall.sh
```

Ez eltávolítja:

- a script telepített példányát;
- a systemd service-t és timert;
- a szerveroldali env fájlt és a benne tárolt jelszót.

A qBittorrent által már elfogadott költöztetések ettől nem állnak le.

Ha a letöltött repository mappáját is törölni szeretnéd:

```bash
cd ~
rm -rI -- "$HOME/qbittorrent-storage-mover"
```

A parancs törlés előtt megerősítést kér. Csak akkor írj `y` választ, ha valóban
a `qbittorrent-storage-mover` mappát jelzi.

## Gyakori hibák

### `qBittorrent Web API login failed`

A Web UI felhasználónév vagy jelszó hibás. Ellenőrizd, hogy ugyanazokkal az
adatokkal be tudsz-e lépni a qBittorrent böngészős felületére.

### `HTTP Error 403: Forbidden`

A qBittorrent hitelesítést kér, de a megadott belépési adatok nem megfelelőek,
vagy az IP-cím átmenetileg tiltásra került túl sok sikertelen próbálkozás miatt.

### `Source and target are on the same filesystem`

A program szerint a forrás és a cél ugyanazon a meghajtón van. Ennek gyakori
oka, hogy a HDD nincs felcsatolva. Ellenőrzés:

```bash
findmnt -T /CEL/MAPPA
df -hT /FORRAS/MAPPA /CEL/MAPPA
```

Ne kapcsold ki ezt a védelmet: megakadályozza, hogy hiányzó HDD mount esetén a
script véletlenül a rendszermeghajtót töltse meg.

### `cannot write to`

A qBittorrent Linux-felhasználó nem írhat a célmappába. Ellenőrzés:

```bash
namei -l /CEL/MAPPA
```

### `SKIPPED, target already exists`

Azonos nevű fájl vagy mappa már van a célhelyen. A program biztonsági okból nem
írja felül. Vizsgáld meg kézzel a meglévő tartalmat.

### `No completed torrents are currently eligible`

Ez nem feltétlenül hiba. Jelenleg nincs olyan torrent, amely:

- teljesen elkészült;
- elérte a megadott várakozási időt;
- még a forrásmappában van;
- és megfelel az esetleges TAG-szűrésnek.

### A terminál csak `>` jelet mutat

Valószínűleg egy Markdown kódblokkot lezáró három backtick karaktert is
bemásoltál. Nyomj `Ctrl+C`-t, majd másold be újra csak a szürke kódblokk
belsejében lévő parancsot.

## Gyakori kérdések

### Aktív feltöltés közben is áthelyez?

Igen. A qBittorrent kezeli az állapotváltozást, majd az új helyről folytatja a
seedelést. A tényleges fájlmozgatás idejére a qBittorrent átmenetileg
szüneteltetheti az adott torrentet.

### Miért kerül egyszerre több torrent `moving` állapotba?

A script egy kötegben adja át az összes megfelelőt. A qBittorrent a saját
belső költöztetési sorában végzi el a tényleges fájlműveleteket.

### A program törli az eredeti adatokat?

A qBittorrent „Set location” funkciója valódi áthelyezést végez. A sikeres
költöztetés után az adat az új helyen marad, és onnan seedel tovább.

### Mi alapján számítja a várakozási időt?

A qBittorrent által jelentett befejezési idő (`completion_on`) alapján.

### Mi történik, ha nincs elég hely?

A program 10 GiB biztonsági tartalékot fenntart, és nem adja a költöztetési
sorhoz azt a torrentet, amely már nem férne el.

### Dockerrel működik?

Ez a telepítő nem Dockerhez készült. Konténeres qBittorrentnél a host és a
konténer eltérő útvonalakat láthat, ezért külön konfiguráció szükséges.

## Biztonsági megoldások

- Az első futás mindig próbaüzem.
- A jelszó gépelése rejtett.
- A valódi env fájl nem kerül a repository-ba.
- A konfigurációt csak root olvashatja.
- A célmappának már léteznie kell.
- A qBittorrent-felhasználónak írnia kell tudnia a célba.
- A forrás és cél nem lehet ugyanazon a fájlrendszeren.
- A program nem ír felül létező azonos nevű célt.
- 10 GiB szabad helyet tartalékol.

## Projektfájlok

| Fájl | Feladat |
|---|---|
| `install.sh` | Interaktív telepítő és próbaüzem |
| `uninstall.sh` | Eltávolító |
| `qbit-move-completed.py` | A qBittorrent API-t kezelő program |
| `qbit-mover.env.example` | Titkok nélküli mintakonfiguráció |
| `systemd/` | Service- és timer-sablonok |
| `tests/` | Automatikus tesztek |

## Licenc

MIT
