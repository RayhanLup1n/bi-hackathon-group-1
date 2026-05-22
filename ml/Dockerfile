# ========================================
# Dockerfile - R.A.D.A.R Pangan ML Model
# Inference server for price prediction
#
# TEMPLATE: ML teammate should customize this
#
# Contract:
#   - Expose port 8001
#   - POST /predict -> price predictions
#   - GET  /health  -> {"status": "ok"}
# ========================================

FROM python:3.11-slim

WORKDIR /app

# Install ML dependencies
# TODO: ML teammate - update requirements as needed
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy model files and inference code
COPY . .

EXPOSE 8001

# TODO: ML teammate - update entrypoint to match your server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
