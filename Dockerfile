FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Make sure Flask listens on the port and all interfaces
ENV PORT=8080
EXPOSE 8080

# Start the application
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app