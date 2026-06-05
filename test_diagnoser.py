from modules.error_diagnoser import ErrorDiagnoser


diagnoser = ErrorDiagnoser()

test_files = [
    "data/errors/oom.log",
    "data/errors/permission.log",
    "data/errors/module.log"
]

for file in test_files:
    print("=" * 60)
    print(f"测试文件: {file}")

    results = diagnoser.diagnose_file(file)

    print(diagnoser.format_results(results))
