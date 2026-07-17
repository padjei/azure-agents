# Use a lightweight, stable official Python image
FROM python:3.11-slim

# Set system environment variables to optimize Python performance inside Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Establish a secure working directory inside the container
WORKDIR /app

# Copy only the dependency file first to maximize Docker caching efficiency
COPY requirements.txt .

# Install dependencies (no-cache reduces build size)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the actual AI agent source code into the container
COPY azure_security_agent.py .

# Run the script interactively when the container fires up
CMD ["python", "azure_security_agent.py"]
