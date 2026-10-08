FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
# 改成淘宝的镜像源（新域名）
RUN npm config set registry https://registry.npmmirror.com
RUN npm install
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
