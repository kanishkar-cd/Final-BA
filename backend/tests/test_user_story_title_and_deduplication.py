from app.agents.user_story_agent import _dedupe_stories, _title_from_summary


class _Logger:
    def warning(self, *_args, **_kwargs):
        pass


def test_title_from_summary_does_not_end_at_eight_words() -> None:
    summary = "Create an approved strategy and messaging framework and deliver the finalized sitemap"

    assert _title_from_summary(summary) == summary


def test_title_from_user_story_keeps_only_complete_action() -> None:
    summary = "As a marketer, I want to publish an approved campaign, so that customers see consistent messaging."

    assert _title_from_summary(summary) == "Publish an approved campaign"


def test_dedupe_stories_preserves_repeated_wording_for_distinct_features() -> None:
    from types import SimpleNamespace

    first = SimpleNamespace(
        id="US-001",
        feature_id="FEAT-1",
        one_line_story_id="OLS-1",
        user_story="As a marketer, I want to publish a campaign, so that customers are informed.",
        title="Publish a campaign",
    )
    repeated = SimpleNamespace(
        id="US-002",
        feature_id="FEAT-2",
        one_line_story_id="OLS-2",
        user_story="As a marketer, I want to publish a campaign, so that customers are informed.",
        title="Publish a campaign",
    )

    assert _dedupe_stories([first, repeated], logger=_Logger()) == [first, repeated]
