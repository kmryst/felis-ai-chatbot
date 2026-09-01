FROM python:3.12-slim
WORKDIR /app
COPY server.py /app/server.py
RUN useradd -m -u 10001 appuser
USER appuser
EXPOSE 8080
CMD ["python", "/app/server.py"]
