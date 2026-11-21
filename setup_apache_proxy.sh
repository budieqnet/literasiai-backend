#!/bin/bash
# setup_apache_proxy.sh
# Script untuk mengkonfigurasi Apache reverse proxy ke backend LiterasiAI (port 5008)
# Jalankan dengan: sudo bash setup_apache_proxy.sh

CONF_FILE="/etc/apache2/sites-enabled/000-default.conf"

echo "==> Menambahkan proxy rules LiterasiAI ke Apache..."

# Tambahkan sebelum tag </VirtualHost>
sed -i 's|</VirtualHost>|	# LiterasiAI — Proxy ke backend Flask (port 5008)\n\tProxyPass /api/ http://127.0.0.1:5008/api/\n\tProxyPassReverse /api/ http://127.0.0.1:5008/api/\n\tProxyPass /health http://127.0.0.1:5008/health\n\tProxyPassReverse /health http://127.0.0.1:5008/health\n</VirtualHost>|' "$CONF_FILE"

echo "==> Menguji konfigurasi Apache..."
apache2ctl -t

echo "==> Merestart Apache..."
systemctl reload apache2

echo ""
echo "=== Selesai! ==="
echo "Sekarang frontend di http://localhost/literasiai-web/ akan otomatis terhubung ke Flask backend."
echo "API_BASE di frontend bisa diubah ke '' (string kosong) agar menggunakan path relatif."
