#!/bin/bash

# Detect OLSPanel base directory
BASE_DIR="/usr/local/olspanel/mypanel"
if [ ! -d "$BASE_DIR" ]; then
  # Fallback to local discovery
  BASE_DIR="$(pwd)"
  if [ ! -f "$BASE_DIR/manage.py" ]; then
    BASE_DIR="$(dirname "$(dirname "$BASE_DIR")")"
  fi
fi

# Define source and destination paths
MODULE_SRC="$BASE_DIR/3rdparty/selfhealer/modules/selfhealer"
MODULE_DEST="$BASE_DIR/modules/selfhealer"
ICON_SVG_SRC="$BASE_DIR/3rdparty/selfhealer/plugin_icon.svg"
ICON_SVG_DEST="$BASE_DIR/media/icon/selfhealer.svg"
ICON_PNG_SRC="$BASE_DIR/3rdparty/selfhealer/plugin_icon.png"
ICON_PNG_DEST="$BASE_DIR/media/icon/selfhealer.png"

# Copy Django module to the system modules directory
if [ -d "$MODULE_SRC" ]; then
  mkdir -p "$MODULE_DEST"
  cp -rf "$MODULE_SRC"/* "$MODULE_DEST"/
  chown -R www-data:www-data "$MODULE_DEST"
  echo "✅ Django selfhealer module copied to $MODULE_DEST"
else
  echo "❌ Error: Django selfhealer module source not found: $MODULE_SRC"
  exit 1
fi

# Deploy Icons
if [ -f "$ICON_SVG_SRC" ]; then
  cp -f "$ICON_SVG_SRC" "$ICON_SVG_DEST"
  chown www-data:www-data "$ICON_SVG_DEST"
  echo "✅ SVG vector icon deployed to $ICON_SVG_DEST"
fi
if [ -f "$ICON_PNG_SRC" ]; then
  cp -f "$ICON_PNG_SRC" "$ICON_PNG_DEST"
  chown www-data:www-data "$ICON_PNG_DEST"
  echo "✅ PNG preview icon deployed to $ICON_PNG_DEST"
fi

# Run the system healer immediately on installation to fix OLS/Webmail/phpMyAdmin bugs on-the-fly
echo "🚀 Running initial system diagnostics & self-healer..."
if [ -f "$BASE_DIR/manage.py" ]; then
  /root/venv/bin/python "$BASE_DIR/manage.py" shell -c "import django; django.setup(); from modules.selfhealer.views import run_self_healer_cli; run_self_healer_cli()"
  echo "✅ Post-installation system self-heal completed successfully."
else
  echo "⚠️ Warning: Django manage.py not found at $BASE_DIR. Post-install self-heal skipped."
fi

# Restart the panel service asynchronously to load the new module
if systemctl is-active --quiet cp 2>/dev/null; then
  (sleep 2 && systemctl restart cp) &
  echo "🔄 Scheduled OLSPanel backend restart..."
fi

echo "🎉 System Self-Healer installation script completed successfully."
