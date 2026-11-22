"""Exercise the Windows child-mode accounting and transport without installing any policy."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == "win32", "Requires the Windows .NET Framework")
class FamilyTests(unittest.TestCase):
    def test_family_scenarios(self):
        root = Path(__file__).resolve().parents[1]
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "Checks.exe"
            subprocess.run([
                str(compiler), "/nologo", "/platform:x64", "/codepage:65001", "/main:FamilyChecks",
                "/out:" + str(exe), "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
                "/reference:System.Web.Extensions.dll", "/reference:System.ServiceProcess.dll",
                *map(str, sorted((root / "family").glob("*.cs"))), str(root / "tests/FamilyChecks.cs"),
            ], check=True)
            subprocess.run([str(exe)], timeout=25, check=True)

