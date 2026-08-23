# Repo Radio serving API — App Runner target (port 8080).
# Build from the REPO ROOT so fixtures/ and pipeline/ ride along (mock mode +
# the sanctioned pipeline.greptile import):
#   docker build -f server/Dockerfile -t repo-radio-api .
FROM python:3.11-slim

WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ server/
COPY fixtures/ fixtures/
COPY pipeline/ pipeline/
COPY contracts/ contracts/

EXPOSE 8080
CMD ["uvicorn", "app:app", "--app-dir", "server", "--host", "0.0.0.0", "--port", "8080"]
