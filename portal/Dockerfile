# 사내 앱 포탈 소개 페이지 (정적 HTML)
# 빌드: docker build -t app-portal .   실행: docker run -p 8080:80 app-portal
FROM nginx:1.27-alpine
COPY index.html /usr/share/nginx/html/index.html
EXPOSE 80
