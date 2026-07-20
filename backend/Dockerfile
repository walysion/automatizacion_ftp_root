# Usamos una versión ligera de Python
FROM python:3.11-slim

# Evita que Python genere archivos .pyc y fuerza a que los logs salgan directo a consola
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Instalamos Chromium desde los repositorios oficiales de Debian (que no están bloqueados)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar el directorio de trabajo
WORKDIR /app

# 3. Copiar e instalar los requerimientos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. El comando para iniciar la aplicación Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]