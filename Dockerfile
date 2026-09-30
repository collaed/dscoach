FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir psycopg2-binary argon2-cffi
COPY lib/ /app/lib/
COPY src/ /app/src/
COPY static/ /app/static/
ENV PYTHONPATH=/app/lib:/app/src
EXPOSE 8000
CMD ["python", "-u", "src/server.py"]
