FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY public ./public
RUN useradd --create-home game && mkdir /data && chown game /data
USER game
ENV PORT=8000 GAME_DB=/data/game.sqlite3
EXPOSE 8000
CMD ["python", "server.py"]
