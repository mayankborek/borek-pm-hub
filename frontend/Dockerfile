# Stage 1: build the static bundle with Vite.
FROM node:22-alpine AS build

WORKDIR /app

# Override if registry.npmjs.org is unreachable from your network
ARG NPM_REGISTRY=https://registry.npmjs.org/
COPY package.json package-lock.json ./
RUN npm ci --registry="${NPM_REGISTRY}"

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
# Same-origin by default: nginx proxies /api to the API container.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# Stage 2: serve the bundle with nginx and proxy /api to the backend.
FROM nginx:1.30-alpine

# Pick up Alpine security fixes published since the base image was built.
RUN apk upgrade --no-cache

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.inc /etc/nginx/conf.d/security-headers.inc
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO /dev/null http://localhost/ || exit 1
