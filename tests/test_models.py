from premote.models import QuotaBucket, QuotaGroup, QuotaReport, WindowInfo, PromptResult


def test_quota_bucket():
    bucket = QuotaBucket(
        id="gemini-weekly",
        name="Weekly Limit",
        description="Weekly window",
        window="weekly",
        remaining_fraction=0.984,
        reset_time="2026-09-24T10:15:12Z",
    )
    assert bucket.remaining_percent == 98
    assert bucket.window == "weekly"


def test_quota_report_from_json():
    data = {
        "command": {
            "name": "usage",
            "data": {
                "groups": [
                    {
                        "name": "Gemini Models",
                        "description": "Models group",
                        "buckets": [
                            {
                                "id": "gemini-weekly",
                                "name": "Weekly Limit Remaining",
                                "description": "Weekly",
                                "window": "weekly",
                                "remaining_fraction": 0.95,
                                "reset_time": "2026-09-24T10:00:00Z",
                            }
                        ],
                    }
                ]
            },
        }
    }
    report = QuotaReport.from_json_dict(data)
    assert len(report.groups) == 1
    assert report.groups[0].name == "Gemini Models"
    assert report.groups[0].buckets[0].remaining_percent == 95


def test_window_info():
    w = WindowInfo(
        id="0x01c00003",
        desktop=1,
        x=0,
        y=75,
        width=1600,
        height=849,
        title="Terminal - tom@llm-prototypowanie:~/github",
    )
    assert w.desktop == 1
    assert w.width == 1600


def test_prompt_result():
    res = PromptResult(response="Hello world", status="SUCCESS")
    assert res.response == "Hello world"
    assert res.status == "SUCCESS"
