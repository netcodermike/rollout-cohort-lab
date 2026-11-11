"""Run the recorded API scenarios against fresh local services or Docker Compose."""

from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "examples.json").read_text(encoding="utf-8"))


def free_ports():
    with socket.socket() as first, socket.socket() as second:
        for listener in (first, second):
            listener.bind(("127.0.0.1", 0))
        return first.getsockname()[1], second.getsockname()[1]


def request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    try:
        with urlopen(Request(url, data, {"Content-Type": "application/json"}), timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def wait_ready(base, process=None):
    for _ in range(150):
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}")
        try:
            if request(base + "/health")[0] == 200:
                return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Service did not start at {base}")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start(stack, role, port, env, temp):
    name, path, language = SPEC[role]
    directory = ROOT / "services" / name
    if language == "C#":
        build = subprocess.run(["dotnet", "build", "Service.csproj", "--nologo"], cwd=directory,
                               text=True, capture_output=True)
        if build.returncode:
            raise RuntimeError(build.stdout + build.stderr)
        command = ["dotnet", "bin/Debug/net8.0/Service.dll"]
    elif language == "JavaScript":
        command = ["node", "server.mjs"]
    else:
        command = [sys.executable, "server.py"]
    service_env = dict(os.environ, HOST="127.0.0.1", PORT=str(port), OPERATION_PATH=path, **env)
    with (temp / f"{name}.log").open("wb") as log:
        process = subprocess.Popen(command, cwd=directory, env=service_env, stdout=log, stderr=log)
    stack.callback(stop, process)
    base = f"http://127.0.0.1:{port}"
    wait_ready(base, process)
    return base


def check(base):
    gateway, path, _ = SPEC["gateway"]
    print(f"{gateway}  ->  {SPEC['worker'][0]}    |    POST {path}")
    endpoint = base + path
    for label, payload, expected_status, expected in SPEC["cases"]:
        status, body = request(endpoint, payload)
        assert status == expected_status, (label, status, body)
        actual = {key: body[key] for key in expected}
        assert actual == expected, (label, actual, expected)
        print(f"HTTP {status}  {label}")
        for key, value in actual.items():
            print(f"  {key} = {json.dumps(value, ensure_ascii=True, separators=(', ', ': '))}")
    status, _ = request(endpoint, {})
    assert status == 400, ("empty input", status)
    if SPEC["slug"] == "inventory-reservation-mesh":
        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(
                lambda index: request(endpoint, {"orderId": f"race-{index}", "sku": "MUG", "quantity": 4})[0],
                (1, 2)))
        assert sorted(results) == [200, 409], results
        print("PASS  Concurrent holds cannot oversell")
    print("PASS  End-to-end checks")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--base-url":
        base = sys.argv[2].rstrip("/")
        wait_ready(base)
        check(base)
        return
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python demo.py [--base-url http://127.0.0.1:8080]")
    with TemporaryDirectory(prefix="microservice-demo-") as directory:
        temp = Path(directory)
        try:
            with ExitStack() as stack:
                api_port, worker_port = free_ports()
                worker = start(stack, "worker", worker_port, {"DB_PATH": str(temp / "data.sqlite3")}, temp)
                base = start(stack, "gateway", api_port, {"UPSTREAM_URL": worker + SPEC["worker"][1]}, temp)
                check(base)
        except Exception:
            for log in temp.glob("*.log"):
                print(log.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
            raise


if __name__ == "__main__":
    main()
