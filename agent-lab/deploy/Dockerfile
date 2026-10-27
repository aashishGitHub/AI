FROM python:3.14-slim

WORKDIR /app
COPY pyproject.toml ./
COPY agent ./agent
COPY mcp_server ./mcp_server
COPY orchestrator ./orchestrator
COPY mesh ./mesh
COPY evals ./evals
COPY memory ./memory
COPY promptreg ./promptreg
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 mesh && mkdir /data && chown mesh /data
USER mesh
VOLUME /data
ENTRYPOINT ["python", "-m", "mesh"]
