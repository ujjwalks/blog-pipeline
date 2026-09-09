"""Behavior tests for the unattended model artifact boundary."""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from auto_artifact import (  # noqa: E402
    ARTIFACT_JSON_SCHEMA,
    parse_claude_output,
    safe_artifact_paths,
    validate_artifact,
)
from existing import PostRecord  # noqa: E402


AUTO_CONFIG = {
    "target": {
        "repoPath": "/tmp/app",
        "contentDir": "frontend/content/blog",
        "blogFormat": "json",
        "categories": ["accounting", "tech"],
        "authors": [{"id": "finboard-team"}],
    },
    "automation": {
        "minTopicScore": 18,
        "minSourceAuthority": 4,
        "similarityThreshold": 0.72,
        "productionBaseUrl": "https://finboard.ai",
    },
}


def article_content():
    opening = (
        "QuickBooks AI now lets finance teams review current accounting data inside conversational tools while keeping approval with a qualified person. "
        "Teams should automate retrieval, summaries, and draft workflows, but they should still verify source transactions, deterministic calculations, reconciliations, and every consequential accounting decision before relying on the result."
    )
    detail = " ".join(["Finance teams can inspect evidence and preserve a reliable audit trail before approving a result."] * 38)
    return (
        f"<p>{opening}</p>"
        '<h2>Why QuickBooks AI matters now</h2><p>On 2026-07-28, <a href="https://www.intuit.com/blog/news-social/quickbooks-expands-into-claude-and-chatgpt-with-new-sales-invoicing-payroll-and-lending-features/">Intuit announced new connected actions</a>. ' + detail + "</p>"
        '<h2>What finance teams can automate</h2><p>' + detail + ' <a href="/blog/how-to-design-a-trustworthy-ai-finance-architecture">See the architecture guide</a>.</p>'
        '<h2>Accounting controls still matter</h2><p>Source data supports each claim. Deterministic calculation produces the number. Review checks the evidence. A qualified person owns the decision. ' + detail + "</p>"
        '<h2>Limits and common mistakes</h2><p>' + detail + ' <a href="/blog/designing-audit-ready-controls-without-slowing-the-close">Review audit-ready controls</a>.</p>'
        '<h2>Frequently asked questions</h2>'
        '<h3>Can QuickBooks AI post invoices?</h3><p>It can support connected invoice actions when the user authorizes them.</p>'
        '<h3>Does QuickBooks AI replace review?</h3><p>No. A qualified finance professional should review consequential accounting outputs.</p>'
        '<h3>What should teams automate first?</h3><p>Start with retrieval, summaries, and draft workflows that retain source evidence.</p>'
        '<h3>How should teams verify results?</h3><p>Trace claims to transactions, use deterministic calculations, and reconcile to the books.</p>'
        '<p>FinBoard provides controlled multi-entity reporting with traceable evidence. <a href="https://finboard.ai">Explore FinBoard</a>.</p>'
    )


FAQS = [
    ("Can QuickBooks AI post invoices?", "It can support connected invoice actions when the user authorizes them."),
    ("Does QuickBooks AI replace review?", "No. A qualified finance professional should review consequential accounting outputs."),
    ("What should teams automate first?", "Start with retrieval, summaries, and draft workflows that retain source evidence."),
    ("How should teams verify results?", "Trace claims to transactions, use deterministic calculations, and reconcile to the books."),
]


def valid_artifact():
    slug = "quickbooks-ai-for-finance-teams"
    return {
        "outcome": "publish",
        "topic": {
            "slug": slug,
            "title": "QuickBooks AI for Finance Teams",
            "persona": "cfo",
            "angle": "What to automate and what to review",
            "primaryKeyword": "QuickBooks AI",
            "intentSummary": "QuickBooks AI automation and accounting review controls for finance teams",
            "whyNow": "Intuit added connected Claude and ChatGPT actions on 2026-07-28.",
            "scores": {"freshness": 5, "audienceFit": 5, "sourceAuthority": 4, "searchSharingPotential": 4, "productRelevance": 5},
            "sources": [
                {"url": "https://www.intuit.com/blog/news-social/quickbooks-expands-into-claude-and-chatgpt-with-new-sales-invoicing-payroll-and-lending-features/", "publisher": "Intuit", "publishedOrUpdated": "2026-07-28", "claim": "Connected actions launched", "authority": "primary"},
                {"url": "https://quickbooks.intuit.com/learn-support/en-us/help-article/mobile-and-apps/connect-quickbooks-online-chatgpt/L0RDe9RPd_US_en_US", "publisher": "QuickBooks", "publishedOrUpdated": "2026-08-26", "claim": "Connection steps", "authority": "primary"},
            ],
        },
        "blog": {
            "slug": slug,
            "title": "QuickBooks AI for Finance Teams: What to Automate and Review",
            "category": "accounting",
            "excerpt": "QuickBooks AI gives finance teams useful automation while accounting review and source evidence remain essential.",
            "author": "FinBoard Team",
            "authorId": "finboard-team",
            "date": "2026-09-09",
            "coverImage": f"/blog/covers/{slug}.png",
            "coverAlt": "QuickBooks AI workflow for finance teams with review controls",
            "format": "html",
            "order": 100,
            "structuredData": {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "BlogPosting", "headline": "QuickBooks AI for Finance Teams: What to Automate and Review", "datePublished": "2026-09-09", "dateModified": "2026-09-09", "author": {"@type": "Organization", "@id": "https://finboard.ai/#organization", "name": "FinBoard Team", "url": "https://finboard.ai/about"}, "mainEntityOfPage": {"@type": "WebPage", "@id": f"https://finboard.ai/blog/{slug}"}, "image": f"https://finboard.ai/blog/covers/{slug}.png"},
                    {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}} for question, answer in FAQS]},
                ],
            },
            "content": article_content(),
        },
        "cover": {"tag": "For Finance Teams", "accent": "#2563EB"},
    }


