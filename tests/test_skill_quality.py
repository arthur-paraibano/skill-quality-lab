from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from activation_suite import summarize, validate_suite
from activation_runner_lib import call_provider, execute_suite
from check_dependencies import check_dependencies
from ecosystem_adapters import audit_ecosystem
from install_skill import install_staged, safe_extract
from package_skill import create_package
from runtime_checks import check_runtime_file
from security_checks import scan_security
from security_scan import scan as run_security_scan
from skill_quality_lib import audit_skill, load_config, parse_frontmatter


def skill_text(name: str = "demo") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: Audit demo skills. Use when a demo needs review.\n"
        "---\n"
        "# Demo\n"
    )


def valid_suite() -> dict:
    categories = (
        ["positive_direct"] * 3 + ["positive_indirect"] * 2 +
        ["negative"] * 3 + ["boundary"] * 2
    )
    cases = []
    for index, category in enumerate(categories):
        expected = True if category.startswith("positive") else False
        if category == "boundary":
            expected = "conditional"
        cases.append({
            "id": f"case-{index}",
            "category": category,
            "prompt": "A realistic prompt",
            "expected_activation": expected,
            "rationale": "Covers the category.",
            "status": "passed",
            "evidence": "Observed the expected workflow.",
        })
    return {
        "schema_version": 1,
        "skill": {"name": "demo", "profile": "portable"},
        "cases": cases,
    }


class FrontmatterTests(unittest.TestCase):
    def test_rejects_invalid_yaml(self) -> None:
        text = '---\nname: demo\ndescription: "unterminated\n---\n# Demo\n'
        with self.assertRaisesRegex(ValueError, "invalid YAML"):
            parse_frontmatter(text)

    def test_rejects_duplicate_keys(self) -> None:
        text = "---\nname: demo\nname: other\ndescription: Use when testing.\n---\n"
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            parse_frontmatter(text)

    def test_audit_rejects_non_string_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "demo"
            root.mkdir()
            (root / "SKILL.md").write_text(
                "---\nname: 12\ndescription: true\n---\n# Demo\n", encoding="utf-8")
            result = audit_skill(root)
            self.assertEqual("not ready", result.verdict)
            self.assertEqual(
                {"invalid-name-type", "invalid-description-type"},
                {finding.code for finding in result.findings},
            )

    def test_audit_rejects_malformed_openai_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "demo"
            (root / "agents").mkdir(parents=True)
            (root / "SKILL.md").write_text(skill_text(), encoding="utf-8")
            (root / "agents" / "openai.yaml").write_text(
                "interface: [unterminated\n", encoding="utf-8")
            result = audit_skill(root, "codex")
            self.assertIn("invalid-openai-metadata", {item.code for item in result.findings})

    def test_audit_rejects_duplicate_openai_yaml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "demo"
            (root / "agents").mkdir(parents=True)
            (root / "SKILL.md").write_text(skill_text(), encoding="utf-8")
            (root / "agents" / "openai.yaml").write_text(
                "interface:\n  display_name: Demo\n  display_name: Other\n",
                encoding="utf-8",
            )
            result = audit_skill(root, "codex")
            self.assertIn("invalid-openai-metadata", {item.code for item in result.findings})


