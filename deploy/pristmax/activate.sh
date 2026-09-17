set -eu
backup=/root/pristmax-migration-20260917
cp -a /etc/nginx/conf.d/ashou.conf "$backup/ashou.conf.before"
mv /etc/nginx/conf.d/ashou.conf "$backup/ashou.conf.disabled"
cp "$backup/pristmax.conf" /etc/nginx/conf.d/pristmax.conf
chmod -R a+rX /var/www/pristmax
if command -v restorecon >/dev/null; then restorecon -R /var/www/pristmax; fi
if nginx -t; then
 systemctl reload nginx
else
 rm /etc/nginx/conf.d/pristmax.conf
 cp "$backup/ashou.conf.before" /etc/nginx/conf.d/ashou.conf
 systemctl start ashou
 exit 1
fi
curl -fsS http://127.0.0.1/ -H 'Host: 8.133.180.156' | head -c 200
