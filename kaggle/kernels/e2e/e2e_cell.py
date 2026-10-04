E2E_ARGS = ["--mode", "dense", "--expand-refs", "--synonyms", "--transliterate", "--resolve-refs", "--boost-in-force", "--max-parts-per-section", "2"]
MODELS = ["qwen2.5:7b", "llama3.1:8b"]
LABEL = "e2e-qwen25-7b"
# bd-legal-rag — end-to-end answer evaluation on a Kaggle GPU with local Ollama models.
# Started by scripts/finish.py, which prepends E2E_ARGS (the retrieval configuration and labels).
# Inputs: the "bdrag-bundle" dataset (code + chunks) and the output of the "bdrag-build-index"
# notebook (the index). Settings: GPU T4, Internet ON. Output: results/e2e-*.json/.answers.json/.txt
# A 7B model answers at tens of tokens per second on a T4; on a laptop CPU one answer can take minutes.
import glob
import gzip
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

E2E_ARGS = globals().get("E2E_ARGS", [])
MODELS = globals().get("MODELS", ["qwen2.5:7b", "llama3.1:8b"])
LABEL = globals().get("LABEL", "e2e-qwen25-7b")


def sh(cmd, **kw):
    print("$", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)


# code
# the bundle's code zip first: the index notebook's output also holds an (older) copy of the code
for z in glob.glob("/kaggle/input/**/bdrag-code.zip", recursive=True):
    zipfile.ZipFile(z).extractall("/kaggle/working/_code")
hits = glob.glob("/kaggle/working/_code/**/scripts/eval_e2e.py", recursive=True) or \
    glob.glob("/kaggle/input/**/bdrag-code/**/scripts/eval_e2e.py", recursive=True)
assert hits, "attach the bdrag-bundle dataset"
assert os.path.exists(os.path.join(os.path.dirname(os.path.dirname(hits[0])), "data", "eval", "eval.jsonl")), \
    "the code bundle has no data/eval: re-run scripts/make_kaggle_bundle.py"
src = os.path.dirname(os.path.dirname(hits[0]))
shutil.copytree(src, "/kaggle/working/bdrag", dirs_exist_ok=True)
os.chdir("/kaggle/working/bdrag")

# chunks (Kaggle may have unpacked the .gz parts)
parts = glob.glob("/kaggle/input/**/chunks-part*.jsonl.gz", recursive=True) or \
    glob.glob("/kaggle/input/**/chunks-part*.jsonl", recursive=True)
parts.sort(key=lambda p: int(p.rsplit("part", 1)[1].split(".")[0]))
os.makedirs("data/processed", exist_ok=True)
with open("data/processed/chunks.jsonl", "wb") as out:
    for p in parts:
        with (gzip.open(p, "rb") if p.endswith(".gz") else open(p, "rb")) as f:
            shutil.copyfileobj(f, out)

# index, from the build notebook's output (a folder, or bdrag_index.zip)
vec = [p for p in glob.glob("/kaggle/input/**/vectors.npy", recursive=True) if "/_" not in p]
if not vec:
    for z in glob.glob("/kaggle/input/**/bdrag_index.zip", recursive=True):
        zipfile.ZipFile(z).extractall("/kaggle/working/_index")
    vec = glob.glob("/kaggle/working/_index/**/vectors.npy", recursive=True)
assert vec, "attach the bdrag-build-index notebook output"
INDEX = os.path.dirname(vec[0])
print("index:", INDEX, os.listdir(INDEX))

sh([sys.executable, "-m", "pip", "install", "-q", "sentence-transformers"])

# Ollama on the GPU
sh("apt-get install -y -qq zstd > /dev/null 2>&1 || true")
sh("curl -fsSL https://ollama.com/install.sh | sh")
env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_KEEP_ALIVE": "30m"}
server = subprocess.Popen(["ollama", "serve"], env=env, stdout=open("/kaggle/working/ollama.log", "w"),  # noqa: SIM115
                          stderr=subprocess.STDOUT)
for _ in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        break
    except OSError:
        time.sleep(2)
for m in MODELS:
    sh(["ollama", "pull", m], env=env)

os.environ.update({"RAG_LLM_TIMEOUT": "600", "OLLAMA_NUM_CTX": "8192", "OLLAMA_HOST": "http://127.0.0.1:11434"})
os.makedirs("/kaggle/working/results", exist_ok=True)
t0 = time.time()
with open(f"/kaggle/working/results/{LABEL}.txt", "w", encoding="utf-8") as log:
    p = subprocess.run([sys.executable, "scripts/eval_e2e.py", "--eval", "data/eval/eval.jsonl",
                        "--index", INDEX, "--provider", "ollama", "--llm-model", MODELS[0],
                        "--judge-provider", "ollama", "--judge-model", MODELS[1],
                        "--label", LABEL, "--results", "/kaggle/working/results", *E2E_ARGS],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write(p.stdout)
print(p.stdout[-6000:])
print(f"eval_e2e exit {p.returncode} after {(time.time() - t0) / 60:.0f} min")
server.terminate()
