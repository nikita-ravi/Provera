FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api.py .
COPY src/ ./src/

# Copy data files
COPY data/processed/ ./data/processed/

# Expose port
EXPOSE 8000

# Start command
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
