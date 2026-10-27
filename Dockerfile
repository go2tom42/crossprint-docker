FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

# Install the project's declared dependencies.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Include the application, policy files, and bundled printer presets.
COPY . .

EXPOSE 5000

# One worker is intentional: Crossprint serializes conversions itself.
# Two threads let page loads and health checks respond during conversion.
CMD ["sh", "-c", "exec gunicorn --chdir web app:app --workers 1 --threads 2 --timeout 600 --bind 0.0.0.0:${PORT}"]
