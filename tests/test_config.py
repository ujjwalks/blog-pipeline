import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from config import validate_config


BASE = {
    "target": {"repoPath": "/tmp/app", "contentDir": "content/blog", "blogFormat": "json", "categories": ["accounting"], "authors": [{"id": "finboard-team"}]},
    "personas": [{"id": "cfo", "name": "CFO", "pains": ["slow close"], "keywords": ["close"]}],
    "topicsPerRun": 10,
    "blogsPerRun": 1,
    "frequency": "daily",
    "cron": "10 12 * * *",
    "scheduler": "launchd",
    "gates": {"topicApproval": "auto", "contentApproval": "auto"},
    "reviewChannel": {"type": "slack", "slack": {"channelId": "C123", "webhookEnv": "BLOG_WEBHOOK", "botTokenEnv": "BLOG_BOT_TOKEN"}},
    "review": {"mode": "vercel-preview"},
    "deploy": {"mode": "git-push", "remote": "origin", "target": "main"},
    "automation": {
        "timezone": "Asia/Kolkata", "minTopicScore": 18,
        "minSourceAuthority": 4, "similarityThreshold": 0.72,
        "productionBaseUrl": "https://finboard.ai",
        "sitemapUrl": "https://finboard.ai/sitemap.xml",
        "verificationAttempts": 30, "verificationIntervalSeconds": 20,
        "validationCommands": [["python3", "-m", "unittest", "discover", "-s", "tests"], ["yarn", "--cwd", "frontend", "test:unit"], ["yarn", "--cwd", "frontend", "build"]]
    }
}


class AutoConfigTest(unittest.TestCase):
    def test_accepts_complete_auto_config(self):
        self.assertEqual(validate_config(BASE), [])

    def test_rejects_one_automatic_gate(self):
        cfg = copy.deepcopy(BASE)
        cfg["gates"]["contentApproval"] = "manual"
        self.assertIn("gates: automatic mode requires topicApproval and contentApproval to both equal 'auto'", validate_config(cfg))

    def test_rejects_secret_value_and_bad_threshold(self):
        cfg = copy.deepcopy(BASE)
        cfg["reviewChannel"]["slack"]["webhookEnv"] = "https://hooks.slack.com/services/secret"
        cfg["automation"]["similarityThreshold"] = 1.2
        errors = validate_config(cfg)
        self.assertTrue(any("webhookEnv" in error for error in errors))
        self.assertTrue(any("similarityThreshold" in error for error in errors))

    def test_requires_one_blog_per_run_in_automatic_mode(self):
        cfg = copy.deepcopy(BASE)
        cfg["blogsPerRun"] = 2
        self.assertIn("blogsPerRun: automatic mode requires blogsPerRun to equal 1", validate_config(cfg))

