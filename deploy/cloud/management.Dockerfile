FROM node:22-alpine AS build
WORKDIR /app
COPY manage_front/package.json manage_front/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY manage_front/ ./
RUN npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