class ConfigurationTests(unittest.TestCase):
    def test_rejects_invalid_unused_override(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            config = root / "config.json"
            config.write_text(
                json.dumps({"severity_overrides": {"unused-code": "fatal"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid severity"):
                load_config(root, config)

    def test_rejects_missing_explicit_config(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                load_config(root, root / "missing.json")


class ActivationSuiteTests(unittest.TestCase):
    def test_valid_complete_suite_is_release_ready(self) -> None:
        suite = valid_suite()
        self.assertEqual([], validate_suite(suite))
        self.assertTrue(summarize(suite)["release_ready"])

    def test_rejects_invalid_skill_identity(self) -> None:
        suite = valid_suite()
        suite["skill"] = {"name": "INVALID NAME", "profile": "nonsense"}
        errors = validate_suite(suite)
        self.assertTrue(any("skill.name" in error for error in errors))
        self.assertTrue(any("skill.profile" in error for error in errors))
        self.assertFalse(summarize(suite)["release_ready"])

    def test_rejects_numeric_boundary_boolean(self) -> None:
        suite = valid_suite()
        boundary = next(case for case in suite["cases"] if case["category"] == "boundary")
        boundary["expected_activation"] = 1
        self.assertTrue(any("expected_activation" in error for error in validate_suite(suite)))

    def test_rejects_non_string_case_fields(self) -> None:
        suite = valid_suite()
        suite["cases"][0]["id"] = 1
        suite["cases"][0]["prompt"] = ["not", "text"]
        suite["cases"][0]["evidence"] = {"not": "text"}
        errors = validate_suite(suite)
        self.assertTrue(any(".id" in error for error in errors))
        self.assertTrue(any(".prompt" in error for error in errors))
        self.assertTrue(any(".evidence" in error for error in errors))


class RuntimeCheckTests(unittest.TestCase):
    def test_builtin_formats_report_syntax_failures(self) -> None:
        cases = {
            "bad.py": "def broken(:\n",
            "bad.json": "{broken",
            "bad.toml": "key = [",
            "bad.yaml": "key: [broken",
        }
        for filename, content in cases.items():
            with self.subTest(filename=filename):
                result = check_runtime_file(Path(filename), content)
                self.assertIsNotNone(result)
                self.assertEqual("failed", result.status)

    def test_missing_external_checker_is_not_assessed(self) -> None:
        with mock.patch("runtime_checks.shutil.which", return_value=None):
            result = check_runtime_file(Path("script.sh"), "echo ok\n")
        self.assertEqual("not_assessed", result.status)


class SecurityTests(unittest.TestCase):
    def test_redacts_detected_secret(self) -> None:
        token = "sk" + "_live_" + "A" * 24
        issues = scan_security(Path("config.txt"), f'api_key = "{token}"\n')
        secret = next(item for item in issues if item.code == "possible-secret")
        self.assertNotIn(token, secret.evidence)
        self.assertIn("redacted", secret.evidence)

    def test_python_ast_detects_delete_api(self) -> None:
        content = "import shutil\nshutil.rmtree('/tmp/example')\n"
        issues = scan_security(Path("cleanup.py"), content)
        self.assertIn("destructive-api-call", {item.code for item in issues})

    def test_reviewed_inline_marker_suppresses_exact_code(self) -> None:
        content = (
            "import shutil\n"
            "shutil.rmtree(path)  # skill-quality: allow destructive-api-call -- validated temp path\n"
        )
        issues = scan_security(Path("cleanup.py"), content)
        self.assertNotIn("destructive-api-call", {item.code for item in issues})
        self.assertIn("reviewed-security-suppression", {item.code for item in issues})

    def test_requested_unavailable_external_scanner_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with mock.patch("security_scan.shutil.which", return_value=None):
                result = run_security_scan(Path(value), external="gitleaks")
            self.assertEqual("ready with warnings", result["verdict"])
            self.assertEqual("not_assessed", result["external"][0]["status"])


class DependencyIsolationTests(unittest.TestCase):
    def test_plan_mode_discovers_requirements_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "scripts").mkdir()
            (root / "scripts" / "requirements.txt").write_text("PyYAML>=6\n", encoding="utf-8")
            result = check_dependencies(root)
            self.assertEqual("not_run", result["status"])
            self.assertEqual("plan", result["mode"])
            self.assertEqual([], result["steps"])

    def test_rejects_unsafe_import_expression(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "invalid import module"):
                check_dependencies(Path(value), create_venv=True,
                                   imports=["json;print('bad')"])


class ActivationRunnerTests(unittest.TestCase):
    def test_command_runner_records_observable_result(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "demo"
            root.mkdir()
            (root / "SKILL.md").write_text(skill_text(), encoding="utf-8")
            command = [sys.executable, "-c",
                       "import json, sys; sys.stdin.read(); "
                       "print(json.dumps({'activation': True, 'evidence': 'loaded'}))"]
            result = execute_suite(valid_suite(), root, "command", command=command, limit=1)
            self.assertEqual("passed", result["cases"][0]["status"])
            self.assertFalse(result["execution"]["classification_only"])

    def test_provider_requires_environment_credential(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                call_provider("openai", "explicit-model", "prompt", 1)

    def test_provider_response_adapters_extract_text(self) -> None:
        fixtures = {
            "openai": {"output": [{"content": [{"type": "output_text", "text": "openai"}]}]},
            "anthropic": {"content": [{"type": "text", "text": "anthropic"}]},
            "gemini": {"steps": [{"type": "model_output",
                                     "content": [{"type": "text", "text": "gemini"}]}]},
        }
        environments = {
            "openai": {"OPENAI_API_KEY": "test"},
            "anthropic": {"ANTHROPIC_API_KEY": "test"},
            "gemini": {"GEMINI_API_KEY": "test"},
        }
        for provider, response in fixtures.items():
            with self.subTest(provider=provider):
                with mock.patch.dict("os.environ", environments[provider], clear=True), \
                     mock.patch("activation_runner_lib._request_json", return_value=response):
                    self.assertEqual(provider, call_provider(provider, "model", "prompt", 1))


class EcosystemAdapterTests(unittest.TestCase):
    def test_valid_openapi_document(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "openapi.yaml").write_text(
                "openapi: 3.1.0\ninfo:\n  title: Demo\n  version: 1.0.0\n"
                "paths:\n  /items:\n    get:\n      operationId: listItems\n",
                encoding="utf-8",
            )
            self.assertEqual("ready", audit_ecosystem(root, "openapi")["verdict"])

    def test_mcp_rejects_ambiguous_transport(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "mcp.json").write_text(json.dumps({
                "mcpServers": {"demo": {"command": "python", "url": "https://example.test"}}
            }), encoding="utf-8")
            result = audit_ecosystem(root, "mcp")
            self.assertIn("ambiguous-mcp-transport", {item["code"] for item in result["findings"]})

    def test_langchain_detects_declared_and_imported_framework(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "requirements.txt").write_text("langchain>=1\n", encoding="utf-8")
            (root / "app.py").write_text("import langchain\n", encoding="utf-8")
            self.assertEqual("ready", audit_ecosystem(root, "langchain")["verdict"])

    def test_langchain_detects_javascript_usage(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"@langchain/core": "^1.0.0"}}), encoding="utf-8")
            (root / "app.js").write_text(
                'import { AIMessage } from "@langchain/core/messages";\n', encoding="utf-8")
            runtime_result = SimpleNamespace(status="passed", language="javascript", evidence="valid")
            with mock.patch("ecosystem_adapters.check_runtime_file", return_value=runtime_result):
                self.assertEqual("ready", audit_ecosystem(root, "langchain")["verdict"])

    def test_langchain_rejects_invalid_javascript(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"@langchain/core": "^1.0.0"}}), encoding="utf-8")
            (root / "app.js").write_text(
                'import "@langchain/core";\nconst = ;\n', encoding="utf-8")
            runtime_result = SimpleNamespace(
                status="failed", language="javascript", evidence="SyntaxError")
            with mock.patch("ecosystem_adapters.check_runtime_file", return_value=runtime_result):
                result = audit_ecosystem(root, "langchain")
            self.assertIn("invalid-framework-source", {item["code"] for item in result["findings"]})

    def test_semantic_kernel_detects_dotnet_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "app.csproj").write_text(
                '<Project><ItemGroup><PackageReference Include="Microsoft.SemanticKernel" /></ItemGroup></Project>',
                encoding="utf-8",
            )
            result = audit_ecosystem(root, "semantic-kernel")
            self.assertEqual("ready", result["verdict"])


