FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY equitybot ./equitybot
RUN pip install --no-cache-dir .
COPY config.json ./
RUN useradd -m -u 10001 bot && mkdir /app/data && chown bot:bot /app/data
USER bot
EXPOSE 8080
CMD ["python", "-m", "equitybot", "serve", "--host", "0.0.0.0"]
