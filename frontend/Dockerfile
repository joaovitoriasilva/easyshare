# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve stage: nginxinc/nginx-unprivileged runs nginx as a non-root user by
# default (listens on 8080, uses /tmp for its pid/cache instead of root-owned
# /var/run and /var/cache), so no extra permission setup is needed here.
FROM nginxinc/nginx-unprivileged:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080

# wget is provided by busybox in the alpine base image, no install needed.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8080/ || exit 1
