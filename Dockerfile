# Python 3.12 pinned: keeps pypdf/onnxruntime wheels boring; 3.13 removed cgi
# (our multipart parser is hand-rolled stdlib anyway).
FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir "openpyxl>=3.1" pypdf python-docx

COPY trustops/ trustops/
COPY site/ site/
COPY data/ data/

ENV TRUSTOPS_DATA=/data
CMD ["python", "-m", "trustops.server.app", "--host", "0.0.0.0"]
