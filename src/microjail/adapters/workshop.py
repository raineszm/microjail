import subprocess


def init(name: str, sdks: list[str] | None = None):
    if sdks is None:
        sdks = []
    sdks = sdks.copy()
    sdks.append("direnv")
    subprocess.run(["workshop", "init", name, "--sdks", ",".join(sdks)], check=True)
