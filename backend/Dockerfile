# Usamos una versión ligera de Python
FROM python:3.11-slim

# Evita que Python genere archivos .pyc y fuerza a que los logs salgan directo a consola
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 1. Configuramos la Zona Horaria base del contenedor
ENV TZ=America/Santiago

# 2. Instalamos Chromium, herramientas necesarias y el paquete de zonas horarias (tzdata)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    curl \
    libpq-dev \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 3. Configurar el directorio de trabajo
WORKDIR /app

# 4. Copiar e instalar los requerimientos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. El comando para iniciar la aplicación Flask
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]