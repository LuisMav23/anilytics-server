# Use Python base image
FROM python:3.9

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application files
COPY . .

# Expose port 5000
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
