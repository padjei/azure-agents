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

# Copy the AI agent source code into the container
COPY azure_security_agent.py data_architect_agent.py ./

# Default to the security agent; override in docker-compose (or `docker run`) to
# launch the data architect: `command: python data_architect_agent.py`
CMD ["python", "azure_security_agent.py"]
