FROM node:22-slim

WORKDIR /app

# package-lock.json どおりのバージョンを入れる
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]