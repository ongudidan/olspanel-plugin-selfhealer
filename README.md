# OLSPanel System Self-Healer Plugin

A lightweight, robust, and interactive utility plugin designed for OLSPanel servers to automatically diagnose and repair integration settings, permission models, script handlers, and symlinks on-the-fly.

## 🌟 Key Features
1. **Automated Post-Installation Fixes**: As soon as the plugin is installed, its installer script (`plugin.cmd`) executes the backend diagnostics and applies necessary fixes automatically.
2. **On-the-Fly Diagnostics GUI**: Adds a modern, premium control interface inside your OLSPanel admin dashboard (`/module/selfhealer/gui/`) featuring service status metrics and a system healing control button.
3. **Real-Time Streaming Terminal**: Connects to the backend via Server-Sent Events (SSE) to stream stdout details line-by-line in a glassmorphic console log display.
4. **OLS & suEXEC Compatibility Healing**:
   - Aligns `mypanel` configuration naming by ensuring `vhost.conf` exists on disk.
   - Maps the target server IP address, `127.0.0.1`, and `localhost` to the `mypanel` virtual host in listener maps.
   - Updates `restrained` option to `0` for all admin panel virtual hosts (`mypanel` and `panel_*`) in `httpd_config.conf` to allow access outside `$VH_ROOT`.
   - Injects the global PHP script handler mapping (`add lsapi:lsphp php`) into all custom panel virtual host script handlers.
   - Restores missing `/home/fortunedevs/public_html/html` Document Root directories with correct user ownership.
   - Recreates missing or broken phpMyAdmin / Webmail symlinks in `/usr/local/lsws/Example/html/`.
   - Recursively sets RainLoop webmail data directories to `777` (world-writable) for suEXEC compatibility.
   - Diagnoses and repairs APT repository release info changes automatically to prevent PHP package/extension installation failures.

## 📦 How to Build / Pack
To bundle this plugin as a zip archive ready for uploading/installing inside OLSPanel, run:
```bash
zip -r olspanel-plugin-selfhealer.zip selfhealer/
```

## 🛠️ Folder Structure
- `selfhealer/plugin_selfhealer.conf`: OLSPanel integration configurations.
- `selfhealer/plugin.cmd`: Post-install shell command script.
- `selfhealer/plugin_icon.svg`: Modern shield icon.
- `selfhealer/modules/selfhealer/`: Django module code.
  - `views.py`: Execution pipeline, status checks, and log streamer.
  - `urls.py`: Routed views.
  - `apps.py`: Dynamic auto-discovery hook registrations.
  - `templates/selfhealer/gui.html`: Premium GUI console template.
