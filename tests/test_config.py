import tempfile
import unittest
from pathlib import Path

from jobcatch.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent

MIN = """
[[track]]
name = "{name}"
sites = ["saramin"]
keywords = ["설계"]
career = ["신입"]
"""


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.toml"

    def tearDown(self):
        self.tmp.cleanup()

    def test_env_wins_over_file(self):
        self.path.write_text(MIN.format(name="B"), encoding="utf-8")
        cfg = load_config({"JOBCATCH_CONFIG": MIN.format(name="A")}, self.path)
        self.assertEqual(cfg.tracks[0].name, "A")

    def test_file_used_without_env(self):
        self.path.write_text(MIN.format(name="B"), encoding="utf-8")
        cfg = load_config({}, self.path)
        self.assertEqual(cfg.tracks[0].name, "B")

    def test_missing_raises(self):
        with self.assertRaises(ConfigError):
            load_config({}, self.path)

    def test_broken_toml_raises_without_echo(self):
        with self.assertRaises(ConfigError) as ctx:
            load_config({"JOBCATCH_CONFIG": "keywords = [비밀키워드"}, self.path)
        self.assertNotIn("비밀키워드", str(ctx.exception))

    def test_unknown_site_rejected(self):
        bad = MIN.format(name="A").replace('["saramin"]', '["wanted"]')
        with self.assertRaises(ConfigError):
            load_config({"JOBCATCH_CONFIG": bad}, self.path)

    def test_unknown_career_rejected(self):
        bad = MIN.format(name="A").replace('["신입"]', '["인턴"]')
        with self.assertRaises(ConfigError):
            load_config({"JOBCATCH_CONFIG": bad}, self.path)

    def test_no_track_rejected(self):
        with self.assertRaises(ConfigError):
            load_config({"JOBCATCH_CONFIG": "[run]\nmax_pages = 1\n"}, self.path)

    def test_bad_education_rejected(self):
        with self.assertRaises(ConfigError):
            load_config({"JOBCATCH_CONFIG": '[common]\neducation = "대학교"\n' + MIN.format(name="A")},
                        self.path)

    def test_error_hides_track_name(self):
        bad = MIN.format(name="비밀직무").replace('["saramin"]', '["wanted"]')
        with self.assertRaises(ConfigError) as ctx:
            load_config({"JOBCATCH_CONFIG": bad}, self.path)
        self.assertNotIn("비밀직무", str(ctx.exception))
        self.assertIn("track #1", str(ctx.exception))

    def test_wrong_shape_is_config_error(self):
        for text in ['[track]\nname = "A"\n', 'common = 1\n' + MIN.format(name="A"),
                     'run = "x"\n' + MIN.format(name="A")]:
            with self.subTest(text=text[:12]):
                with self.assertRaises(ConfigError):
                    load_config({"JOBCATCH_CONFIG": text}, self.path)

    def test_groups_and_extra_tags(self):
        text = ('[common]\nextra_tags = ["설계검증"]\n' + MIN.format(name="A")
                + 'groups = { "기구설계" = ["기구"], "장비설계" = ["장비"] }\n')
        cfg = load_config({"JOBCATCH_CONFIG": text}, self.path)
        self.assertEqual(cfg.common.extra_tags, ["설계검증"])
        self.assertEqual(list(cfg.tracks[0].groups), ["기구설계", "장비설계"])
        self.assertEqual(cfg.tracks[0].groups["장비설계"], ["장비"])

    def test_bad_groups_rejected(self):
        text = MIN.format(name="A") + 'groups = ["기구"]\n'
        with self.assertRaises(ConfigError):
            load_config({"JOBCATCH_CONFIG": text}, self.path)

    def test_example_config_loads(self):
        cfg = load_config({}, ROOT / "config.example.toml")
        self.assertEqual(len(cfg.tracks), 2)

    def test_defaults(self):
        cfg = load_config({"JOBCATCH_CONFIG": MIN.format(name="A")}, self.path)
        self.assertEqual(cfg.max_pages, 2)
        self.assertEqual(cfg.delay_sec, 2.0)
        self.assertEqual(cfg.max_cards_per_track, 30)
        self.assertEqual(cfg.common.education, "")
        self.assertEqual(cfg.common.commute_limit_min, 60)
        self.assertEqual(cfg.common.commute_soft_min, 75)
        self.assertEqual(cfg.common.max_detail_lookups, 150)
        self.assertEqual(cfg.tracks[0].include_any, [])


if __name__ == "__main__":
    unittest.main()