class PackagingAndInstallTests(unittest.TestCase):
    def test_packages_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value)
            root = temp / "demo"
            root.mkdir()
            (root / "SKILL.md").write_text(skill_text(), encoding="utf-8")
            first, second = temp / "first.zip", temp / "second.zip"
            self.assertEqual(create_package(root, first), create_package(root, second))
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_safe_extract_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value)
            archive = temp / "escape.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../outside.txt", "bad")
            with self.assertRaisesRegex(ValueError, "escapes destination"):
                safe_extract(archive, temp / "out")

    def test_safe_extract_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value)
            archive = temp / "link.zip"
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr(info, "target")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                safe_extract(archive, temp / "out")

    def test_safe_extract_rejects_excessive_expanded_size(self) -> None:
        member = SimpleNamespace(file_size=256 * 1024 * 1024 + 1)

        class FakeArchive:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def infolist(self):
                return [member]

        with mock.patch("install_skill.zipfile.ZipFile", return_value=FakeArchive()):
            with self.assertRaisesRegex(ValueError, "expands beyond"):
                safe_extract(Path("unused.zip"), Path("unused"))

    def test_replace_restores_previous_installation_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value)
            staging = temp / "staging"
            destination = temp / "skills"
            installed = destination / "demo"
            staging.mkdir()
            installed.mkdir(parents=True)
            (staging / "version.txt").write_text("new", encoding="utf-8")
            (installed / "version.txt").write_text("old", encoding="utf-8")
            with mock.patch.object(Path, "replace", side_effect=OSError("simulated failure")):
                with self.assertRaisesRegex(OSError, "simulated failure"):
                    install_staged(staging, destination, "demo", replace=True)
            self.assertEqual("old", (installed / "version.txt").read_text(encoding="utf-8"))
            self.assertFalse(any(destination.glob(".skill-quality-install-*")))


class ComparisonTests(unittest.TestCase):
    def test_severity_regression_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value)
            reports = []
            for folder, severity, score, verdict in (
                ("before", "warning", 93, "ready with warnings"),
                ("after", "error", 80, "not ready"),
            ):
                target = temp / folder
                report = {
                    "schema_version": 1,
                    "summary": {
                        "target": str(target), "profile": "portable", "name": "demo",
                        "score": score, "verdict": verdict, "counts": {},
                    },
                    "findings": [{
                        "severity": severity, "code": "same-finding", "message": "message",
                        "evidence": "same evidence", "remediation": "fix it",
                        "path": str(target / "SKILL.md"), "line": 1,
                    }],
                }
                path = temp / f"{folder}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                reports.append(path)
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / "compare_audits.py"),
                 str(reports[0]), str(reports[1]), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(1, completed.returncode)
            self.assertIn('"severity_changed"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
