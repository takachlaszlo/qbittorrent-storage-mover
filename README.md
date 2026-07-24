# qBittorrent Storage Mover

Moves torrents from a fast download filesystem to larger storage after they
have been complete for two hours, while qBittorrent keeps seeding them.

The mover sends all eligible torrent hashes to qBittorrent in one
`setLocation` API request. qBittorrent manages its own relocation queue and
performs the actual file operations.

## Requirements

- Linux with systemd
- Native `qbittorrent-nox` installation (not Docker)
- Python 3.9 or newer
- qBittorrent Web UI/API enabled
- Source and target on different filesystems
- The qBittorrent Linux user must be able to write to the target directory

## Install

```bash
git clone https://github.com/takachlaszlo/qbittorrent-storage-mover.git
cd qbittorrent-storage-mover
sudo ./install.sh
```

The installer asks for:

- Linux user running qBittorrent
- Web UI protocol, host and port
- Web UI username and password
- Current qBittorrent download directory
- Storage target directory

The password input is hidden. Server-specific settings are written to
`/etc/qbit-mover/qbit-mover.env` with mode `0600`; no real `.env` file belongs
in the repository.

Installation starts with a dry run. The hourly timer is enabled only after
the dry run succeeds and you explicitly approve activation.

## Defaults

- Completed age: 2 hours (`MIN_AGE_SECONDS=7200`)
- Schedule: hourly
- Free-space reserve: 10 GiB
- Destination: the exact target directory supplied during installation

## Status and logs

```bash
systemctl status qbit-mover.timer --no-pager
systemctl list-timers qbit-mover.timer --no-pager --full
sudo journalctl -u qbit-mover.service -n 100 --no-pager
```

Run an immediate check:

```bash
sudo systemctl start qbit-mover.service
```

## Configuration

Edit `/etc/qbit-mover/qbit-mover.env`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl start qbit-mover.service
```

Never commit the real environment file.

## Uninstall

```bash
sudo ./uninstall.sh
```

Stopping this helper does not cancel moves already accepted by qBittorrent.

## Safety

- Refuses to run if source and target are on the same filesystem, which also
  protects against an unmounted storage filesystem.
- Requires the target directory to exist.
- Keeps a 10 GiB free-space reserve.
- Skips content whose destination name already exists.
- Uses a dry run before first activation.
- Stores the generated environment file as root-only.

## License

MIT
