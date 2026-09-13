# Distribution packaging templates

These are **templates**: fill in the `homepage`, `sha256`, and URLs for your
release before publishing to each channel.

| Channel | File | Publish with |
|---------|------|--------------|
| PyPI | `pyproject.toml` | `.github/workflows/release.yml` (Trusted Publishing) |
| Single-file binary | `pyinstaller/wzlcarrot.spec` | `scripts/build_binary.sh` / `.github/workflows/binaries.yml` |
| One-command install | `../scripts/install.sh` | curl-pipe or copy |
| Homebrew | `homebrew/wzlcarrot-cli.rb` | `brew install --build-from-source ./wzlcarrot-cli.rb` |
| Scoop | `scoop/wzlcarrot-cli.json` | `scoop install ./wzlcarrot-cli.json` |
| WinGet | `winget/wzlcarrot-cli.installer.yaml` | `wingetcreate update` |
| Debian/Ubuntu | `debian/control` | `dpkg-buildpackage` / `fpm` |
