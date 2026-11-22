"""Build the Windows family helper with the .NET Framework compiler bundled with Windows."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(destination, version):
    source = ROOT / "family"
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    command = [
        str(compiler), "/nologo", "/optimize+", "/target:winexe", "/platform:x64",
        "/utf8output", "/codepage:65001", "/win32icon:" + str(ROOT / "assets/icon.ico"),
        "/out:" + str(destination / "TimeParents.Family.exe"),
        "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
        "/reference:System.ServiceProcess.dll", "/reference:System.Web.Extensions.dll",
        *map(str, sorted(source.glob("*.cs"))),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        version_source = Path(tmp) / "ReleaseVersion.cs"
        version_source.write_text(
            "using System.Reflection;\n"
            f'[assembly: AssemblyVersion("{version}.0")]\n'
            f'[assembly: AssemblyInformationalVersion("{version}")]\n',
            encoding="utf-8",
        )
        subprocess.run(command + [str(version_source)], check=True)
    shutil.copy2(source / "Setup.ps1", destination / "Setup.ps1")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    from app_version import VERSION
    build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "family", VERSION)

