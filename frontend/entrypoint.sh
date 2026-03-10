#!/bin/sh

API_URL="${VITE_API_URL:-http://localhost:8000}"
echo "Injecting API_URL: $API_URL"

# Write a runtime config JS file that the app will read
cat > /usr/share/nginx/html/config.js << JSEOF
window.__API_URL__ = "$API_URL";
JSEOF

nginx -g "daemon off;"
