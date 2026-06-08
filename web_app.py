from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.error_diagnoser import ErrorDiagnoser
from modules.router import detect_intent


app = FastAPI(title="HPC Agent Web")

documents, sources = load_documents()
diagnoser = ErrorDiagnoser()

app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    question = request.message.strip()

    if not question:
        return {
            "intent": "empty",
            "answer": "请输入问题。"
        }

    intent = detect_intent(question)

    if intent == "generate_sbatch":
        answer = generate_sbatch_script(question)

    elif intent == "suggest_params":
        answer = suggest_slurm_parameters(question)

    elif intent == "diagnose_error":
        results = diagnoser.diagnose(question)
        answer = diagnoser.format_results(results)

    else:
        retrieved_docs = retrieve(question, documents, sources)
        answer = ask_llm(question, retrieved_docs)

    return {
        "intent": intent,
        "answer": answer
    }