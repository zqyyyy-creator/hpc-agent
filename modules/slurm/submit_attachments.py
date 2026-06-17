import shlex

from modules.slurm.slurm_assistant import build_resource_recommendation_text, extract_command


def parse_cli_attachment_paths(raw_paths: str):
    lexer = shlex.shlex(raw_paths, posix=True)
    lexer.whitespace += ",，"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [item for item in lexer if item]


def infer_run_command_from_uploaded_files(uploaded_files):
    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".py"):
            return f"python3 {name}"

    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".sh"):
            return f"bash {name}"

    return None


def build_submit_request_with_uploaded_files(question: str, uploaded_files):
    submit_request = question
    inferred_command = None

    if uploaded_files and not extract_command(question):
        inferred_command = infer_run_command_from_uploaded_files(uploaded_files)

    if inferred_command:
        submit_request = f"{question}\n运行命令: {inferred_command}"

    recommendation_text, recommendation_details = build_resource_recommendation_text(
        submit_request,
        uploaded_files,
    )

    if recommendation_text:
        submit_request = f"{submit_request}\n{recommendation_text}"

    return submit_request, inferred_command, recommendation_details
