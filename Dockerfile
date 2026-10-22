FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /app

# Build tesserocr against the Linux OCR libraries; install CPU-only PyTorch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config libtesseract-dev libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r requirements.txt

COPY . .
# Bake public models and static assets into the image, never local user data.
RUN DJANGO_DEBUG=True python scripts/cache_embedding_model.py \
    && DJANGO_DEBUG=True python scripts/setup_ocr.py \
    && DJANGO_DEBUG=True python manage.py collectstatic --noinput

ENV DJANGO_DEBUG=False
EXPOSE 10000
CMD ["sh", "scripts/start_render.sh"]
