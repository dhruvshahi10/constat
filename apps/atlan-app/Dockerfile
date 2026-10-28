# Constat as an Atlan App Framework app. The base image is Atlan's app runtime
# (docs: /product/capabilities/build-apps/partner-with-us/how-tos/package-app-with-docker).
# Build multi-platform and push to the tenant's Harbor registry:
#   docker buildx build --platform linux/amd64,linux/arm64 -f apps/atlan-app/Dockerfile \
#     -t <harbor>/constat/app:1.0.0 --push .
# Local check: docker run -e ATLAN_WORKFLOW_HOST=localhost -e ATLAN_WORKFLOW_PORT=7233 -p 8000:8000 <image>
ARG BASE=ghcr.io/atlanhq/app-runtime-base:latest
FROM ${BASE}
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install atlan-application-sdk pyatlan
COPY constat ./constat
COPY apps/atlan-app ./apps/atlan-app
COPY evals/golden ./evals/golden
ENV CLAIM_STORE=atlan CONSTAT_TMP=/tmp/constat-app
EXPOSE 8000
CMD ["python", "apps/atlan-app/app.py", "--help"]
