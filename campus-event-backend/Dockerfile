FROM python:3.12-slim
WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY campus-event-backend/app ./app
COPY campus-event-backend/guidelines ./guidelines

EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]