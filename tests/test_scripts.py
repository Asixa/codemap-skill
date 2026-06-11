"""Golden / behavior tests for the codemap scripts. Stdlib only — run with:

    python -m unittest discover -s tests -v

Each test drives the real CLI (subprocess) against a throwaway fixture, so it tests
exactly what an agent or CI runs.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "assets", "template.html"))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "modules.json")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def save(self, state):
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)

    def load(self):
        with open(self.state, encoding="utf-8") as f:
            return json.load(f)


class TestScan(Base):
    def _project(self):
        write(os.path.join(self.d, "src/a.py"), "x = 1\ny = 2\n")
        write(os.path.join(self.d, "src/b.py"), "def f():\n    return 3\n")
        self.save({"meta": {}, "bands": [], "spine": [], "modules": [
            {"id": "m_a", "label": "A", "band": "b", "coupling": "low", "deps": [], "paths": ["src/a.py"]},
            {"id": "m_b", "label": "B", "band": "b", "coupling": "low", "deps": [], "paths": ["src/b.py"]},
            {"id": "m_empty", "label": "E", "band": "b", "coupling": "low", "deps": [], "paths": ["nope/**/*.py"]},
        ]})

    def test_loc_hash_empty(self):
        self._project()
        r = run("scan.py", "--root", self.d, "--state", self.state, "--write")
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads(r.stdout)
        self.assertIn("m_empty", rep["empty"])
        self.assertIn("m_a", rep["unaudited"])
        st = {m["id"]: m for m in self.load()["modules"]}
        self.assertEqual(st["m_a"]["loc"], 2)
        self.assertTrue(st["m_a"]["contentHash"])
        # hash is content-stable: re-scan gives the same hash
        run("scan.py", "--root", self.d, "--state", self.state, "--write")
        self.assertEqual(self.load()["modules"][0]["contentHash"], st["m_a"]["contentHash"])

    def test_stale_detection(self):
        self._project()
        run("scan.py", "--root", self.d, "--state", self.state, "--write")
        st = self.load()
        for m in st["modules"]:
            if m["id"] == "m_a":
                m["auditedHash"] = m["contentHash"]
                m["score"] = 80
        self.save(st)
        # unchanged → fresh
        rep = json.loads(run("scan.py", "--root", self.d, "--state", self.state).stdout)
        self.assertIn("m_a", rep["fresh"])
        # change the file → stale
        write(os.path.join(self.d, "src/a.py"), "x = 1\ny = 2\nz = 3\n")
        rep = json.loads(run("scan.py", "--root", self.d, "--state", self.state).stdout)
        self.assertIn("m_a", rep["stale"])

    def test_git_changed_modules(self):
        if shutil.which("git") is None:
            self.skipTest("git not available")
        self._project()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        g = lambda *a: subprocess.run(["git", "-C", self.d, *a], capture_output=True, text=True, env=env)
        g("init", "-q")
        g("add", "-A"); g("commit", "-qm", "init")
        head = g("rev-parse", "HEAD").stdout.strip()
        st = self.load(); st["meta"]["rev"] = head; self.save(st)
        write(os.path.join(self.d, "src/b.py"), "def f():\n    return 99\n")
        g("add", "-A"); g("commit", "-qm", "change b")
        rep = json.loads(run("scan.py", "--root", self.d, "--state", self.state).stdout)
        self.assertIsNotNone(rep["git"])
        self.assertIn("m_b", rep["git"]["changed_modules"])
        self.assertNotIn("m_a", rep["git"]["changed_modules"])


class TestQuery(Base):
    def _state(self):
        self.save({"meta": {}, "modules": [
            {"id": "good", "label": "G", "band": "x", "coupling": "low", "score": 92, "grade": "A", "tags": ["clean"], "findings": [], "paths": []},
            {"id": "df", "label": "D", "band": "x", "coupling": "low", "score": 70, "grade": "C", "tags": ["dual-format"],
             "findings": [{"sev": "MED", "loc": "a:1", "text": "x"}], "paths": []},
            {"id": "bad", "label": "B", "band": "x", "coupling": "low", "score": 48, "grade": "D", "tags": ["stub"],
             "findings": [{"sev": "HIGH", "loc": "b:2", "text": "y"}], "paths": []},
            {"id": "new", "label": "N", "band": "x", "coupling": "low", "paths": []},
        ]})

    def test_max_grade(self):
        self._state()
        ids = run("query.py", "--state", self.state, "--max-grade", "C", "--format", "ids").stdout.split()
        self.assertCountEqual(ids, ["df", "bad"])

    def test_tag(self):
        self._state()
        ids = run("query.py", "--state", self.state, "--tag", "dual-format", "--format", "ids").stdout.split()
        self.assertEqual(ids, ["df"])

    def test_sev(self):
        self._state()
        ids = run("query.py", "--state", self.state, "--sev", "HIGH", "--format", "ids").stdout.split()
        self.assertEqual(ids, ["bad"])

    def test_needs_audit(self):
        self._state()
        ids = run("query.py", "--state", self.state, "--needs-audit", "--format", "ids").stdout.split()
        self.assertIn("new", ids)


class TestApplyAudit(Base):
    def _state(self):
        self.save({"meta": {}, "modules": [
            {"id": "m1", "label": "M", "band": "x", "coupling": "low", "contentHash": "abc", "paths": []},
        ]})

    def apply(self, result):
        return run("apply_audit.py", "--state", self.state, "--id", "m1", "--json", json.dumps(result))

    def test_valid(self):
        self._state()
        r = self.apply({"score": 70, "grade": "C", "tags": ["legacy"],
                        "findings": [{"sev": "LOW", "loc": "f:1", "text": "t"}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        m = self.load()["modules"][0]
        self.assertEqual(m["score"], 70)
        self.assertEqual(m["auditedHash"], "abc")

    def test_grade_score_mismatch(self):
        self._state()
        r = self.apply({"score": 70, "grade": "A", "tags": ["clean"], "findings": []})
        self.assertNotEqual(r.returncode, 0)

    def test_unknown_tag(self):
        self._state()
        r = self.apply({"score": 70, "grade": "C", "tags": ["not-a-real-tag"],
                        "findings": [{"sev": "LOW", "loc": "f:1", "text": "t"}]})
        self.assertNotEqual(r.returncode, 0)

    def test_clean_with_bad_tag(self):
        self._state()
        r = self.apply({"score": 90, "grade": "A", "tags": ["clean", "legacy"],
                        "findings": [{"sev": "LOW", "loc": "f:1", "text": "t"}]})
        self.assertNotEqual(r.returncode, 0)

    def test_clean_low_score(self):
        self._state()
        r = self.apply({"score": 50, "grade": "D", "tags": ["clean"], "findings": []})
        self.assertNotEqual(r.returncode, 0)

    def test_finding_missing_text(self):
        self._state()
        r = self.apply({"score": 70, "grade": "C", "tags": ["legacy"],
                        "findings": [{"sev": "LOW", "loc": "f:1", "text": ""}]})
        self.assertNotEqual(r.returncode, 0)

    def test_bad_tag_without_findings(self):
        self._state()
        r = self.apply({"score": 70, "grade": "C", "tags": ["legacy"], "findings": []})
        self.assertNotEqual(r.returncode, 0)


class TestRender(Base):
    def _render(self, state):
        self.save(state)
        out_html = os.path.join(self.d, "out.html")
        out_md = os.path.join(self.d, "out.md")
        r = run("render.py", "--state", self.state, "--template", TEMPLATE,
                "--out-html", out_html, "--out-md", out_md)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out_html, encoding="utf-8") as f:
            html = f.read()
        with open(out_md, encoding="utf-8") as f:
            md = f.read()
        return html, md

    def test_basic(self):
        html, md = self._render({"meta": {"project": "Demo"}, "bands": [{"id": "b", "t": "B"}], "spine": [],
            "modules": [{"id": "m1", "label": "Widget", "band": "b", "coupling": "low", "deps": [],
                         "loc": 5, "score": 80, "grade": "B", "tags": ["clean"], "findings": []}]})
        self.assertIn("Widget", html)        # label present in the DATA
        self.assertIn("function esc(", html)  # the escaper ships
        self.assertIn("Widget", md)

    def test_script_breakout_blocked(self):
        # a label containing </script> must not be able to close the data <script> tag
        html, _ = self._render({"meta": {}, "bands": [{"id": "b", "t": "B"}], "spine": [],
            "modules": [{"id": "m1", "label": "</script><script>alert(1)</script>", "band": "b",
                         "coupling": "low", "deps": [], "loc": 1, "score": 50, "grade": "D",
                         "tags": ["stub"], "findings": [{"sev": "HIGH", "loc": "a:1", "text": "x"}]}]})
        self.assertEqual(html.count("</script>"), 1)  # only the real closing tag


if __name__ == "__main__":
    unittest.main()
