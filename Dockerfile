# Python 3.12 pinned: keeps pypdf/onnxruntime wheels boring; 3.13 removed cgi
# (our multipart parser is hand-rolled stdlib anyway).
FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir "openpyxl>=3.1" pypdf python-docx fastembed

# bake the retrieval model into the image: runtime has zero network egress
# and cold start never depends on a model host being up
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY trustops/ trustops/
COPY site/ site/
COPY data/ data/

ENV TRUSTOPS_DATA=/data
CMD ["python", "-m", "trustops.server.app", "--host", "0.0.0.0"]
