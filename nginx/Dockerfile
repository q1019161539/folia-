FROM nginx:1.29-alpine
RUN apk add --no-cache apache2-utils
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/entrypoint.sh /entrypoint.sh
COPY web /usr/share/nginx/html
RUN chmod +x /entrypoint.sh && chmod -R a+rX /usr/share/nginx/html
ENTRYPOINT ["/entrypoint.sh"]
