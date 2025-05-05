FROM python:3.9-slim

WORKDIR /app

COPY app.py .
# COPY index.html .   # (only if you actually use it)
# COPY any other needed files

RUN pip install Flask==2.2.5

EXPOSE 5000

CMD ["python", "app.py"]

