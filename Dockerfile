FROM python:3.11-slim

WORKDIR /app

# Dépendances système pour les parsers de documents + OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Note: Vision LLM (Ministral 3) est utilisé via Ollama pour l'analyse d'images

# Dépendances Python
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY app/ .

# Créer les dossiers nécessaires
RUN mkdir -p /data /app/index /app/static /app/templates

# Rendre le script d'entrée exécutable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Utiliser l'entrypoint pour la détection automatique d'Ollama
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
