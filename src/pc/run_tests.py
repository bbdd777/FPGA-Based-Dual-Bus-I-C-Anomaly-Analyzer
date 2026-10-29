"""保存单元测试证据；图形检查、串口流回放另外执行。"""
from pathlib import Path
import hashlib
import io
import json
import unittest


def main():
    root = Path(__file__).resolve().parent
    output = root / "verification"
    output.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    (output / "unit_tests.log").write_text(log.getvalue(), encoding="utf-8")
    print(log.getvalue())
    sources = list(root.glob("*.py"))+list((root/"tests").glob("*.py"))
    report = dict(passed=result.wasSuccessful(), tests=result.testsRun,
                  failures=len(result.failures), errors=len(result.errors),
                  sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (output / "unit_tests.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
