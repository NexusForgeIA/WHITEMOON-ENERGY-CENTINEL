FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PORT=8080
CMD ["python3", "server.py", "--host", "0.0.0.0"]
