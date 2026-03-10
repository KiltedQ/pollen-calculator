#!/bin/sh

# Replace the placeholder API URL in the built JS files with the runtime env var
if [ -n "$VITE_API_URL" ]; then
  echo "Injecting VITE_API_URL: $VITE_API_URL"
  find /usr/share/nginx/html/assets -name "*.js" -exec \
    sed -i "s|http://localhost:8000|$VITE_API_URL|g" {} \;
else
  echo "Warning: VITE_API_URL not set, defaulting to http://localhost:8000"
fi

# Start nginx
nginx -g "daemon off;"
