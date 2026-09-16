#!/bin/sh
set -eu
htpasswd -bc /etc/nginx/.htpasswd folia "$STUDIO_PASSWORD" >/dev/null
exec nginx -g 'daemon off;'
