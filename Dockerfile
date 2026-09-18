# AgroOptimize backend -- FastAPI + NSGA-II (pymoo) + Mamdani fuzzy (scikit-fuzzy)
FROM python:3.11-slim

WORKDIR /app

# System deps for numpy/pandas/matplotlib wheels build cleanly on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY run_demo.py ./run_demo.py

# results/ is gitignored (saved optimisation runs) but must exist for
# results_store to write into -- Step 10's Fly.io volume mounts over this.
RUN mkdir -p /app/results

EXPOSE 8000

# --proxy-headers: Fly.io terminates TLS in front of this container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