class AutoArtifactTest(unittest.TestCase):
    def test_schema_requires_publish_payload_or_no_topic_reason(self):
        self.assertEqual(ARTIFACT_JSON_SCHEMA["oneOf"][0]["required"], ["outcome", "topic", "blog", "cover"])
        self.assertEqual(ARTIFACT_JSON_SCHEMA["oneOf"][1]["required"], ["outcome", "reason"])

    def test_parses_structured_output_and_result_fallback(self):
        artifact = {"outcome": "nothing_publishable", "reason": "No candidate met 18 points"}
        self.assertEqual(parse_claude_output(json.dumps({"structured_output": artifact})), artifact)
        self.assertEqual(parse_claude_output(json.dumps({"result": json.dumps(artifact)})), artifact)
        with self.assertRaisesRegex(ValueError, "structured_output"):
            parse_claude_output(json.dumps({"result": 4}))

    def test_valid_publish_artifact_passes(self):
        self.assertEqual(validate_artifact(valid_artifact(), AUTO_CONFIG, "2026-09-09", [], []), [])

    def test_nothing_publishable_requires_nonempty_reason(self):
        self.assertEqual(validate_artifact({"outcome": "nothing_publishable", "reason": "No qualified topic"}, AUTO_CONFIG, "2026-09-09", [], []), [])
        self.assertTrue(validate_artifact({"outcome": "nothing_publishable", "reason": " "}, AUTO_CONFIG, "2026-09-09", [], []))

    def test_rejects_low_score_and_missing_primary_source(self):
        artifact = valid_artifact()
        artifact["topic"]["scores"]["sourceAuthority"] = 3
        artifact["topic"]["sources"] = [dict(source, authority="secondary") for source in artifact["topic"]["sources"]]
        errors = validate_artifact(artifact, AUTO_CONFIG, "2026-09-09", [], [])
        self.assertTrue(any("sourceAuthority" in error for error in errors))
        self.assertTrue(any("primary source" in error for error in errors))

    def test_rejects_duplicate_and_contract_drift(self):
        artifact = valid_artifact()
        artifact["blog"]["authorId"] = "someone-else"
        artifact["blog"]["date"] = "2026-09-08"
        posts = [PostRecord(artifact["topic"]["slug"], "Older title", "Existing intent", ())]
        errors = validate_artifact(artifact, AUTO_CONFIG, "2026-09-09", posts, [])
        self.assertTrue(any("duplicate" in error for error in errors))
        self.assertTrue(any("authorId" in error for error in errors))
        self.assertTrue(any("publish date" in error for error in errors))

    def test_rejects_url_faq_and_structure_drift(self):
        artifact = valid_artifact()
        graph = artifact["blog"]["structuredData"]["@graph"]
        graph[0]["mainEntityOfPage"]["@id"] = "https://finboard.ai/blog/wrong"
        graph[1]["mainEntity"][0]["acceptedAnswer"]["text"] = "Different answer"
        artifact["blog"]["content"] = artifact["blog"]["content"].replace("<h2>Limits and common mistakes</h2>", "")
        errors = validate_artifact(artifact, AUTO_CONFIG, "2026-09-09", [], [])
        self.assertTrue(any("canonical" in error for error in errors))
        self.assertTrue(any("FAQ" in error for error in errors))

    def test_safe_paths_reject_escape_and_return_canonical_paths(self):
        article, cover = safe_artifact_paths(Path("/tmp/app"), AUTO_CONFIG, valid_artifact())
        self.assertEqual(article, Path("/tmp/app/frontend/content/blog/quickbooks-ai-for-finance-teams.json").resolve())
        self.assertEqual(cover, Path("/tmp/app/frontend/public/blog/covers/quickbooks-ai-for-finance-teams.png").resolve())
        artifact = valid_artifact()
        artifact["blog"]["slug"] = "../../outside"
        with self.assertRaisesRegex(ValueError, "invalid slug"):
            safe_artifact_paths(Path("/tmp/app"), AUTO_CONFIG, artifact)


if __name__ == "__main__":
    unittest.main()
