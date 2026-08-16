# Python 3.12 pinned: keeps pypdf/onnxruntime wheels boring; 3.13 removed cgi
# (our multipart parser is hand-rolled stdlib anyway).
FROM python:3.12-slim
WORKDIR /app

# One dependency list, exactly pinned, shared with local dev — an image that
# resolves different versions than the venv the evals ran against is an image
# nobody has actually tested.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bake the retrieval model into the image: runtime has zero network egress
# and cold start never depends on a model host being up
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY trustops/ trustops/
COPY site/ site/
COPY data/ data/

ENV TRUSTOPS_DATA=/data
EXPOSE 8790
CMD ["python", "-m", "trustops.server.app", "--host", "0.0.0.0"]
