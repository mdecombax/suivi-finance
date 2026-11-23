# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose the port Cloud Run will use
EXPOSE 8080

# Run the application
# 1 process + 8 threads : les appels API d'une page partent en parallèle (au lieu de faire
# la queue derrière 2 workers synchrones) et partagent les caches de prix en mémoire.
# L'essentiel du travail attend le réseau (JustETF / Yahoo / Firestore), donc les threads suffisent.
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --worker-class gthread --timeout 120 app:app
