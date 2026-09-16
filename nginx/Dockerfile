FROM node:22-alpine AS effects-builder
WORKDIR /effects
COPY effects/package.json ./
RUN npm install --no-audit --no-fund
COPY effects/ ./
RUN npm run build

FROM papersman/folia-web@sha256:27f36fe454eaa2af0ac8e53e7d2cb9694e6bad3a3ed1ad711b8e64086c0bf719 AS folia-static

FROM nginx:1.29-alpine
RUN apk add --no-cache apache2-utils
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/entrypoint.sh /entrypoint.sh
COPY web /usr/share/nginx/html
COPY --from=effects-builder /effects/dist /usr/share/nginx/html/effects
COPY --from=folia-static /usr/share/nginx/html /usr/share/nginx/folia-native
RUN chmod +x /entrypoint.sh && chmod -R a+rX /usr/share/nginx/html
ENTRYPOINT ["/entrypoint.sh"]
