# The dashboard ships as static assets served by nginx, which also reverse-
# proxies both backends so the browser only ever talks to this origin (ADR-006).
FROM node:22-alpine AS build

WORKDIR /app

# Dependencies first: the lockfile only changes when the app's deps do.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS serve

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
